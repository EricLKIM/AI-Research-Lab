#!/usr/bin/env python3
"""Create historical Topic Research snapshots from time-bounded API sources."""
from __future__ import annotations

import argparse
import math
import random
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        configured = os.environ.get("AI_RESEARCH_LAB_HOME")
        if configured:
            return Path(configured).resolve()
        executable_dir = Path(sys.executable).resolve().parent
        for candidate in (executable_dir, *executable_dir.parents):
            if (candidate / "AI Research Lab.exe").exists():
                return candidate
        return executable_dir
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()


def _app_data_root() -> Path:
    if getattr(sys, "frozen", False):
        configured = os.environ.get("AI_RESEARCH_LAB_DATA_HOME")
        if configured:
            return Path(configured).resolve()
        local_app_data = os.environ.get("LOCALAPPDATA")
        return (Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local") / "AI Research Lab"
    return PROJECT_ROOT


APP_DATA_ROOT = _app_data_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_lab.crawler.topic_news import TopicNewsCrawler
from research_lab.digest.topic_formatter import _slugify
from research_lab.i18n import DEFAULT_OUTPUT_LANGUAGE, google_search_profile
from research_lab.time_series import save_snapshot
from research_lab.digest.baseline_formatter import save_seven_day_baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GDELT·X·YouTube의 날짜 범위 API를 사용해 과거 Topic Research 스냅샷을 채웁니다."
    )
    parser.add_argument("--topic", required=True, help="backfill할 주제")
    parser.add_argument("--backfill-days", type=int, required=True, help="과거 수집 일수 (1~365)")
    parser.add_argument(
        "--collection-interval-hours",
        type=int,
        default=None,
        choices=[1, 3, 6, 8, 12, 24],
        help="스냅샷 시간 구간. --collection-interval-days와 함께 사용할 수 없음",
    )
    parser.add_argument(
        "--collection-interval-days",
        type=int,
        default=None,
        help="날짜별 백필 스냅샷 간격 (1~30일, 기본: 1일)",
    )
    parser.add_argument("--limit", type=int, default=10, help="각 구간의 최대 자료 수")
    parser.add_argument(
        "--community-sources",
        default="gdelt,x,youtube",
        help="backfill 소스: gdelt,x,youtube (기본: gdelt,x,youtube)",
    )
    parser.add_argument("--output-dir", default=None, help="저장 경로 (기본: vault/)")
    parser.add_argument("--data-dir", default=None, help="JSON 데이터 저장 경로 (기본: output-dir)")
    parser.add_argument("--output-language", default=DEFAULT_OUTPUT_LANGUAGE)
    parser.add_argument(
        "--gdelt-source-language",
        default="global",
        choices=["global", "korean", "english"],
        help="GDELT 원문 언어: global, korean, english (기본: global)",
    )
    parser.add_argument(
        "--gdelt-region-profile",
        default="auto",
        choices=["auto", "global_even", "country_focus"],
        help="GDELT 지역 분산: auto, global_even, country_focus (기본: auto)",
    )
    parser.add_argument("--dry-run", action="store_true", help="API 호출·파일 저장 없이 대상 구간만 표시")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.backfill_days <= 365:
        raise SystemExit("--backfill-days must be between 1 and 365.")
    if args.limit <= 0:
        raise SystemExit("--limit must be greater than 0.")
    if args.collection_interval_days is not None and not 1 <= args.collection_interval_days <= 30:
        raise SystemExit("--collection-interval-days must be between 1 and 30.")
    if args.collection_interval_days is not None and args.collection_interval_hours is not None:
        raise SystemExit("Use only one of --collection-interval-days or --collection-interval-hours.")

    try:
        from dotenv import load_dotenv
        load_dotenv(APP_DATA_ROOT / ".env")
    except ImportError:
        pass

    requested_sources = {
        source.strip().lower()
        for source in args.community_sources.split(",")
        if source.strip()
    }
    unsupported = requested_sources - {"gdelt", "x", "youtube"}
    if unsupported:
        raise SystemExit(
            "Historical backfill currently supports only gdelt,x,youtube. "
            f"Unsupported: {', '.join(sorted(unsupported))}"
        )

    now = datetime.now().astimezone()
    if args.collection_interval_days is not None:
        interval = timedelta(days=args.collection_interval_days)
        interval_label = f"{args.collection_interval_days} days"
        window_count = math.ceil(args.backfill_days / args.collection_interval_days)
    else:
        interval_hours = args.collection_interval_hours or 24
        interval = timedelta(hours=interval_hours)
        interval_label = f"{interval_hours} hours"
        window_count = math.ceil(args.backfill_days * 24 / interval_hours)
    earliest = now - timedelta(days=args.backfill_days)
    profile = google_search_profile(args.output_language)
    vault_dir = Path(args.output_dir) if args.output_dir else APP_DATA_ROOT / "vault"
    data_dir = Path(args.data_dir) if args.data_dir else vault_dir
    topic_dir = data_dir / "topics" / _slugify(args.topic)

    print(f"Backfill topic: {args.topic}")
    print(f"Windows: {window_count} x {interval_label}")
    print(f"Range: {earliest.isoformat()} <= article_time < {now.isoformat()}")
    print(f"Sources: {', '.join(sorted(requested_sources))}")
    if "youtube" in requested_sources:
        print("YouTube uses one search request per window when configured.")
    if "gdelt" in requested_sources:
        print(
            "GDELT uses its public API; no API key is required. "
            "Requests use a response-based delay."
        )

    saved_count = 0
    last_gdelt_request_completed_at: float | None = None
    gdelt_post_request_delay = 0.0
    for index in range(window_count, 0, -1):
        window_end = now - interval * (index - 1)
        window_start = max(earliest, window_end - interval)
        active_sources = set(requested_sources)

        # X Recent Search is limited to the most recent seven days.
        if window_start < now - timedelta(days=7):
            active_sources.discard("x")
        if not active_sources:
            print(f"[{window_start:%Y-%m-%d %H:%M}] skipped (no source supports this range)")
            continue

        print(
            f"[{window_start:%Y-%m-%d %H:%M} to {window_end:%Y-%m-%d %H:%M}] "
            f"sources={','.join(sorted(active_sources))}",
            end="",
        )
        if args.dry_run:
            print(" dry-run")
            continue

        if "gdelt" in active_sources and last_gdelt_request_completed_at is not None:
            elapsed = time.monotonic() - last_gdelt_request_completed_at
            remaining = gdelt_post_request_delay - elapsed
            if remaining > 0:
                print(f" waiting {remaining:.1f}s before next GDELT request", end="")
                time.sleep(remaining)

        crawler = TopicNewsCrawler(
            lang=profile["lang"],
            country=profile["country"],
            lr=profile["lr"],
            gossip_ratio=(
                0 if active_sources == {"gdelt"}
                else 100 if "gdelt" not in active_sources
                else 50
            ),
            gossip_mode="strict",
            community_sources=active_sources,
            allow_google_gossip_fallback=False,
            allow_google_news=False,
            gdelt_source_language=args.gdelt_source_language,
            gdelt_region_profile=args.gdelt_region_profile,
        )
        articles = crawler.fetch(
            args.topic,
            limit=args.limit,
            window_start=window_start,
            window_end=window_end,
        )
        if "gdelt" in active_sources:
            last_gdelt_request_completed_at = time.monotonic()
            if crawler.gdelt_crawler.last_response_seconds is not None:
                response_seconds = crawler.gdelt_crawler.last_response_seconds
                # Real runs showed 35-43 second pauses still triggered 429s.
                # Use a conservative independent cool-down after each success.
                gdelt_post_request_delay = random.uniform(60.0, 75.0)
                print(
                    f" [GDELT] response took {response_seconds:.1f}s; "
                    f"next request waits {gdelt_post_request_delay:.2f}s",
                    end="",
                )
            else:
                gdelt_post_request_delay = random.uniform(75.0, 90.0)
        if not articles:
            print(" 0 items - snapshot skipped")
            continue
        snapshot = save_snapshot(
            topic_dir,
            args.topic,
            articles,
            collected_at=window_end,
            window_start=window_start,
            window_end=window_end,
            output_language=args.output_language,
            gossip_ratio=crawler.gossip_ratio,
            time_unknown_articles=crawler.last_time_unknown_articles,
        )
        saved_count += 1
        print(f" {len(articles)} items -> {snapshot.name}")

    print(f"Backfill complete: {saved_count} snapshots saved.")
    if saved_count and args.backfill_days >= 7 and not args.dry_run:
        baseline = save_seven_day_baseline(topic_dir, args.topic, vault_dir)
        if baseline:
            print(f"7-day baseline saved: {baseline}")


if __name__ == "__main__":
    main()
