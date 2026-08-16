"""X API v2를 통한 공개 게시물 수집기."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests


class XCrawler:
    SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
    VALIDATION_URL = "https://api.x.com/2/users/by/username/xdevelopers"

    def __init__(self, bearer_token: str = "", timeout: int = 10) -> None:
        self.bearer_token = bearer_token.strip()
        self.timeout = timeout
        self.session = requests.Session()

    @classmethod
    def from_environment(cls, timeout: int = 10) -> "XCrawler":
        return cls(os.environ.get("X_BEARER_TOKEN", ""), timeout=timeout)

    @property
    def is_configured(self) -> bool:
        return bool(self.bearer_token)

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
                "query": f"{topic} -is:retweet",
                "max_results": min(max(limit, 10), 100),
                "tweet.fields": "created_at,author_id,public_metrics",
                "expansions": "author_id",
                "user.fields": "username,name",
            }
            if window_start is not None:
                params["start_time"] = window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if window_end is not None:
                params["end_time"] = window_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            response = self.session.get(
                self.SEARCH_URL,
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"  ⚠️  '{topic}' X 검색 실패: {error}")
            return []

        payload = response.json()
        users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
        results: list[dict] = []
        for post in payload.get("data", []):
            text = (post.get("text") or "").strip()
            post_id = post.get("id")
            if not text or not post_id:
                continue
            author = users.get(post.get("author_id"), {})
            username = author.get("username", "unknown")
            results.append({
                "source": f"@{username}",
                "title": text[:160],
                "url": f"https://x.com/{username}/status/{post_id}",
                "summary": text,
                "date": post.get("created_at", ""),
                "kind": "gossip",
                "time_status": "known" if post.get("created_at") else "unknown",
                "platform": "x",
                "community": "X",
            })
            if len(results) >= limit:
                break
        return results

    def validate_connection(self) -> tuple[bool, str]:
        """Check Bearer Token access with a minimal public user lookup."""
        if not self.is_configured:
            return False, "credentials missing"
        try:
            response = self.session.get(
                self.VALIDATION_URL,
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            return False, f"authentication failed ({error})"
        return True, "connected"
