"""Deduplicated local alerts produced after a manual trend analysis."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


def _key(kind: str, text: str) -> str:
    return hashlib.sha256(f"{kind}|{text}".encode("utf-8")).hexdigest()[:16]


def build_alerts(result: dict, *, emerging: bool = True, rising: bool = True, contradictions: bool = True, quality: bool = True) -> list[dict]:
    alerts: list[dict] = []
    if emerging:
        for item in result.get("emerging_signals", []):
            if float(item.get("confidence", 0)) >= 65:
                title = str(item.get("title", ""))
                alerts.append({"kind": "emerging_signal", "title": title, "message": f"High-confidence emerging signal: {title}", "confidence": item.get("confidence", 0)})
    if rising:
        for signal in result.get("time_series", {}).get("signals", []):
            if signal.get("direction") in {"rising", "new"} and int(signal.get("total", 0)) >= 2:
                tag = str(signal.get("tag", ""))
                alerts.append({"kind": "rising_signal", "title": tag, "message": f"Rising time-series signal: {tag} ({signal.get('before')} -> {signal.get('recent')})"})
    if contradictions:
        for item in result.get("contradictions", []):
            title = str(item.get("topic", "Contradiction"))
            alerts.append({"kind": "contradiction", "title": title, "message": f"Contradictory evidence: {title}"})
    if quality:
        data = result.get("data_quality", {})
        if data.get("coverage_note") == "limited" or float(data.get("duplicate_rate", 0)) >= 0.45 or int(data.get("independent_domain_count", 0)) < 2:
            alerts.append({"kind": "data_quality", "title": "Data quality", "message": "Data-quality caution: limited coverage, low source diversity, or high duplication."})
    for alert in alerts:
        alert["id"] = _key(alert["kind"], alert["title"])
    return alerts


def save_new_alerts(topic_dir: Path, alerts: list[dict]) -> list[dict]:
    """Persist active alerts and return only alerts not already shown."""
    path = topic_dir / "_analysis_alerts.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    previous_ids = set(previous.get("active_ids", []))
    new_alerts = [alert for alert in alerts if alert["id"] not in previous_ids]
    path.write_text(json.dumps({
        "updated_at": datetime.now().astimezone().isoformat(),
        "active_ids": [alert["id"] for alert in alerts],
        "alerts": alerts,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return new_alerts
