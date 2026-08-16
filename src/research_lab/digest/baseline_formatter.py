"""No-API baseline note created after a useful backfill completes."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from research_lab.analyzer.time_series_analysis import build_time_series_summary
from research_lab.digest.topic_formatter import _slugify, TOPICS_DIR


def save_seven_day_baseline(topic_dir: Path, topic: str, output_dir: Path) -> Path | None:
    summary, _ = build_time_series_summary(topic_dir, topic, 7)
    quality = summary["data_quality"]
    # A baseline is meaningful only when it represents more than an isolated run.
    if quality["snapshot_count"] < 2 or quality["article_count"] < 10:
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = Path(output_dir) / TOPICS_DIR / _slugify(topic) / f"{timestamp}_7d_baseline.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---", f"topic: {topic}", "tags:", "  - research-baseline", "  - seven-day", "---", "",
        f"# 7-day baseline: {topic}", "",
        "> [!info] This is an automatic local-data baseline, not a final conclusion or GPT analysis.", "",
        "## Coverage",
        f"- Period: {summary['period_start']} to {summary['period_end']}",
        f"- Snapshots: {quality['snapshot_count']} | Unique articles: {quality['article_count']} | Independent domains: {quality['independent_domain_count']}",
        "",
        "## Repeated signals",
    ]
    signals = [row for row in summary["signals"] if row["total"] >= 2]
    lines.extend(f"- {row['tag']}: {row['direction']} ({row['before']} -> {row['recent']})" for row in signals[:10])
    if not signals:
        lines.append("- Insufficient repeated signals yet.")
    lines += ["", "## Data quality", f"- Duplicate rate: {quality['duplicate_rate']:.1%} | Time-unknown rate: {quality['time_unknown_rate']:.1%}", f"- Coverage: {quality['coverage_note']}", "", "Use manual Trend Analysis for evidence-weighted conclusions and cross-topic context."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
