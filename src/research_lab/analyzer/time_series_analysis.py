"""Deterministic, bounded time-series evidence derived from raw snapshots."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from research_lab.tagging import tag_article
from research_lab.time_series import load_snapshots


def _snapshot_time(snapshot: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(snapshot.get("collected_at", "")))
    except ValueError:
        return None


def _article_id(article: dict) -> str:
    return str(article.get("article_id") or article.get("url") or f"{article.get('source', '')}|{article.get('title', '')}")


def _top(counter: Counter, limit: int = 10) -> list[dict]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def build_time_series_summary(topic_dir: Path, topic: str, period_days: int = 30, now: datetime | None = None) -> tuple[dict, str]:
    """Build a small evidence pack without an API call or Markdown scanning."""
    now = now or datetime.now().astimezone()
    period_days = max(7, min(365, int(period_days)))
    start = now - timedelta(days=period_days)
    selected = [snapshot for snapshot in load_snapshots(topic_dir) if (_snapshot_time(snapshot) or now) >= start]
    articles: dict[str, dict] = {}
    duplicate_count = 0
    for snapshot in selected:
        collected_at = _snapshot_time(snapshot) or now
        for raw in snapshot.get("articles", []) or []:
            article = tag_article(raw, topic)
            article["_snapshot_collected_at"] = collected_at.isoformat()
            identity = _article_id(article)
            if identity in articles:
                duplicate_count += 1
                continue
            articles[identity] = article

    rows = list(articles.values())
    midpoint = start + (now - start) / 2
    early_tags: Counter = Counter()
    recent_tags: Counter = Counter()
    all_tags: Counter = Counter()
    platforms: Counter = Counter()
    regions: Counter = Counter()
    domains: set[str] = set()
    time_unknown = 0
    for article in rows:
        tags = article.get("normalized_tags", []) or []
        all_tags.update(tags)
        article_time = _snapshot_time({"collected_at": article.get("_snapshot_collected_at", "")})
        target = recent_tags if article_time and article_time >= midpoint else early_tags
        target.update(tags)
        platforms[str(article.get("platform") or article.get("kind") or "unknown")] += 1
        region = str(article.get("rss_region") or article.get("source_region") or "unknown")
        regions[region] += 1
        host = urlparse(str(article.get("url", ""))).netloc.lower()
        if host:
            domains.add(host)
        if article.get("time_status") == "unknown":
            time_unknown += 1

    signal_rows: list[dict] = []
    early_total = max(1, sum(early_tags.values()))
    recent_total = max(1, sum(recent_tags.values()))
    for tag, total in all_tags.items():
        before, after = early_tags[tag], recent_tags[tag]
        ratio = ((after + 1) / recent_total) / ((before + 1) / early_total)
        if total < 2:
            direction = "new" if after else "stable"
        elif ratio >= 1.5:
            direction = "rising"
        elif ratio <= 0.67:
            direction = "falling"
        else:
            direction = "stable"
        signal_rows.append({"tag": tag, "direction": direction, "before": before, "recent": after, "change_ratio": round(ratio, 2), "total": total})
    signal_rows.sort(key=lambda row: (row["direction"] == "rising", row["direction"] == "new", row["total"], row["change_ratio"]), reverse=True)

    article_count = len(rows)
    quality = {
        "article_count": article_count,
        "snapshot_count": len(selected),
        "independent_domain_count": len(domains),
        "duplicate_article_count": duplicate_count,
        "duplicate_rate": round(duplicate_count / max(1, duplicate_count + article_count), 3),
        "time_unknown_count": time_unknown,
        "time_unknown_rate": round(time_unknown / max(1, article_count), 3),
        "platform_distribution": _top(platforms, 8),
        "region_distribution": _top(regions, 8),
        "coverage_note": "limited" if len(selected) < 2 else "usable",
    }
    summary = {
        "period_days": period_days,
        "period_start": start.date().isoformat(),
        "period_end": now.date().isoformat(),
        "signals": signal_rows[:12],
        "top_tags": _top(all_tags, 12),
        "data_quality": quality,
    }
    signature = hashlib.sha256(json.dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return summary, signature
