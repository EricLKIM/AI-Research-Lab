#!/usr/bin/env python3
"""Run configured favorite-topic collection non-interactively from Task Scheduler."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from research_lab.digest.topic_formatter import _slugify
from research_lab.pending_backfills import pending_days


def missing_snapshot_dates(topic: str, history_days: int) -> list[str]:
    topic_dir = ROOT / "vault" / "topics" / _slugify(topic)
    snapshots = topic_dir / "snapshots"
    covered: set[date] = set()
    snapshot_paths = snapshots.glob("*.json") if snapshots.exists() else []
    snapshot_paths = list(snapshot_paths)
    if not snapshot_paths:
        if not topic_dir.exists():
            return []
        return [
            (date.today() - timedelta(days=offset)).isoformat()
            for offset in range(history_days, 0, -1)
        ]
    for path in snapshot_paths:
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            start = snapshot.get("window_start")
            end = snapshot.get("window_end")
            if start and end:
                cursor = datetime.fromisoformat(start).date()
                end_day = datetime.fromisoformat(end).date()
                while cursor < end_day:
                    covered.add(cursor)
                    cursor += timedelta(days=1)
            elif snapshot.get("collected_at"):
                covered.add(datetime.fromisoformat(snapshot["collected_at"]).date())
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            continue
    baseline = min(covered, default=date.today())
    return [
        (date.today() - timedelta(days=offset)).isoformat()
        for offset in range(history_days, 0, -1)
        if date.today() - timedelta(days=offset) >= baseline and date.today() - timedelta(days=offset) not in covered
    ]


def main() -> int:
    settings_path = ROOT / "gui_settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    favorites_path = ROOT / "topics_favorites.json"
    topics = json.loads(favorites_path.read_text(encoding="utf-8")) if favorites_path.exists() else []
    output_dir = settings.get("vault_path", str(ROOT / "vault"))
    sources = ",".join(name for name, enabled in settings.get("community_sources", {}).items() if enabled)
    for topic in topics:
        snapshots = ROOT / "vault" / "topics" / _slugify(str(topic)) / "snapshots"
        latest = max(snapshots.glob("*.json"), default=None) if snapshots.exists() else None
        missed_days = max(0, (datetime.now().astimezone() - datetime.fromtimestamp(latest.stat().st_mtime).astimezone()).days) if latest else int(settings.get("new_topic_backfill_days", 7))
        queued_dump_days = pending_days(ROOT / "vault", str(topic))
        missing_dates = missing_snapshot_dates(str(topic), int(settings.get("new_topic_backfill_days", 7)))
        if queued_dump_days:
            command = [
                sys.executable, "-u", "scripts/backfill_gdelt_dump.py", "--topic", str(topic),
                "--backfill-days", "1", "--collection-interval-days",
                str(settings.get("new_topic_backfill_interval_days", 1)), "--daily-limit",
                str(settings.get("backfill_daily_article_count", 5)), "--cache-policy",
                settings.get("dump_cache_policy", "persistent"), "--data-dir", str(ROOT / "vault"), "--output-dir", output_dir,
                "--scan-mode", settings.get("dump_scan_mode", "sample"),
                "--output-language", settings.get("output_language", "한국어"), "--retry-pending",
            ]
            # No --allow-http-fallback here: Windows scheduled tasks run without
            # a person to make an informed consent decision.
            subprocess.run(command, cwd=ROOT, check=False)
        missing_dates = [value for value in missing_dates if value not in queued_dump_days]
        if settings.get("backfill_method", "doc_api") == "gdelt_dump" and missing_dates:
            subprocess.run([
                sys.executable, "-u", "scripts/backfill_gdelt_dump.py", "--topic", str(topic),
                "--backfill-days", str(len(missing_dates)), "--dates", ",".join(missing_dates), "--collection-interval-days",
                str(settings.get("new_topic_backfill_interval_days", 1)), "--daily-limit",
                str(settings.get("backfill_daily_article_count", 5)), "--cache-policy",
                settings.get("dump_cache_policy", "persistent"), "--data-dir", str(ROOT / "vault"), "--output-dir", output_dir,
                "--scan-mode", settings.get("dump_scan_mode", "sample"),
                "--output-language", settings.get("output_language", "한국어"),
            ], cwd=ROOT, check=False)
        elif settings.get("backfill_method", "doc_api") != "gdelt_dump" and missed_days:
            subprocess.run([
                sys.executable, "-u", "scripts/backfill_topic.py", "--topic", str(topic),
                "--backfill-days", str(min(missed_days, 365)), "--collection-interval-days",
                str(settings.get("new_topic_backfill_interval_days", 1)), "--limit",
                str(settings.get("backfill_daily_article_count", 5)), "--community-sources", "gdelt",
                "--data-dir", str(ROOT / "vault"), "--output-dir", output_dir,
            ], cwd=ROOT, check=False)
        command = [
            sys.executable, "-u", "scripts/topic_digest.py", "--topic", str(topic),
            "--limit", "10", "--vault-name", settings.get("vault_name", "vault"),
            "--output-dir", output_dir, "--data-dir", str(ROOT / "vault"),
            "--model", settings.get("model", "gpt-5.4-nano"),
            "--format", settings.get("export_format", "obsidian"),
            "--output-language", settings.get("output_language", "한국어"),
            "--gossip-ratio", str(settings.get("gossip_ratio", 20)),
            "--community-sources", sources,
            "--latest-news-priority", settings.get("latest_news_priority", "google_rss"),
            "--google-rss-region-profile", settings.get("google_rss_region_profile", "balanced"),
        ]
        subprocess.run(command, cwd=ROOT, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
