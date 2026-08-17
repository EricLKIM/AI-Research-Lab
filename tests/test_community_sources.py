from research_lab.crawler.hacker_news import HackerNewsCrawler
from research_lab.crawler.gdelt import GdeltCrawler
from research_lab.crawler.reddit import RedditCrawler
from research_lab.crawler.tavily import TavilySocialCrawler
from research_lab.crawler.topic_news import TopicNewsCrawler
from research_lab.crawler.x import XCrawler
from research_lab.crawler.youtube import YouTubeCrawler


class FakeHackerNewsCrawler:
    def supports_topic(self, topic):
        return topic == "AI"

    def fetch(self, topic, limit):
        return [{
            "source": "Hacker News",
            "title": "AI chip discussion",
            "url": "https://news.ycombinator.com/item?id=1",
            "summary": "Community discussion",
            "date": "2026-08-14T00:00:00+00:00",
            "kind": "gossip",
            "time_status": "known",
            "platform": "hackernews",
            "community": "Hacker News",
        }]


class FakeTavilyCrawler:
    is_configured = True

    def fetch(self, topic, limit, **_ignored):
        return [{
            "source": "Reddit via Tavily",
            "title": f"{topic} discussion found by Tavily",
            "url": "https://www.reddit.com/r/example/comments/tavily",
            "summary": "Social discovery result",
            "date": "2026-08-14T00:00:00+00:00",
            "kind": "gossip",
            "time_status": "known",
            "platform": "reddit",
            "community": "Reddit",
        }]


class FakeRedditCrawler:
    is_configured = True

    def fetch(self, topic, limit, **_ignored):
        return [{
            "source": "r/example",
            "title": f"{topic} direct API discussion",
            "url": "https://www.reddit.com/r/example/comments/direct",
            "summary": "Direct source result",
            "date": "2026-08-14T00:00:00+00:00",
            "kind": "gossip",
            "time_status": "known",
            "platform": "reddit",
            "community": "r/example",
        }]


def test_hacker_news_is_only_enabled_for_ai_or_semiconductor_topics():
    assert HackerNewsCrawler.supports_topic("AI chip market")
    assert HackerNewsCrawler.supports_topic("반도체 공급망")
    assert not HackerNewsCrawler.supports_topic("real estate")


def test_hacker_news_source_is_included_when_enabled(monkeypatch):
    crawler = TopicNewsCrawler(
        gossip_ratio=100,
        gossip_mode="strict",
        community_sources={"hackernews"},
        hacker_news_crawler=FakeHackerNewsCrawler(),
    )
    monkeypatch.setattr(crawler, "_fetch_news", lambda topic, limit: [])

    results = crawler.fetch("AI", limit=3)

    assert len(results) == 1
    assert results[0]["platform"] == "hackernews"


def test_empty_community_source_setting_does_not_enable_default_sources():
    crawler = TopicNewsCrawler(community_sources=set())

    assert crawler.community_sources == set()


def test_tavily_social_is_prioritized_before_direct_community_apis(monkeypatch):
    crawler = TopicNewsCrawler(
        gossip_ratio=100,
        gossip_mode="strict",
        community_sources={"tavily", "reddit"},
        tavily_crawler=FakeTavilyCrawler(),
        reddit_crawler=FakeRedditCrawler(),
    )
    monkeypatch.setattr(crawler, "_fetch_news", lambda topic, limit: [])

    results = crawler.fetch("AI", limit=2)

    assert [item["title"] for item in results] == [
        "AI discussion found by Tavily",
        "AI direct API discussion",
    ]


def test_google_rss_priority_skips_gdelt_when_rss_has_enough_news(monkeypatch):
    class SlowGdelt:
        is_configured = True

        def fetch(self, *args, **kwargs):
            raise AssertionError("GDELT must not run when Google RSS already has enough news")

    crawler = TopicNewsCrawler(
        gossip_ratio=0,
        community_sources={"gdelt"},
        gdelt_crawler=SlowGdelt(),
        latest_news_priority="google_rss",
    )
    monkeypatch.setattr(crawler, "_fetch_news", lambda topic, limit: [{
        "source": "Google News", "title": str(index), "url": f"https://example.com/{index}",
        "kind": "news", "time_status": "known",
    } for index in range(limit)])

    results = crawler.fetch("AI", limit=10)

    assert len(results) == 10


def test_balanced_google_rss_queries_multiple_national_editions(monkeypatch):
    crawler = TopicNewsCrawler(country="KR", lang="ko", community_sources=set())
    requested_countries = []

    def fake_region(topic, limit, lang, country):
        requested_countries.append(country)
        return [{
            "source": country, "title": country, "url": f"https://{country.lower()}.example/{index}",
            "kind": "news", "time_status": "known",
        } for index in range(limit)]

    monkeypatch.setattr(crawler, "_fetch_news_region", fake_region)

    results = crawler._fetch_news("Semiconductors", 10)

    assert requested_countries == ["KR", "US", "CN", "JP", "GB"]
    assert len(results) == 10


def test_source_status_reports_disabled_missing_and_topic_specific_sources():
    crawler = TopicNewsCrawler(community_sources={"reddit", "hackernews"})

    status = {
        item["source"]: item["state"]
        for item in crawler.get_community_source_status("AI")
    }

    assert status == {
        "tavily": "disabled",
        "reddit": "credentials_missing",
        "x": "disabled",
        "youtube": "disabled",
        "hackernews": "ready",
        "gdelt": "disabled",
    }


def test_connection_validation_reports_missing_credentials_without_requests():
    assert TavilySocialCrawler().validate_connection() == (False, "credentials missing")
    assert RedditCrawler().validate_connection() == (False, "credentials missing")
    assert XCrawler().validate_connection() == (False, "credentials missing")
    assert YouTubeCrawler().validate_connection() == (False, "credentials missing")


def test_configured_connection_validators_accept_successful_responses(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "test-token"}

    reddit = RedditCrawler("id", "secret", "app:1.0 (by /u/test)")
    monkeypatch.setattr(reddit.session, "post", lambda *args, **kwargs: FakeResponse())
    x = XCrawler("token")
    monkeypatch.setattr(x.session, "get", lambda *args, **kwargs: FakeResponse())
    youtube = YouTubeCrawler("key")
    monkeypatch.setattr(youtube.session, "get", lambda *args, **kwargs: FakeResponse())
    hacker_news = HackerNewsCrawler()
    gdelt = GdeltCrawler()
    monkeypatch.setattr(hacker_news.session, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(gdelt.session, "get", lambda *args, **kwargs: FakeResponse())

    assert reddit.validate_connection() == (True, "connected")
    assert x.validate_connection() == (True, "connected")
    assert youtube.validate_connection() == (True, "connected (1 YouTube quota unit used)")
    assert hacker_news.validate_connection() == (True, "connected (no API key required)")
    assert gdelt.validate_connection() == (True, "connected (no API key required)")
