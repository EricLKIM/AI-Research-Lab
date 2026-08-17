from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from research_lab.time_series import (
    get_latest_snapshot,
    get_snapshot_count,
    load_snapshots,
    save_snapshot,
)


def test_time_series_snapshot() -> None:
    collected_at = datetime(
        2026,
        8,
        12,
        12,
        0,
        0,
    ).astimezone()

    articles = [
        {
            "title": "Test Article 1",
            "url": "https://example.com/1",
        },
        {
            "title": "Test Article 2",
            "url": "https://example.com/2",
        },
    ]

    with TemporaryDirectory() as temp_dir:
        topic_directory = Path(temp_dir)

        snapshot_path = save_snapshot(
            topic_directory,
            "Test Topic",
            articles,
            collected_at=collected_at,
            output_language="English",
            gossip_ratio=20,
            backfill_scan_mode="full",
            time_unknown_articles=[
                {
                    "title": "Undated community signal",
                    "url": "https://example.com/unknown",
                    "kind": "gossip",
                    "time_status": "unknown",
                }
            ],
        )

        snapshots = load_snapshots(topic_directory)

        latest = get_latest_snapshot(topic_directory)

        assert snapshot_path.exists()
        assert get_snapshot_count(topic_directory) == 1
        assert latest is not None
        assert latest["topic"] == "Test Topic"
        assert latest["article_count"] == 2
        assert len(latest["articles"]) == 2
        assert latest["time_unknown_article_count"] == 1
        assert latest["time_unknown_articles"][0]["url"] == "https://example.com/unknown"
        assert latest["backfill_scan_mode"] == "full"
