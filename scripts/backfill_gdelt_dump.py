#!/usr/bin/env python3
"""Backfill topic snapshots from local-filtered daily GDELT GKG archives."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
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

from research_lab.crawler.gdelt_dump import GdeltDumpCrawler
from research_lab.digest.topic_formatter import _slugify
from research_lab.i18n import DEFAULT_OUTPUT_LANGUAGE
from research_lab.pending_backfills import pending_days, record_failure, resolve_day
from research_lab.time_series import save_snapshot
from research_lab.digest.baseline_formatter import save_seven_day_baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill locally from daily GDELT GKG dump files.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--backfill-days", type=int, default=None)
    parser.add_argument("--dates", default="", help="comma-separated calendar dates (YYYY-MM-DD) to fill")
    parser.add_argument("--collection-interval-days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--daily-limit", type=int, default=5, help="target number of articles per calendar day")
    parser.add_argument("--keywords", default="", help="comma-separated additional local filter keywords")
    parser.add_argument("--cache-dir", default=str(APP_DATA_ROOT / "vault" / "gdelt-cache"))
    parser.add_argument("--cache-policy", choices=["persistent", "temporary"], default="persistent")
    parser.add_argument("--scan-mode", choices=["sample", "full"], default="sample",
                        help="sample stops after the target count; full checks every 15-minute block")
    parser.add_argument("--data-dir", default=str(APP_DATA_ROOT / "vault"))
    parser.add_argument("--output-dir", default=None, help="human-readable Markdown output directory")
    parser.add_argument("--output-language", default=DEFAULT_OUTPUT_LANGUAGE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-pending", action="store_true", help="retry failed dump dates recorded in the local vault")
    parser.add_argument("--allow-http-fallback", action="store_true", help="manual, one-run-only fallback after an HTTPS certificate failure")
    parser.add_argument("--http-consent-file", default="", help="interactive GUI response file; never supplied by scheduled collection")
    args = parser.parse_args()
    requested_dates: list[date] = []
    try:
        requested_dates = sorted({date.fromisoformat(value.strip()) for value in args.dates.split(",") if value.strip()})
    except ValueError as error:
        raise SystemExit(f"--dates must use YYYY-MM-DD: {error}") from error
    if (not requested_dates and (args.backfill_days is None or not 1 <= args.backfill_days <= 365)) or not 1 <= args.collection_interval_days <= 30 or args.daily_limit < 1:
        raise SystemExit("backfill days must be 1..365 and interval days must be 1..30")

    now = datetime.now().astimezone()
    total_days = len(requested_dates) if requested_dates else args.backfill_days
    windows = math.ceil(total_days / args.collection_interval_days)
    extras = [item.strip() for item in args.keywords.split(",") if item.strip()]
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir) if args.output_dir else data_dir
    crawler = GdeltDumpCrawler(Path(args.cache_dir), cache_policy=args.cache_policy, allow_http_fallback=args.allow_http_fallback)
    topic_dir = data_dir / "topics" / _slugify(args.topic)
    print(f"Dump backfill topic: {args.topic}; windows: {windows} x {args.collection_interval_days} days; scan={args.scan_mode}; daily target={args.daily_limit}")
    print(f"Local keywords: {', '.join(crawler.build_keywords(args.topic, extras))}")
    retry_dates = pending_days(data_dir, args.topic) if args.retry_pending else []
    if retry_dates:
        print(f"Pending dump dates queued for retry: {', '.join(retry_dates)}")

    def request_http_consent(day) -> bool:
        """Pause this manual run until the GUI records a deliberate response."""
        if not args.http_consent_file:
            return False
        consent_path = Path(args.http_consent_file)
        try:
            consent_path.parent.mkdir(parents=True, exist_ok=True)
            consent_path.write_text(json.dumps({"status": "required", "topic": args.topic, "day": day.isoformat()}), encoding="utf-8")
        except OSError as error:
            print(f"  [Warning] cannot request HTTP consent: {error}", flush=True)
            return False
        print(f"[HTTP_CONSENT_REQUIRED] {consent_path}", flush=True)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                response = json.loads(consent_path.read_text(encoding="utf-8"))
                if "allow" in response:
                    consent_path.unlink(missing_ok=True)
                    return bool(response["allow"])
            except (OSError, json.JSONDecodeError):
                pass
            time.sleep(0.15)
        print("  [Warning] HTTP consent timed out; keeping HTTPS-only mode.", flush=True)
        return False

    def collect_days(days: list, start: datetime, end: datetime) -> list[dict]:
        articles: list[dict] = []
        seen: set[str] = set()
        for day in days:
            try:
                day_articles = crawler.filter_day(day, args.topic, args.daily_limit, extras, args.scan_mode)
                if crawler.last_failure_needs_http_consent and request_http_consent(day):
                    print("  [GDELT dump] user approved HTTP fallback for this run", flush=True)
                    crawler.allow_http_fallback = True
                    day_articles = crawler.filter_day(day, args.topic, args.daily_limit, extras, args.scan_mode)
                if crawler.last_failure is not None:
                    record_failure(
                        data_dir, args.topic, day.isoformat(), "gdelt_dump", str(crawler.last_failure),
                        needs_http_consent=crawler.last_failure_needs_http_consent,
                    )
                    print("  [Pending] retry will be included in the next manual or scheduled collection", flush=True)
                    continue
                resolve_day(data_dir, args.topic, day.isoformat())
                for article in day_articles:
                    if article["url"] not in seen:
                        articles.append(article)
                        seen.add(article["url"])
            finally:
                crawler.release_day(day)
        return articles

    calendar_days = requested_dates or [now.date() - timedelta(days=offset) for offset in range(args.backfill_days - 1, -1, -1)]
    processed_days = {day.isoformat() for day in calendar_days}
    for offset in range(0, len(calendar_days), args.collection_interval_days):
        days = calendar_days[offset:offset + args.collection_interval_days]
        start = datetime.combine(days[0], datetime.min.time(), tzinfo=now.tzinfo)
        end = datetime.combine(days[-1] + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
        print(f"[{start:%Y-%m-%d} to {end:%Y-%m-%d}] {len(days)} daily archives", end="", flush=True)
        if args.dry_run:
            print(" dry-run")
            continue
        articles = collect_days(days, start, end)
        if not articles:
            print(" 0 items - snapshot skipped")
            continue
        snapshot = save_snapshot(topic_dir, args.topic, articles, collected_at=end, window_start=start, window_end=end, output_language=args.output_language, gossip_ratio=0)
        print(f" {len(articles)} items -> {snapshot.name}")

    remaining_retry_days = [datetime.fromisoformat(value).date() for value in retry_dates if value not in processed_days]
    if remaining_retry_days and not args.dry_run:
        print(f"[pending retry] {len(remaining_retry_days)} daily archives", end="", flush=True)
        articles = collect_days(remaining_retry_days, now - timedelta(days=1), now)
        if articles:
            snapshot = save_snapshot(topic_dir, args.topic, articles, collected_at=now, window_start=now - timedelta(days=1), window_end=now, output_language=args.output_language, gossip_ratio=0)
            print(f" {len(articles)} items -> {snapshot.name}")
        else:
            print(" 0 items - snapshot skipped")
    if not args.dry_run and total_days >= 7:
        baseline = save_seven_day_baseline(topic_dir, args.topic, output_dir)
        if baseline:
            print(f"7-day baseline saved: {baseline}")


if __name__ == "__main__":
    main()
