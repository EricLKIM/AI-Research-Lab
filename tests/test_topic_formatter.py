from research_lab.analyzer.topic_gpt import TopicAnalysisResult
from research_lab.digest.topic_formatter import TopicDigestFormatter


def test_topic_note_includes_all_collected_sources(tmp_path):
    result = TopicAnalysisResult(
        date="2026-08-17",
        topic="Politics",
        trend_summary=["A trend"],
        highlights=[],
        key_takeaways=[],
        suggested_tags=[],
        suggested_search_queries=[],
        collected_articles=[
            {
                "title": "A Reddit discussion",
                "url": "https://www.reddit.com/r/example/comments/1",
                "source": "r/example",
                "platform": "reddit",
                "kind": "gossip",
                "date": "2026-08-17T00:00:00+00:00",
            },
            {
                "title": "A news article",
                "url": "https://news.example/article",
                "source": "Example News",
                "kind": "news",
            },
        ],
    )

    content = TopicDigestFormatter(tmp_path, lang="en").save(result).read_text(encoding="utf-8")

    assert "## All Collected Sources (2)" in content
    assert "[A Reddit discussion](https://www.reddit.com/r/example/comments/1)" in content
    assert "r/example · reddit · gossip" in content
    assert "[A news article](https://news.example/article)" in content
