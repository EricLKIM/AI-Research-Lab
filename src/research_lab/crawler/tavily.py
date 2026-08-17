"""Optional Tavily social-media source used for latest gossip discovery."""
from __future__ import annotations

import asyncio
import inspect
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


class TavilySocialCrawler:
    """Search public social discussions through Tavily's Agent Toolkit.

    This is deliberately a latest-research source only. Tavily's relative time
    filters are useful for discovery, but are not a reproducible historical
    source for GDELT-style backfill.
    """

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key.strip()

    @classmethod
    def from_environment(cls) -> "TavilySocialCrawler":
        return cls(os.environ.get("TAVILY_API_KEY", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch(self, topic: str, limit: int, **_ignored: object) -> list[dict]:
        if not self.is_configured or limit <= 0:
            return []

        try:
            from tavily_agent_toolkit import social_media_search
        except ImportError:
            print("  [Warning] Tavily Social is enabled, but tavily-agent-toolkit is unavailable.")
            return []

        try:
            response = social_media_search(
                query=topic,
                api_key=self.api_key,
                platform="combined",
                max_results=min(limit, 20),
                time_range="week",
                include_raw_content=False,
            )
            if inspect.isawaitable(response):
                response = asyncio.run(response)
        except Exception as error:  # The optional toolkit owns its HTTP client and error types.
            print(f"  [Warning] Tavily Social search failed for '{topic}': {error}")
            return []

        items = self._result_items(response)
        results: list[dict] = []
        seen_urls: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "").strip()
            if not url or url in seen_urls:
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            summary = str(
                item.get("content") or item.get("snippet") or item.get("summary") or ""
            ).strip()
            if not title:
                title = summary[:160].strip()
            if not title:
                continue
            date = self._date_value(item)
            platform = self._platform(item, url)
            results.append({
                "source": str(item.get("source") or platform.title() or "Tavily Social").strip(),
                "title": title,
                "url": url,
                "summary": summary,
                "date": date,
                "kind": "gossip",
                "time_status": "known" if date else "unknown",
                "platform": platform,
                "community": platform.title() if platform else "Tavily Social",
            })
            seen_urls.add(url)
            if len(results) >= limit:
                break
        return results

    def validate_connection(self) -> tuple[bool, str]:
        if not self.is_configured:
            return False, "credentials missing"
        try:
            import tavily_agent_toolkit  # noqa: F401
        except ImportError:
            return False, "tavily-agent-toolkit missing"
        return True, "configured (used for gossip collection)"

    @staticmethod
    def _result_items(response: Any) -> list[Any]:
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in ("results", "sources", "data"):
                value = response.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _date_value(item: dict) -> str:
        value = item.get("published_date") or item.get("published_at") or item.get("date")
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC).isoformat()
        return str(value or "").strip()

    @staticmethod
    def _platform(item: dict, url: str) -> str:
        platform = str(item.get("platform") or "").strip().lower()
        if platform:
            return platform
        host = urlparse(url).netloc.lower()
        if "reddit.com" in host:
            return "reddit"
        if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            return "x"
        return "tavily"
