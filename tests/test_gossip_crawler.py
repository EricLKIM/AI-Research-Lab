from research_lab.crawler.topic_news import TopicNewsCrawler


def test_fetch_news_sets_time_status_from_rss_pub_date(monkeypatch):
    """RSS pubDate 유무에 따라 뉴스 time_status를 설정한다."""

    rss = b"""
    <rss><channel>
      <item>
        <title>Published article</title>
        <link>https://news.example/published</link>
        <pubDate>Thu, 13 Aug 2026 10:00:00 GMT</pubDate>
        <source>Example News</source>
      </item>
      <item>
        <title>Undated article</title>
        <link>https://news.example/undated</link>
        <source>Example News</source>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        content = rss

        def raise_for_status(self):
            pass

    crawler = TopicNewsCrawler()
    monkeypatch.setattr(crawler.session, "get", lambda *args, **kwargs: FakeResponse())

    results = crawler._fetch_news("AI", 2)

    assert [article["time_status"] for article in results] == ["known", "unknown"]
    assert results[0]["date"] == "Thu, 13 Aug 2026 10:00:00 GMT"
    assert results[1]["date"] == ""


def test_gossip_html_parsing():
    """Google 검색 결과와 유사한 HTML에서 gossip 결과를 정상적으로 추출하는지 테스트한다."""

    html = """
    <html>
      <body>
        <div class="MjjYud">
          <div>
            <a href="/url?q=https://example.com/blog/ai-opinion">
              <h3>AI에 대한 개인적인 생각</h3>
            </a>
            <div class="VwiC3b">
              AI에 대한 개인적인 의견과 경험을 공유합니다.
            </div>
          </div>
        </div>

        <div class="MjjYud">
          <div>
            <a href="/url?q=https://example.com/forum/ai">
              <h3>AI 커뮤니티 토론</h3>
            </a>
            <div class="VwiC3b">
              AI에 대한 커뮤니티 토론 내용입니다.
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    crawler = TopicNewsCrawler(gossip_ratio=100)

    # Test HTML parsing directly without making an HTTP request.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    results = []
    seen = set()

    for block in soup.select("div.MjjYud, div.g"):
        h3 = block.find("h3")
        a = h3.find_parent("a") if h3 else None

        if not a or not a.get("href"):
            continue

        url = crawler._unwrap_google_url(a.get("href", ""))

        if not url or "google." in url:
            continue

        title = h3.get_text(" ", strip=True)

        snippet_el = block.select_one("div.VwiC3b, div[data-sncf]")
        summary = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        if not title or url in seen:
            continue

        seen.add(url)

        results.append({
            "title": title,
            "url": url,
            "summary": summary,
            "kind": "gossip",
        })

    assert len(results) == 2
    assert all(article["kind"] == "gossip" for article in results)

def test_fetch_gossip_returns_gossip(monkeypatch):
    """_fetch_gossip()이 Google 검색 결과를 gossip으로 반환하는지 테스트한다."""

    html = """
    <html>
      <body>
        <div class="MjjYud">
          <a href="/url?q=https://example.com/blog/ai">
            <h3>AI에 대한 개인적인 생각</h3>
          </a>
          <div class="VwiC3b">
            AI에 대한 개인적인 의견입니다.
          </div>
        </div>

        <div class="MjjYud">
          <a href="/url?q=https://example.com/forum/ai">
            <h3>AI 커뮤니티 토론</h3>
          </a>
          <div class="VwiC3b">
            AI에 대한 커뮤니티 토론입니다.
          </div>
        </div>
      </body>
    </html>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            pass

    def fake_get(*args, **kwargs):
        return FakeResponse()

    crawler = TopicNewsCrawler(
        lang="ko",
        country="KR",
        gossip_ratio=100,
    )

    monkeypatch.setattr(crawler.session, "get", fake_get)

    results = crawler._fetch_gossip("인공지능", 2)

    assert len(results) == 2
    assert all(article["kind"] == "gossip" for article in results)
    assert all(article["time_status"] == "unknown" for article in results)

def test_gossip_ratio_is_reflected_in_final_results(monkeypatch):
    crawler = TopicNewsCrawler(
        lang="ko",
        country="KR",
        lr="lang_ko|country_KR",
        gossip_ratio=20,
        include_time_unknown=True,
    )

    def fake_news(topic, limit):
        return [
            {
                "source": "News",
                "title": f"News {i}",
                "url": f"https://news.example/{i}",
                "summary": f"News {i}",
                "date": "Thu, 13 Aug 2026 10:00:00 GMT",
                "kind": "news",
                "time_status": "known",
            }
            for i in range(limit)
        ]

    def fake_gossip(topic, limit):
        return [
            {
                "source": "Gossip",
                "title": f"Gossip {i}",
                "url": f"https://gossip.example/{i}",
                "summary": f"Gossip {i}",
                "date": "",
                "kind": "gossip",
                "time_status": "unknown",
            }
            for i in range(limit)
        ]

    monkeypatch.setattr(crawler, "_fetch_news", fake_news)
    monkeypatch.setattr(crawler, "_fetch_gossip", fake_gossip)

    results = crawler.fetch("인공지능", limit=10)

    gossip_count = sum(
        1 for article in results
        if article["kind"] == "gossip"
    )

    news_count = sum(
        1 for article in results
        if article["kind"] == "news"
    )

    assert len(results) == 10
    assert gossip_count == 2
    assert news_count == 8
