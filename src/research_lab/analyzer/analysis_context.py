"""Persistent, bounded cross-topic context for trend analysis."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from research_lab.tagging import hierarchy_for, normalize_tag

CONTEXT_VERSION = 1
MAX_CROSS_TOPIC_EVIDENCE = 5


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _iso_time(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _freshness(value: object) -> float:
    """14-day half-life for prior analysis evidence."""
    age_days = max(0.0, (datetime.now(timezone.utc) - _iso_time(value)).total_seconds() / 86400)
    return 0.5 ** (age_days / 14.0)


def _item_tags(item: dict) -> set[str]:
    tags: set[str] = set()
    for value in item.get("tags", []) or []:
        name = value.get("tag", "") if isinstance(value, dict) else value
        normalized = normalize_tag(name)
        if normalized:
            tags.add(normalized)
    return tags


def index_path(data_dir: Path) -> Path:
    return data_dir / "_analysis_tag_index.json"


def update_tag_index(data_dir: Path, topic: str, result: dict, analysis_path: Path) -> None:
    """Replace this topic's index rows with the newest compact analysis rows."""
    path = index_path(data_dir)
    index = _load_json(path, {"version": CONTEXT_VERSION, "entries": []})
    entries = [row for row in index.get("entries", []) if row.get("topic") != topic]
    generated_at = result.get("generated_at") or datetime.now().astimezone().isoformat()
    for category in ("confirmed_trends", "emerging_signals", "rumors"):
        for item in result.get(category, []) or []:
            tags = _item_tags(item)
            if not tags:
                continue
            for tag in tags:
                entries.append({
                    "topic": topic,
                    "tag": tag,
                    "parents": hierarchy_for([tag]),
                    "category": category,
                    "title": str(item.get("title", ""))[:180],
                    "summary": str(item.get("summary", ""))[:280],
                    "confidence": float(item.get("confidence", 0)),
                    "generated_at": generated_at,
                    "analysis_path": str(analysis_path),
                })
    # One newest analysis per topic keeps this index intentionally small.
    _write_json(path, {"version": CONTEXT_VERSION, "entries": entries})


def build_cross_topic_context(data_dir: Path, topic: str, tags: set[str]) -> tuple[list[dict], str]:
    """Look up only matching tag rows; broad parent-only matches have lower weight."""
    index = _load_json(index_path(data_dir), {"entries": []})
    parents = set(hierarchy_for(tags))
    candidates: list[dict] = []
    for row in index.get("entries", []):
        if row.get("topic") == topic:
            continue
        direct = row.get("tag") in tags
        parent_match = bool(set(row.get("parents", [])) & parents)
        if not (direct or parent_match):
            continue
        relevance = 1.0 if direct else 0.35
        score = relevance * (float(row.get("confidence", 0)) / 100.0) * _freshness(row.get("generated_at"))
        candidates.append({**row, "match_type": "direct" if direct else "hierarchy", "context_weight": round(score, 3)})
    candidates.sort(key=lambda row: (row["context_weight"], row.get("generated_at", "")), reverse=True)
    selected = candidates[:MAX_CROSS_TOPIC_EVIDENCE]
    signature = hashlib.sha256(json.dumps(selected, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return selected, signature


def state_path(topic_dir: Path) -> Path:
    return topic_dir / "_analysis_state.json"


def load_state(topic_dir: Path) -> dict:
    return _load_json(state_path(topic_dir), {})


def save_state(topic_dir: Path, *, source_ids: set[str], context_signature: str, output_path: Path, time_series_signature: str = "") -> None:
    _write_json(state_path(topic_dir), {
        "version": CONTEXT_VERSION,
        "processed_article_ids": sorted(source_ids),
        "context_signature": context_signature,
        "time_series_signature": time_series_signature,
        "output_path": str(output_path),
        "updated_at": datetime.now().astimezone().isoformat(),
    })
