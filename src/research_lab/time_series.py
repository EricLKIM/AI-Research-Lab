from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from research_lab.tagging import tag_article


SCHEMA_VERSION = 2


def _safe_timestamp(timestamp: datetime) -> str:
    """
    Convert a datetime into a filesystem-safe timestamp.

    Example:
        2026-08-12T13:30:00+09:00
        ->
        2026-08-12_13-30-00
    """
    return timestamp.strftime("%Y-%m-%d_%H-%M-%S")


def _normalize_topic(topic: str) -> str:
    """Return a normalized topic name."""
    topic = topic.strip()

    if not topic:
        raise ValueError("Topic cannot be empty.")

    return topic

def _article_identity(article: dict[str, Any]) -> str:
    """
    Return a stable identifier for an article.

    URL is preferred because the same article should normally retain
    the same URL across multiple time-series collections.

    If URL is unavailable, fall back to source + title.
    """
    url = str(article.get("url") or "").strip()

    if url:
        identity_source = url
    else:
        source = str(article.get("source") or "").strip()
        title = str(article.get("title") or "").strip()
        identity_source = f"{source}|{title}"

    if not identity_source:
        raise ValueError("Article must contain at least a URL or source/title.")

    return hashlib.sha256(
        identity_source.encode("utf-8")
    ).hexdigest()

def get_snapshot_directory(topic_directory: Path) -> Path:
    """
    Return the directory where time-series snapshots are stored.
    """
    snapshot_directory = topic_directory / "snapshots"
    snapshot_directory.mkdir(parents=True, exist_ok=True)
    return snapshot_directory


def save_snapshot(
    topic_directory: Path,
    topic: str,
    articles: list[dict[str, Any]],
    *,
    collected_at: datetime | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    output_language: str | None = None,
    gossip_ratio: int | None = None,
    time_unknown_articles: list[dict[str, Any]] | None = None,
    backfill_scan_mode: str | None = None,
) -> Path:
    """
    Save one research collection as a time-series snapshot.

    Each execution creates a new JSON file instead of overwriting
    the previous collection.
    """
    topic = _normalize_topic(topic)

    if collected_at is None:
        collected_at = datetime.now().astimezone()

    snapshot_directory = get_snapshot_directory(topic_directory)

    filename = f"{_safe_timestamp(collected_at)}.json"
    snapshot_path = snapshot_directory / filename

    normalized_articles: list[dict[str, Any]] = []

    for article in articles:
        article_copy = tag_article(article, topic)

        # Preserve an existing ID if a future collector already provides one.
        article_copy.setdefault(
            "article_id",
            _article_identity(article_copy),
        )

        normalized_articles.append(article_copy)

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "topic": topic,
        "collected_at": collected_at.isoformat(),
        "window_start": (
            window_start.isoformat()
            if window_start is not None
            else None
        ),
        "window_end": (
            window_end.isoformat()
            if window_end is not None
            else None
        ),
        "output_language": output_language,
        "gossip_ratio": gossip_ratio,
        "backfill_scan_mode": backfill_scan_mode,
        "article_count": len(normalized_articles),
        "articles": normalized_articles,
        "time_unknown_article_count": len(time_unknown_articles or []),
        "time_unknown_articles": time_unknown_articles or [],
    }

    snapshot_path.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return snapshot_path


def load_snapshots(topic_directory: Path) -> list[dict[str, Any]]:
    """
    Load all time-series snapshots for a topic.

    Snapshots are returned in chronological order.
    """
    snapshot_directory = topic_directory / "snapshots"

    if not snapshot_directory.exists():
        return []

    snapshots: list[dict[str, Any]] = []

    for path in sorted(snapshot_directory.glob("*.json")):
        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if isinstance(data, dict):
            snapshots.append(data)

    return snapshots


def get_snapshot_count(topic_directory: Path) -> int:
    """Return the number of valid stored snapshots."""
    return len(load_snapshots(topic_directory))


def get_latest_snapshot(
    topic_directory: Path,
) -> dict[str, Any] | None:
    """Return the most recent snapshot, if one exists."""
    snapshots = load_snapshots(topic_directory)

    if not snapshots:
        return None

    return snapshots[-1]
