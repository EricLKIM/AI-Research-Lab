"""Small, deterministic tag extraction used by collection and analysis.

The vocabulary deliberately starts conservatively.  Raw terms are retained so a
later vocabulary update can be applied without downloading articles again.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

TAGGING_VERSION = 1

ALIASES = {
    "nvidia": ("nvidia", "nvda", "엔비디아"),
    "tsmc": ("tsmc", "taiwan semiconductor", "대만반도체"),
    "semiconductor": ("semiconductor", "semiconductors", "chip", "chips", "반도체"),
    "ai": ("artificial intelligence", "generative ai", " ai ", "인공지능", "생성형 ai"),
    "ai_gpu": ("ai gpu", "gpu", "graphics processing unit"),
    "datacenter": ("data center", "datacentre", "데이터센터"),
    "cloud": ("cloud computing", "cloud service", "클라우드"),
    "openai": ("openai", "chatgpt"),
    "microsoft": ("microsoft", "msft", "마이크로소프트"),
    "google": ("google", "alphabet", "구글"),
    "china": ("china", "chinese", "중국"),
    "interest_rates": ("interest rate", "fed rate", "금리"),
    "real_estate": ("real estate", "housing market", "부동산"),
}

PARENTS = {
    "nvidia": ("semiconductor", "technology"),
    "tsmc": ("semiconductor", "technology"),
    "semiconductor": ("technology",),
    "ai_gpu": ("ai", "semiconductor", "technology"),
    "ai": ("technology",),
    "datacenter": ("ai", "technology"),
    "cloud": ("technology",),
    "openai": ("ai", "technology"),
    "microsoft": ("technology",),
    "google": ("technology",),
    "real_estate": ("economy",),
    "interest_rates": ("economy",),
}

_dictionary_cache: tuple[Path, float, dict] | None = None


def dictionary_path() -> Path:
    """The editable dictionary lives with machine-readable research data."""
    configured = os.environ.get("AI_RESEARCH_LAB_DATA_HOME")
    if configured:
        return Path(configured) / "vault" / "tag_dictionary.json"
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "AI Research Lab" / "vault" / "tag_dictionary.json"
    return Path.cwd() / "vault" / "tag_dictionary.json"


def _custom_dictionary() -> dict:
    global _dictionary_cache
    path = dictionary_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _dictionary_cache and _dictionary_cache[:2] == (path, mtime):
        return _dictionary_cache[2]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        value = value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        value = {}
    _dictionary_cache = (path, mtime, value)
    return value


def _aliases() -> dict[str, tuple[str, ...]]:
    merged = dict(ALIASES)
    custom = _custom_dictionary().get("aliases", {})
    if isinstance(custom, dict):
        for canonical, values in custom.items():
            key = _clean(canonical).replace(" ", "_")
            if not key or not isinstance(values, list):
                continue
            merged[key] = tuple(str(value) for value in values if str(value).strip())
    return merged


def _parents() -> dict[str, tuple[str, ...]]:
    merged = dict(PARENTS)
    custom = _custom_dictionary().get("parents", {})
    if isinstance(custom, dict):
        for canonical, values in custom.items():
            key = _clean(canonical).replace(" ", "_")
            if key and isinstance(values, list):
                merged[key] = tuple(_clean(value).replace(" ", "_") for value in values if _clean(value))
    return merged


def _clean(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def normalize_tag(value: object) -> str:
    """Return a stable tag, including known aliases, or an empty value."""
    cleaned = _clean(value).strip("#.,;:!?()[]{}\"'")
    if not cleaned:
        return ""
    padded = f" {cleaned} "
    for canonical, aliases in _aliases().items():
        if cleaned == canonical or any(alias in cleaned if " " in alias else f" {alias} " in padded for alias in aliases):
            return canonical
    # Keep short, meaningful topic labels without making every title word a tag.
    cleaned = re.sub(r"[^\w가-힣+-]+", "_", cleaned, flags=re.UNICODE).strip("_")
    return cleaned[:64] if len(cleaned) >= 2 else ""


def hierarchy_for(tags: Iterable[str]) -> list[str]:
    parents: set[str] = set()
    for tag in tags:
        parents.update(_parents().get(tag, ()))
    return sorted(parents)


def tag_article(article: dict, topic: str = "") -> dict:
    """Return an article copy annotated with raw, normalized and parent tags."""
    item = dict(article)
    text = " ".join(str(item.get(field, "")) for field in ("title", "summary", "source"))
    lowered = f" {text.casefold()} "
    raw: list[str] = []
    normalized: set[str] = set()
    for canonical, aliases in _aliases().items():
        for alias in aliases:
            if alias.casefold() in lowered:
                raw.append(alias)
                normalized.add(canonical)
                break
    topic_tag = normalize_tag(topic)
    if topic_tag:
        raw.append(str(topic))
        normalized.add(topic_tag)
    # Preserve collector-provided tags if a source adds them in the future.
    for tag in item.get("normalized_tags", []) or []:
        normalized_tag = normalize_tag(tag)
        if normalized_tag:
            normalized.add(normalized_tag)
    item["raw_tags"] = sorted(set(raw), key=str.casefold)
    item["normalized_tags"] = sorted(normalized)
    item["hierarchical_tags"] = hierarchy_for(normalized)
    item["tagging_version"] = TAGGING_VERSION
    return item


def tag_articles(articles: Iterable[dict], topic: str = "") -> list[dict]:
    return [tag_article(article, topic) for article in articles]
