"""AI·반도체 관련 초기 기술 신호를 위한 Hacker News 수집기."""
from __future__ import annotations

from datetime import UTC, datetime

import requests


class HackerNewsCrawler:
    NEW_STORIES_URL = "https://hacker-news.firebaseio.com/v0/newstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
    VALIDATION_URL = "https://hacker-news.firebaseio.com/v0/maxitem.json"
    TOPIC_TERMS = (
        "ai", "artificial intelligence", "machine learning", "llm", "openai",
        "semiconductor", "semiconductors", "chip", "chips", "반도체", "인공지능",
    )

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return True

    @classmethod
    def supports_topic(cls, topic: str) -> bool:
        normalized = topic.casefold()
        return any(term in normalized for term in cls.TOPIC_TERMS)

    def fetch(self, topic: str, limit: int, **_ignored: object) -> list[dict]:
        if limit <= 0 or not self.supports_topic(topic):
            return []
        try:
            response = self.session.get(self.NEW_STORIES_URL, timeout=self.timeout)
            response.raise_for_status()
            story_ids = response.json()[:100]
        except requests.RequestException as error:
            print(f"  ⚠️  Hacker News 최신 글 조회 실패: {error}")
            return []

        terms = [term for term in topic.casefold().split() if len(term) > 1]
        results: list[dict] = []
        for story_id in story_ids:
            try:
                response = self.session.get(self.ITEM_URL.format(item_id=story_id), timeout=self.timeout)
                response.raise_for_status()
                story = response.json()
            except requests.RequestException:
                continue
            if not story or story.get("type") != "story":
                continue
            title = (story.get("title") or "").strip()
            text = (story.get("text") or "").strip()
            if not any(term in f"{title} {text}".casefold() for term in terms):
                continue
            timestamp = story.get("time")
            date = datetime.fromtimestamp(timestamp, tz=UTC).isoformat() if isinstance(timestamp, int) else ""
            story_id = story.get("id")
            results.append({
                "source": "Hacker News",
                "title": title,
                "url": f"https://news.ycombinator.com/item?id={story_id}",
                "summary": text,
                "date": date,
                "kind": "gossip",
                "time_status": "known" if date else "unknown",
                "platform": "hackernews",
                "community": "Hacker News",
            })
            if len(results) >= limit:
                break
        return results

    def validate_connection(self) -> tuple[bool, str]:
        """Check Hacker News public API availability without an API key."""
        try:
            response = self.session.get(self.VALIDATION_URL, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as error:
            return False, f"connection failed ({error})"
        return True, "connected (no API key required)"
