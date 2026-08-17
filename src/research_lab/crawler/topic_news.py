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
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from research_lab.crawler.hacker_news import HackerNewsCrawler
from research_lab.crawler.gdelt import GdeltCrawler
from research_lab.crawler.reddit import RedditCrawler
from research_lab.crawler.tavily import TavilySocialCrawler
from research_lab.crawler.x import XCrawler
from research_lab.crawler.youtube import YouTubeCrawler

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

        # Domains that favor personal or community material.  Gossip is never
        # treated as fact; it only changes the type of signal being collected.
GOSSIP_SITES = [
    "reddit.com", "medium.com", "substack.com", "blogspot.com",
    "wordpress.com", "quora.com",
]

RSS_REGION_PROFILES = {
    "KR": (("ko", "KR", 0.50), ("en", "US", 0.20), ("zh-CN", "CN", 0.15), ("ja", "JP", 0.10), ("en", "GB", 0.05)),
    "US": (("en", "US", 0.50), ("en", "GB", 0.20), ("zh-CN", "CN", 0.15), ("ja", "JP", 0.10), ("ko", "KR", 0.05)),
    "CN": (("zh-CN", "CN", 0.50), ("en", "US", 0.20), ("ko", "KR", 0.15), ("ja", "JP", 0.10), ("en", "GB", 0.05)),
    "JP": (("ja", "JP", 0.50), ("en", "US", 0.20), ("zh-CN", "CN", 0.15), ("ko", "KR", 0.10), ("en", "GB", 0.05)),
}


@dataclass
class TopicArticle:
    title: str
    url: str
    summary: str = ""
    date: str = ""
    source: str = ""
    kind: str = "news"
    time_status: str = "unknown"
    platform: str = ""
    community: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source or "Google News",
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "date": self.date,
            "kind": self.kind,
            "time_status": self.time_status,
            "platform": self.platform,
            "community": self.community,
        }


