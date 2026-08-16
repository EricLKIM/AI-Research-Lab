"""Reddit Data API를 통한 커뮤니티성 자료 수집기."""
from __future__ import annotations

import os
from datetime import UTC, datetime

import requests


class RedditCrawler:
    """승인된 OAuth 자격 증명이 있을 때만 Reddit Data API를 호출한다."""

    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    SEARCH_URL = "https://oauth.reddit.com/search"

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        user_agent: str = "",
        timeout: int = 10,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.user_agent = user_agent.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self._access_token: str | None = None

    @classmethod
    def from_environment(cls, timeout: int = 10) -> "RedditCrawler":
        return cls(
            client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
            user_agent=os.environ.get("REDDIT_USER_AGENT", ""),
            timeout=timeout,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.user_agent)

    def fetch(self, topic: str, limit: int, **_ignored: object) -> list[dict]:
        """주제와 관련된 최신 공개 게시물을 커뮤니티 자료로 반환한다."""
        if not self.is_configured or limit <= 0:
            return []

        try:
            token = self._get_access_token()
            response = self.session.get(
                self.SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": self.user_agent,
                },
                params={
                    "q": topic,
                    "sort": "new",
                    "t": "all",
                    "limit": min(limit, 100),
                    "raw_json": 1,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"  ⚠️  '{topic}' Reddit 검색 실패: {error}")
            return []

        results: list[dict] = []
        for child in response.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            title = (post.get("title") or "").strip()
            permalink = (post.get("permalink") or "").strip()
            if not title or not permalink:
                continue

            created_utc = post.get("created_utc")
            date = ""
            if isinstance(created_utc, (int, float)):
                date = datetime.fromtimestamp(created_utc, tz=UTC).isoformat()

            subreddit = (post.get("subreddit_name_prefixed") or "Reddit").strip()
            results.append({
                "source": subreddit,
                "title": title,
                "url": f"https://www.reddit.com{permalink}",
                "summary": (post.get("selftext") or "").strip(),
                "date": date,
                "kind": "gossip",
                "time_status": "known" if date else "unknown",
                "platform": "reddit",
                "community": subreddit,
            })
            if len(results) >= limit:
                break
        return results

    def validate_connection(self) -> tuple[bool, str]:
        """Validate OAuth credentials without collecting Reddit content."""
        if not self.is_configured:
            return False, "credentials missing"
        try:
            self._get_access_token()
        except requests.RequestException as error:
            return False, f"authentication failed ({error})"
        return True, "connected"

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        response = self.session.post(
            self.TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            headers={"User-Agent": self.user_agent},
            data={"grant_type": "client_credentials"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise requests.RequestException("Reddit OAuth 응답에 access_token이 없습니다.")
        self._access_token = token
        return token
