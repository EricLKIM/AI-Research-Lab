"""YouTube Data API를 통한 최신 영상 기반 커뮤니티 신호 수집기."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests


class YouTubeCrawler:
    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VALIDATION_URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(self, api_key: str = "", timeout: int = 10) -> None:
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = requests.Session()

    @classmethod
    def from_environment(cls, timeout: int = 10) -> "YouTubeCrawler":
        return cls(os.environ.get("YOUTUBE_API_KEY", ""), timeout=timeout)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch(
        self,
        topic: str,
        limit: int,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[dict]:
        if not self.is_configured or limit <= 0:
            return []
        try:
            params = {
                "key": self.api_key,
                "part": "snippet",
                "q": topic,
                "type": "video",
                "order": "date",
                "maxResults": min(limit, 50),
            }
            if window_start is not None:
                params["publishedAfter"] = window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if window_end is not None:
                params["publishedBefore"] = window_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            response = self.session.get(
                self.SEARCH_URL,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"  ⚠️  '{topic}' YouTube 검색 실패: {error}")
            return []

        results: list[dict] = []
        for item in response.json().get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            title = (snippet.get("title") or "").strip()
            if not video_id or not title:
                continue
            channel = (snippet.get("channelTitle") or "YouTube").strip()
            published_at = snippet.get("publishedAt", "")
            results.append({
                "source": channel,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "summary": (snippet.get("description") or "").strip(),
                "date": published_at,
                "kind": "gossip",
                "time_status": "known" if published_at else "unknown",
                "platform": "youtube",
                "community": channel,
            })
            if len(results) >= limit:
                break
        return results

    def validate_connection(self) -> tuple[bool, str]:
        """Check the API key with one low-cost video lookup (1 quota unit)."""
        if not self.is_configured:
            return False, "credentials missing"
        try:
            response = self.session.get(
                self.VALIDATION_URL,
                params={"key": self.api_key, "part": "id", "id": "dQw4w9WgXcQ"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            return False, f"authentication failed ({error})"
        return True, "connected (1 YouTube quota unit used)"
