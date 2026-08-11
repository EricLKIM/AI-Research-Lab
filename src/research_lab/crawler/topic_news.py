"""주제별 Google 검색/Google News 크롤러.

검색 언어/지역은 출력 언어 설정에 맞춰 Google의 hl/gl/lr로 지정한다.
가십 비율이 높을수록 일반 뉴스 대신 Google Web Search에서 블로그/개인 의견/
커뮤니티/토론/게시판 성격의 결과를 더 많이 수집한다.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}

GOSSIP_TERMS = {
    "ko": '(블로그 OR "개인 의견" OR 커뮤니티 OR 게시판 OR 후기 OR 썰 OR "뒷이야기")',
    "en": '(blog OR "personal opinion" OR reddit OR forum OR discussion OR gossip)',
    "ja": '(ブログ OR "個人ブログ" OR 意見 OR 掲示板 OR 口コミ OR 噂)',
    "zh-CN": '(博客 OR "个人观点" OR 论坛 OR 社区 OR 爆料 OR 八卦 OR 讨论)',
    "es": '(blog OR "opinión personal" OR foro OR discusión OR rumores OR cotilleo)',
    "fr": '(blog OR "avis personnel" OR forum OR discussion OR rumeur OR potins)',
    "de": '(Blog OR "persönliche Meinung" OR Forum OR Diskussion OR Gerüchte OR Klatsch)',
    "vi": '(blog OR "ý kiến cá nhân" OR diễn đàn OR thảo luận OR tin đồn)',
}

# 개인/커뮤니티성 자료를 우선하는 도메인. "가십"은 사실이라고 간주하지 않고
# 단지 정보의 성격을 바꾸는 검색 신호로만 사용한다.
GOSSIP_SITES = [
    "reddit.com", "medium.com", "substack.com", "blogspot.com",
    "wordpress.com", "quora.com",
]


@dataclass
class TopicArticle:
    title: str
    url: str
    summary: str = ""
    date: str = ""
    source: str = ""
    kind: str = "news"

    def to_dict(self) -> dict:
        return {
            "source": self.source or "Google News",
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "date": self.date,
            "kind": self.kind,
        }


class TopicNewsCrawler:
    RSS_URL = "https://news.google.com/rss/search"
    WEB_URL = "https://www.google.com/search"

    def __init__(self, timeout: int = 10, lang: str = "ko", country: str = "KR", lr: str | None = None,
                 gossip_ratio: int = 0) -> None:
        self.timeout = timeout
        self.lang = lang
        self.country = country
        self.lr = lr or f"lang_{lang.split('-')[0]}"
        self.gossip_ratio = max(0, min(100, int(gossip_ratio)))
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, topic: str, limit: int = 10) -> list[dict]:
        topic = (topic or "").strip()
        if not topic:
            return []

        gossip_n = round(limit * self.gossip_ratio / 100)
        news_n = limit - gossip_n
        results: list[dict] = []

        if news_n:
            results.extend(self._fetch_news(topic, news_n))
        if gossip_n:
            results.extend(self._fetch_gossip(topic, gossip_n))

        # 한 소스가 부족하면 다른 소스로 자동 보충한다. 중복 URL은 제거한다.
        if len(results) < limit:
            existing = {a["url"] for a in results}
            if news_n:
                extra = self._fetch_gossip(topic, limit - len(results))
            else:
                extra = self._fetch_news(topic, limit - len(results))
            for a in extra:
                if a["url"] not in existing:
                    results.append(a)
                    existing.add(a["url"])
                if len(results) >= limit:
                    break

        return results[:limit]

    def _fetch_news(self, topic: str, limit: int) -> list[dict]:
        params = {
            "q": topic,
            "hl": self.lang,
            "gl": self.country,
            "ceid": f"{self.country}:{self.lang}",
        }
        try:
            resp = self.session.get(self.RSS_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"  ⚠️  '{topic}' Google News 검색 실패: {e}")
            return []

        articles: list[dict] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            description = (item.findtext("description") or "").strip()
            if not title or not link:
                continue
            articles.append(TopicArticle(title, link, self._clean_description(description), pub_date, source, "news").to_dict())
            if len(articles) >= limit:
                break
        return articles

    def _fetch_gossip(self, topic: str, limit: int) -> list[dict]:
        lang_key = self.lang if self.lang in GOSSIP_TERMS else self.lang.split("-")[0]
        terms = GOSSIP_TERMS.get(lang_key, GOSSIP_TERMS["en"])
        sites = " OR ".join(f"site:{site}" for site in GOSSIP_SITES)
        query = f"{topic} {terms} ({sites})"
        params = {
            "q": query,
            "hl": self.lang,
            "gl": self.country,
            "lr": self.lr,
            "num": min(max(limit * 2, 10), 20),
            "filter": "0",
            "pws": "0",
        }
        try:
            resp = self.session.get(self.WEB_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠️  '{topic}' Google Web Search(가십) 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []
        seen: set[str] = set()
        for block in soup.select("div.MjjYud, div.g"):
            h3 = block.find("h3")
            a = h3.find_parent("a") if h3 else None
            if not a or not a.get("href"):
                continue
            url = self._unwrap_google_url(a.get("href", ""))
            if not url or "google." in urlparse(url).netloc or url in seen:
                continue
            title = h3.get_text(" ", strip=True)
            snippet_el = block.select_one("div.VwiC3b, div[data-sncf]")
            summary = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if not title:
                continue
            seen.add(url)
            results.append(TopicArticle(title, url, summary, "", urlparse(url).netloc, "gossip").to_dict())
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _unwrap_google_url(url: str) -> str:
        if url.startswith("/url?"):
            q = parse_qs(urlparse(url).query).get("q", [])
            if q:
                return q[0]
        return html.unescape(url)

    @staticmethod
    def _clean_description(value: str) -> str:
        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
