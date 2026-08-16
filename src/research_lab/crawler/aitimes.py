"""
aitimes.py

AI Times (https://www.aitimes.com/) 최신 기사 크롤러.

반환 형식:
    [
        {
            "title": "기사 제목",
            "url": "https://...",
            "summary": "요약 또는 리드 문장",
            "date": "2026-07-25",
            "category": "카테고리",
        },
        ...
    ]
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.aitimes.com"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


@dataclass
class Article:
    title: str
    url: str
    summary: str = ""
    date: str = ""
    category: str = ""

    def to_dict(self) -> dict:
        return {
            "source": "AI Times",
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "date": self.date,
            "category": self.category,
        }


class AITimesCrawler:
    """
    AI Times 최신 기사 크롤러.

    사용 예:
        crawler = AITimesCrawler()
        articles = crawler.fetch(limit=5)
    """

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, limit: int = 5) -> list[dict]:
        """최신 기사를 limit개 크롤링해서 반환한다."""
        try:
            resp = self.session.get(BASE_URL, timeout=self.timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"  ⚠️  AI Times 접속 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []

        # AI Times article lists usually use <section class="article-list"> or <ul class="type"> <li> elements.
        # Try several selectors to tolerate layout changes.
        candidates = (
            soup.select("section.article-list li")
            or soup.select("ul.type li")
            or soup.select("div#section-list li")
            or soup.select("li.item")
            or soup.select("article")
        )

        for item in candidates[:limit * 2]:  # Parse extra candidates before applying the final limit.
            article = self._parse_item(item)
            if article and article.title:
                articles.append(article.to_dict())
            if len(articles) >= limit:
                break

        # Fall back to direct extraction from anchor elements.
        if not articles:
            articles = self._fallback_parse(soup, limit)

        return articles[:limit]

    def _parse_item(self, item) -> Article | None:
        """개별 li/article 요소에서 기사 정보 추출."""
        a_tag = item.find("a", href=True)
        if not a_tag:
            return None

        href = a_tag.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href

        # Title
        title_tag = item.find(["h4", "h3", "h2", "strong", "span"])
        title = (title_tag.get_text(strip=True) if title_tag
                 else a_tag.get_text(strip=True))
        if not title or len(title) < 5:
            return None

        # Summary
        summary_tag = item.find("p")
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        # Date
        date_tag = item.find(["time", "span"], class_=re.compile(r"date|time|ago", re.I))
        date = date_tag.get_text(strip=True) if date_tag else ""

        # Category
        cat_tag = item.find(["em", "span"], class_=re.compile(r"cat|section|tag", re.I))
        category = cat_tag.get_text(strip=True) if cat_tag else ""

        return Article(title=title, url=url, summary=summary, date=date, category=category)

    def _fallback_parse(self, soup: BeautifulSoup, limit: int) -> list[dict]:
        """셀렉터 실패 시 모든 <a> 태그에서 기사 링크 추출."""
        articles = []
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            # AI Times article URL pattern: /news/articleView.html?idxno=...
            if "articleView" not in href and "news" not in href:
                continue
            url = href if href.startswith("http") else BASE_URL + href
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            articles.append({
                "source": "AI Times",
                "title": title,
                "url": url,
                "summary": "",
                "date": datetime.today().strftime("%Y-%m-%d"),
                "category": "",
            })

            if len(articles) >= limit:
                break

        return articles
