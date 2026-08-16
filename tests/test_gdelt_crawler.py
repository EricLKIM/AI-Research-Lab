from datetime import datetime, timezone

from research_lab.crawler.gdelt import GdeltCrawler
from research_lab.crawler.topic_news import TopicNewsCrawler


def test_gdelt_crawler_uses_requested_time_window_and_maps_articles(monkeypatch):
    crawler = GdeltCrawler()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"articles": [
                {"title": "China one", "url": "https://a.example/1", "domain": "a.example", "sourcecountry": "China", "seendate": "20260815090000"},
                {"title": "China two", "url": "https://a.example/2", "domain": "a.example", "sourcecountry": "China", "seendate": "20260815090000"},
                {"title": "Korea one", "url": "https://b.example/1", "domain": "b.example", "sourcecountry": "South Korea", "seendate": "20260815090000"},
            ]}

    def fake_get(*args, **kwargs):
        captured.update(kwargs["params"])
        return FakeResponse()

    monkeypatch.setattr(crawler.session, "get", fake_get)
    start = datetime(2026, 8, 14, tzinfo=timezone.utc)
    end = datetime(2026, 8, 15, tzinfo=timezone.utc)

    articles = crawler.fetch("semiconductors", 2, start, end)

    assert captured["startdatetime"] == "20260814000000"
    assert captured["enddatetime"] == "20260815000000"
    assert articles[0]["platform"] == "gdelt"
    assert articles[0]["kind"] == "news"
    assert [article["title"] for article in articles] == ["China one", "Korea one"]


def test_gdelt_compact_timestamp_is_usable_for_backfill_filtering():
    parsed = TopicNewsCrawler._parse_article_datetime("20260815090000")

    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_country_focus_profile_uses_region_targets_before_filling_remaining_slots():
    crawler = GdeltCrawler(region_profile="country_focus", target_country="KR")
    candidates = [
        {"url": f"https://kr.example/{i}", "source_country": "South Korea", "_diversity_key": "south korea"}
        for i in range(5)
    ] + [
        {"url": f"https://us.example/{i}", "source_country": "United States", "_diversity_key": "united states"}
        for i in range(2)
    ] + [
        {"url": f"https://cn.example/{i}", "source_country": "China", "_diversity_key": "china"}
        for i in range(2)
    ] + [
        {"url": "https://fr.example/0", "source_country": "France", "_diversity_key": "france"}
    ]

    selected = crawler._select_country_focus(candidates, 10)

    assert [crawler._country_key(article) for article in selected] == [
        "korea", "korea", "korea", "korea", "korea", "us", "us", "china", "china", "other"
    ]


def test_gdelt_retries_once_after_a_rate_limit(monkeypatch):
    crawler = GdeltCrawler()
    calls = []

    class RateLimitedResponse:
        status_code = 429

        def raise_for_status(self):
            raise AssertionError("429 should be retried before raise_for_status")

    class SuccessResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"articles": []}

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return RateLimitedResponse() if len(calls) == 1 else SuccessResponse()

    monkeypatch.setattr(crawler.session, "get", fake_get)
    monkeypatch.setattr("research_lab.crawler.gdelt.time.sleep", lambda _seconds: None)

    assert crawler.fetch("Entertainment", 1) == []
    assert len(calls) == 2
