from datetime import datetime
from pathlib import Path

from research_lab.analyzer.time_series_analysis import build_time_series_summary
from research_lab.time_series import load_snapshots


SAMPLE_ROOT = Path(__file__).resolve().parents[1] / "sample_vault" / "vault"


def test_sample_vault_contains_a_usable_local_ai_time_series():
    topic_dir = SAMPLE_ROOT / "topics" / "AI"

    snapshots = load_snapshots(topic_dir)
    summary, _signature = build_time_series_summary(
        topic_dir,
        "AI",
        period_days=7,
        now=datetime.fromisoformat("2026-08-17T09:00:00+09:00"),
    )

    assert len(snapshots) == 4
    assert summary["data_quality"]["article_count"] == 12
    assert summary["data_quality"]["coverage_note"] == "usable"