class TopicNewsCrawler:
    RSS_URL = "https://news.google.com/rss/search"
    WEB_URL = "https://www.google.com/search"

    def __init__(self, timeout: int = 10, lang: str = "ko", country: str = "KR", lr: str | None = None,
                 gossip_ratio: int = 0, gossip_mode: str = "best-effort",
                 include_time_unknown: bool = False,
                 allow_google_gossip_fallback: bool = True,
                 community_sources: set[str] | None = None,
                 tavily_crawler: TavilySocialCrawler | None = None,
                 reddit_crawler: RedditCrawler | None = None,
                 x_crawler: XCrawler | None = None,
                 youtube_crawler: YouTubeCrawler | None = None,
                 hacker_news_crawler: HackerNewsCrawler | None = None,
                 gdelt_crawler: GdeltCrawler | None = None,
                 gdelt_source_language: str = "global",
                 gdelt_region_profile: str = "auto",
                 latest_news_priority: str = "google_rss",
                 google_rss_region_profile: str = "balanced",
                 allow_google_news: bool = True) -> None:
        self.timeout = timeout
        self.lang = lang
        self.country = country
        self.lr = lr or f"lang_{lang.split('-')[0]}"
        self.gossip_ratio = max(0, min(100, int(gossip_ratio)))
        self.gossip_mode = gossip_mode if gossip_mode in {"best-effort", "strict"} else "best-effort"
        self.include_time_unknown = include_time_unknown
        self.allow_google_gossip_fallback = allow_google_gossip_fallback
        self.allow_google_news = allow_google_news
        self.latest_news_priority = (
            latest_news_priority if latest_news_priority in {"google_rss", "gdelt"} else "google_rss"
        )
        self.google_rss_region_profile = (
            google_rss_region_profile if google_rss_region_profile in {"balanced", "local_only"} else "balanced"
        )
        self.last_time_unknown_articles: list[dict] = []
        self.community_sources = (
            community_sources
            if community_sources is not None
            else {"reddit", "x", "youtube"}
        )
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.tavily_crawler = tavily_crawler or TavilySocialCrawler.from_environment()
        self.reddit_crawler = reddit_crawler or RedditCrawler.from_environment(timeout=timeout)
        self.x_crawler = x_crawler or XCrawler.from_environment(timeout=timeout)
        self.youtube_crawler = youtube_crawler or YouTubeCrawler.from_environment(timeout=timeout)
        self.hacker_news_crawler = hacker_news_crawler or HackerNewsCrawler(timeout=timeout)
        self.gdelt_crawler = gdelt_crawler or GdeltCrawler(
            source_language=gdelt_source_language,
            region_profile=(
                "country_focus" if gdelt_region_profile == "auto" else gdelt_region_profile
            ),
            target_country=self.country,
            timeout=max(timeout, 30),
        )

    def get_community_source_status(self, topic: str) -> list[dict[str, str]]:
        """Return the effective community-source state for a topic without calling APIs."""
        sources = [
            ("tavily", self.tavily_crawler.is_configured, True),
            ("reddit", self.reddit_crawler.is_configured, True),
            ("x", self.x_crawler.is_configured, True),
            ("youtube", self.youtube_crawler.is_configured, True),
            ("hackernews", True, self.hacker_news_crawler.supports_topic(topic)),
            ("gdelt", self.gdelt_crawler.is_configured, True),
        ]
        statuses: list[dict[str, str]] = []
        for name, configured, eligible in sources:
            if name not in self.community_sources:
                state = "disabled"
            elif not eligible:
                state = "not_applicable"
            elif not configured:
                state = "credentials_missing"
            else:
                state = "ready"
            statuses.append({"source": name, "state": state})
        return statuses

    def fetch(
        self,
        topic: str,
        limit: int = 10,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[dict]:
        topic = (topic or "").strip()
        if not topic:
            return []

        # Collect more than the requested limit because time-window filtering is applied later.
        collection_limit = max(limit * 3, 30)

        gossip_n = round(collection_limit * self.gossip_ratio / 100)
        news_n = collection_limit - gossip_n

        results: list[dict] = []
        gdelt_results: list[dict] = []

        def fetch_google_news() -> list[dict]:
            return self._fetch_news(topic, news_n) if news_n and self.allow_google_news else []

        def fetch_gdelt() -> list[dict]:
            if "gdelt" not in self.community_sources:
                return []
            return self.gdelt_crawler.fetch(topic, collection_limit, window_start, window_end)

        if self.latest_news_priority == "google_rss":
            # Fast RSS is the default. Avoid a slow GDELT request entirely when
            # RSS already supplies the requested news allocation.
            results.extend(fetch_google_news())
            if len(results) < news_n:
                gdelt_results = fetch_gdelt()
                results.extend(gdelt_results)
        else:
            gdelt_results = fetch_gdelt() if news_n else []
            results.extend(gdelt_results)
            if len(gdelt_results) < news_n:
                results.extend(fetch_google_news())

        if gossip_n:
            if window_start is None and window_end is None:
                results.extend(self._fetch_gossip(topic, gossip_n))
            else:
                results.extend(self._fetch_gossip(topic, gossip_n, window_start, window_end))

        self.last_time_unknown_articles = [
            article for article in results
            if article.get("kind") == "gossip" and article.get("time_status") == "unknown"
        ]

        results = self._filter_by_time_window(
            results,
            window_start,
            window_end,
            include_time_unknown=self.include_time_unknown,
        )

        news_results = [
            article for article in results
            if article.get("kind") == "news"
        ]

        gossip_results = [
            article for article in results
            if article.get("kind") == "gossip"
        ]

        target_gossip_n = round(limit * self.gossip_ratio / 100)
        target_news_n = limit - target_gossip_n

        selected_news = news_results[:target_news_n]
        selected_gossip = gossip_results[:target_gossip_n]

        results = selected_news + selected_gossip

        if self.gossip_mode == "strict":
            return results

        # Fill shortages in one category with the other category.
        if len(results) < limit:
            selected_urls = {article["url"] for article in results}

            for article in news_results + gossip_results:
                if article["url"] in selected_urls:
                    continue

                results.append(article)
                selected_urls.add(article["url"])

                if len(results) >= limit:
                    break

        results = results[:limit]

        # Fill source shortages automatically from other sources and deduplicate URLs.
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
        if self.google_rss_region_profile == "local_only":
            return self._fetch_news_region(topic, limit, self.lang, self.country)

        regions = RSS_REGION_PROFILES.get(
            self.country,
            ((self.lang, self.country, 0.50), ("en", "US", 0.20), ("zh-CN", "CN", 0.15), ("ja", "JP", 0.10), ("en", "GB", 0.05)),
        )
        quotas = [max(1, int(limit * share)) for _, _, share in regions] if limit >= len(regions) else [int(limit * share) for _, _, share in regions]
        while sum(quotas) > limit:
            largest = max(range(len(quotas)), key=quotas.__getitem__)
            if quotas[largest] <= 1:
                break
            quotas[largest] -= 1
        for index in range(limit - sum(quotas)):
            quotas[index % len(quotas)] += 1
        regional_candidates: list[list[dict]] = []
        for (lang, country, _share), quota in zip(regions, quotas):
            if quota <= 0:
                regional_candidates.append([])
                continue
            # Ask for a little surplus because syndicated articles often appear
            # in several national editions and are removed by URL de-duplication.
            candidates: list[dict] = []
            for article in self._fetch_news_region(topic, max(quota * 2, 3), lang, country):
                item = dict(article)
                item["rss_region"] = country
                candidates.append(item)
            regional_candidates.append(candidates)

        # Interleave regions by their requested share. Returning one country
        # batch at a time made the final top-N selection look entirely US-only.
        results: list[dict] = []
        seen_urls: set[str] = set()
        positions = [0] * len(regional_candidates)
        selected_per_region = [0] * len(regional_candidates)
        total_quota = max(1, sum(quotas))
        while len(results) < limit:
            eligible: list[int] = []
            for index, candidates in enumerate(regional_candidates):
                while positions[index] < len(candidates) and candidates[positions[index]]["url"] in seen_urls:
                    positions[index] += 1
                if positions[index] < len(candidates):
                    eligible.append(index)
            if not eligible:
                break
            index = max(
                eligible,
                key=lambda item: quotas[item] * (len(results) + 1) / total_quota - selected_per_region[item],
            )
            article = regional_candidates[index][positions[index]]
            positions[index] += 1
            results.append(article)
            seen_urls.add(article["url"])
            selected_per_region[index] += 1
        if results:
            mix = ", ".join(
                f"{regions[index][1]}={count}"
                for index, count in enumerate(selected_per_region) if count
            )
            print(f"  [Google RSS] regional candidates: {mix}", flush=True)
        return results

    def _fetch_news_region(self, topic: str, limit: int, lang: str, country: str) -> list[dict]:
        params = {
            "q": topic,
            "hl": lang,
            "gl": country,
            "ceid": f"{country}:{lang}",
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

            time_status = "known" if pub_date else "unknown"

            articles.append(TopicArticle(title, link, self._clean_description(description), pub_date, source, "news", time_status).to_dict())
            if len(articles) >= limit:
                break
        return articles

    @staticmethod
    def _parse_article_datetime(value: str) -> datetime | None:
        """Google News pubDate를 timezone-aware datetime으로 변환한다."""
        if not value:
            return None

        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(value)

            if dt.tzinfo is None:
                return dt.astimezone()

            return dt
        except (TypeError, ValueError, IndexError):
            try:
                # GDELT uses compact UTC timestamps such as 20260815090000.
                if re.fullmatch(r"\d{14}", value):
                    from datetime import timezone

                    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                normalized = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                return dt if dt.tzinfo is not None else dt.astimezone()
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _filter_by_time_window(
        articles: list[dict],
        window_start: datetime | None,
        window_end: datetime | None,
        *,
        include_time_unknown: bool = False,
    ) -> list[dict]:
        """지정된 시간 구간 [start, end)에 해당하는 기사만 반환한다."""

        filtered: list[dict] = []

        for article in articles:
            article_dt = TopicNewsCrawler._parse_article_datetime(
                article.get("date", "")
            )

            if article_dt is None:
                if article.get("kind") == "gossip" and include_time_unknown:
                    filtered.append(article)
                elif window_start is None and window_end is None and article.get("kind") != "gossip":
                    filtered.append(article)
                continue

            if window_start is None and window_end is None:
                filtered.append(article)
                continue

            if window_start is not None:
                article_dt = article_dt.astimezone(window_start.tzinfo)

            if window_start is not None and article_dt < window_start:
                continue

            if window_end is not None and article_dt >= window_end:
                continue

            filtered.append(article)

        return filtered

    def _fetch_gossip(
        self,
        topic: str,
        limit: int,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        seen_urls: set[str] = set()

        # Tavily provides a single optional social-discovery path across Reddit
        # and X, so it receives the gossip allocation before individual APIs.
        # It is not used when a historical time window is requested.
        if (
            window_start is None
            and window_end is None
            and "tavily" in self.community_sources
            and self.tavily_crawler.is_configured
        ):
            tavily_articles = self.tavily_crawler.fetch(topic, limit)
            platform_counts: dict[str, int] = {}
            for article in tavily_articles:
                if article["url"] not in seen_urls:
                    results.append(article)
                    seen_urls.add(article["url"])
                    platform = str(article.get("platform") or "tavily").lower()
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1
            platform_summary = ", ".join(
                f"{platform}={count}" for platform, count in sorted(platform_counts.items())
            ) or "no matching public posts"
            print(
                f"  [Tavily Social] candidates={len(results)}; platforms: {platform_summary}; "
                "priority gossip source",
                flush=True,
            )
            if len(results) >= limit:
                return results

        remaining = limit - len(results)
        if remaining <= 0:
            return results

        crawlers = []
        if "reddit" in self.community_sources and self.reddit_crawler.is_configured:
            crawlers.append(self.reddit_crawler)
        if "x" in self.community_sources and self.x_crawler.is_configured:
            crawlers.append(self.x_crawler)
        if "youtube" in self.community_sources and self.youtube_crawler.is_configured:
            crawlers.append(self.youtube_crawler)
        if (
            "hackernews" in self.community_sources
            and self.hacker_news_crawler.supports_topic(topic)
        ):
            crawlers.append(self.hacker_news_crawler)

        if crawlers:
            per_source_limit = max(1, (remaining + len(crawlers) - 1) // len(crawlers))
            for crawler in crawlers:
                if window_start is None and window_end is None:
                    fetched_articles = crawler.fetch(topic, per_source_limit)
                else:
                    fetched_articles = crawler.fetch(
                        topic,
                        per_source_limit,
                        window_start=window_start,
                        window_end=window_end,
                    )
                for article in fetched_articles:
                    if article["url"] not in seen_urls:
                        results.append(article)
                        seen_urls.add(article["url"])
                    if len(results) >= limit:
                        return results
            return results
        if self.allow_google_gossip_fallback:
            for article in self._fetch_google_gossip(topic, remaining):
                if article["url"] not in seen_urls:
                    results.append(article)
                    seen_urls.add(article["url"])
                if len(results) >= limit:
                    break
        return results

    def _fetch_google_gossip(self, topic: str, limit: int) -> list[dict]:
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
