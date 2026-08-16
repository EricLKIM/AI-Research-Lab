from research_lab.crawler.reddit import RedditCrawler
from research_lab.crawler.topic_news import TopicNewsCrawler


def test_reddit_crawler_returns_timestamped_community_articles(monkeypatch):
    class FakeTokenResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "test-token"}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": {
                    "children": [{"data": {
                        "title": "Community discussion",
                        "permalink": "/r/MachineLearning/comments/example",
                        "selftext": "A useful community signal.",
                        "created_utc": 1786603200,
                        "subreddit_name_prefixed": "r/MachineLearning",
                    }}]
                }
            }

    crawler = RedditCrawler("id", "secret", "ai-research-lab:1.0 (by /u/test)")
    monkeypatch.setattr(crawler.session, "post", lambda *args, **kwargs: FakeTokenResponse())
    monkeypatch.setattr(crawler.session, "get", lambda *args, **kwargs: FakeResponse())

    results = crawler.fetch("AI", 1)

    assert results[0]["kind"] == "gossip"
    assert results[0]["platform"] == "reddit"
    assert results[0]["community"] == "r/MachineLearning"
    assert results[0]["time_status"] == "known"


def test_strict_gossip_mode_does_not_replace_missing_gossip(monkeypatch):
    crawler = TopicNewsCrawler(gossip_ratio=20, gossip_mode="strict")
    monkeypatch.setattr(crawler, "_fetch_news", lambda topic, limit: [{
        "url": f"https://news.example/{index}", "kind": "news"
    } for index in range(limit)])
    monkeypatch.setattr(crawler, "_fetch_gossip", lambda topic, limit: [])

    results = crawler.fetch("AI", limit=10)

    assert len(results) == 8
    assert all(article["kind"] == "news" for article in results)
