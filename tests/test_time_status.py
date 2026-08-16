import json
from pathlib import Path

from research_lab.crawler.topic_news import TopicArticle, TopicNewsCrawler


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "time_status_articles.json"


def test_time_status_dataset():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    known = TopicArticle(
        data[0]["title"],
        data[0]["url"],
        data[0]["summary"],
        data[0]["date"],
        data[0]["source"],
        data[0]["kind"],
    ).to_dict()

    unknown = TopicArticle(
        data[1]["title"],
        data[1]["url"],
        data[1]["summary"],
        data[1]["date"],
        data[1]["source"],
        data[1]["kind"],
    ).to_dict()

    gossip = TopicArticle(
        data[2]["title"],
        data[2]["url"],
        data[2]["summary"],
        data[2]["date"],
        data[2]["source"],
        data[2]["kind"],
    ).to_dict()

    assert known["time_status"] == "unknown"
    assert unknown["time_status"] == "unknown"
    assert gossip["time_status"] == "unknown"


def test_time_unknown_gossip_is_preserved_but_excluded_by_default():
    articles = [
        {"url": "https://example.com/known", "kind": "gossip", "date": "Thu, 13 Aug 2026 10:00:00 GMT", "time_status": "known"},
        {"url": "https://example.com/unknown", "kind": "gossip", "date": "", "time_status": "unknown"},
    ]

    filtered = TopicNewsCrawler._filter_by_time_window(articles, None, None)
    included = TopicNewsCrawler._filter_by_time_window(articles, None, None, include_time_unknown=True)

    assert [article["url"] for article in filtered] == ["https://example.com/known"]
    assert [article["url"] for article in included] == ["https://example.com/known", "https://example.com/unknown"]
