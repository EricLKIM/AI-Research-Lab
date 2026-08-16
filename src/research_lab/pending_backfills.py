"""Persistent retry queue for backfill work that could not be collected."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


QUEUE_FILENAME = "pending_backfills.json"


def queue_path(data_dir: Path) -> Path:
    return data_dir / QUEUE_FILENAME


def load_pending(data_dir: Path) -> list[dict]:
    path = queue_path(data_dir)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_pending(data_dir: Path, records: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = queue_path(data_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def pending_days(data_dir: Path, topic: str, source: str = "gdelt_dump") -> list[str]:
    return sorted({str(item.get("day")) for item in load_pending(data_dir)
                   if item.get("topic") == topic and item.get("source") == source and item.get("day")})


def pending_requires_http_consent(data_dir: Path, topic: str, source: str = "gdelt_dump") -> bool:
    return any(item.get("topic") == topic and item.get("source") == source and item.get("needs_http_consent")
               for item in load_pending(data_dir))


def record_failure(data_dir: Path, topic: str, day: str, source: str, error: str, *, needs_http_consent: bool) -> None:
    records = load_pending(data_dir)
    now = datetime.now().astimezone().isoformat()
    for record in records:
        if record.get("topic") == topic and record.get("day") == day and record.get("source") == source:
            record.update({"last_error": error, "last_failed_at": now, "needs_http_consent": needs_http_consent,
                           "attempts": int(record.get("attempts", 0)) + 1})
            save_pending(data_dir, records)
            return
    records.append({"topic": topic, "day": day, "source": source, "last_error": error,
                    "created_at": now, "last_failed_at": now, "attempts": 1,
                    "needs_http_consent": needs_http_consent})
    save_pending(data_dir, records)


def resolve_day(data_dir: Path, topic: str, day: str, source: str = "gdelt_dump") -> None:
    save_pending(data_dir, [item for item in load_pending(data_dir)
                            if not (item.get("topic") == topic and item.get("day") == day and item.get("source") == source)])
