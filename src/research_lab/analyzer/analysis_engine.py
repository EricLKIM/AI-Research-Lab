"""Deterministic weighting layer for Analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from research_lab.analyzer.analysis_gpt import AnalysisGPTAnalyzer

SOURCE_RELIABILITY = {
    "official": 0.92,
    "news": 0.78,
    "academic": 0.90,
    "blog": 0.55,
    "gossip": 0.35,
    "forum": 0.30,
    "unknown": 0.45,
}

OFFICIAL_DOMAINS = (".gov", ".edu", "who.int", "un.org", "nasa.gov", "openai.com", "microsoft.com", "google.com", "nvidia.com")


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def freshness_score(date_value: str, now: datetime | None = None) -> float:
    """Smooth time decay; missing dates get a conservative mid-low score."""
    dt = _parse_date(date_value)
    if dt is None:
        return 0.55
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400)
    # Half-life about 30 days: recent sources matter more without making old research useless.
    return max(0.10, min(1.0, 0.5 ** (age_days / 30.0)))


def baseline_reliability(source: dict) -> float:
    kind = str(source.get("kind", "unknown")).lower()
    url = source.get("url", "")
    host = urlparse(url).netloc.lower()
    if any(host.endswith(d) or d in host for d in OFFICIAL_DOMAINS):
        return SOURCE_RELIABILITY["official"]
    if kind in SOURCE_RELIABILITY:
        return SOURCE_RELIABILITY[kind]
    return SOURCE_RELIABILITY["unknown"]


def prepare_sources(sources: list[dict]) -> list[dict]:
    prepared = []
    for s in sources:
        item = dict(s)
        item["freshness_score"] = freshness_score(str(item.get("date", "")))
        item["baseline_reliability"] = baseline_reliability(item)
        prepared.append(item)
    return prepared


def _independence_bonus(indices: list[int], sources: list[dict]) -> float:
    hosts = set()
    for i in indices:
        if 0 <= i < len(sources):
            host = urlparse(sources[i].get("url", "")).netloc.lower()
            if host:
                hosts.add(host)
    return min(1.0, 0.65 + 0.10 * max(0, len(hosts) - 1))


def apply_weights(gpt_result, sources: list[dict], reliability_weight: float = 0.5, freshness_weight: float = 0.3, early_signal_weight: float = 0.2) -> dict:
    assessments = {int(a.get("index", -1)): a for a in gpt_result.source_assessments if str(a.get("index", "")).isdigit()}
    source_rows = []
    for i, s in enumerate(sources):
        a = assessments.get(i, {})
        r = max(0.0, min(1.0, float(a.get("reliability", s.get("baseline_reliability", 0.45))) / 100))
        e = max(0.0, min(1.0, float(a.get("evidence", 50)) / 100))
        f = float(s.get("freshness_score", 0.55))
        # User controls change influence, not truth. Normalize configured weights.
        denom = max(0.001, reliability_weight + freshness_weight + early_signal_weight)
        base = (reliability_weight * r + freshness_weight * f + early_signal_weight * e) / denom
        kind = s.get("kind", "news")
        if kind == "gossip":
            base *= 0.85  # gossip remains useful as a signal, but is not allowed to dominate confirmed evidence.
        source_rows.append({**s, "reliability_score": round(r * 100, 1), "evidence_score": round(e * 100, 1), "weight": round(base, 4), "reliability_reason": a.get("reason", "")})

    def finalize(items: list[dict], category: str) -> list[dict]:
        out = []
        for item in items:
            indices = [int(x) for x in item.get("source_indices", []) if str(x).isdigit() and 0 <= int(x) < len(source_rows)]
            if not indices:
                continue
            weights = [source_rows[i]["weight"] for i in indices]
            independent = _independence_bonus(indices, source_rows)
            support = sum(weights) / max(1, len(weights))
            confidence = min(100.0, max(0.0, support * independent * 100))
            tag_rows = []
            for tag in item.get("tags", []):
                tag_rows.append({"tag": str(tag), "confidence": round(confidence, 1), "weight": round(support, 4), "fresh": round(sum(source_rows[i]["freshness_score"] for i in indices) / len(indices), 3)})
            out.append({**item, "category": category, "confidence": round(confidence, 1), "weight": round(support, 4), "independent_sources": len(set(urlparse(source_rows[i].get("url", "")).netloc.lower() for i in indices)), "tags": tag_rows, "source_indices": indices})
        return out

    return {
        "sources": source_rows,
        "confirmed_trends": finalize(gpt_result.confirmed_trends, "Confirmed Trend"),
        "emerging_signals": finalize(gpt_result.emerging_signals, "Emerging Signal"),
        "rumors": finalize(gpt_result.rumors, "Rumor"),
        "contradictions": gpt_result.contradictions,
        "overall_summary": gpt_result.overall_summary,
        "weights": {"reliability": reliability_weight, "freshness": freshness_weight, "early_signal": early_signal_weight},
    }
