import zipfile
from datetime import date, timedelta

from research_lab.crawler.gdelt_dump import GdeltDumpCrawler


def test_local_gdelt_dump_filter_uses_topic_expansion_and_deduplicates_urls(tmp_path):
    crawler = GdeltDumpCrawler(tmp_path)
    archive = crawler.archive_path(date(2026, 8, 15))
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "sample.gkg.csv",
            "id\t20260815T010000Z\t1\texample.com\thttps://example.com/a\t\t\t\tNVIDIA;TECH\n"
            "id\t20260815T020000Z\t1\texample.com\thttps://example.com/a\t\t\t\tNVIDIA;TECH\n",
        )

    articles = crawler.filter_day(date(2026, 8, 15), "Semiconductors", limit=10)

    assert len(articles) == 1
    assert articles[0]["platform"] == "gdelt_dump"
    assert articles[0]["url"] == "https://example.com/a"


def test_master_file_list_groups_15_minute_gkg_blocks_by_day(tmp_path, monkeypatch):
    class Response:
        text = (
            "123 http://data.gdeltproject.org/gdeltv2/20260815000000.gkg.csv.zip\n"
            "456 http://data.gdeltproject.org/gdeltv2/20260815150000.gkg.csv.zip\n"
        )

        def raise_for_status(self):
            pass

    crawler = GdeltDumpCrawler(tmp_path)
    monkeypatch.setattr(crawler.session, "get", lambda *args, **kwargs: Response())

    grouped = crawler._master_urls()

    assert grouped is not None
    assert len(grouped["2026-08-15"]) == 2


def test_balanced_sample_uses_five_evenly_spaced_utc_windows(tmp_path):
    entries = [
        (f"http://example.com/20260815{hour:02d}0000.gkg.csv.zip", tmp_path / f"20260815{hour:02d}0000.gkg.csv.zip")
        for hour in range(0, 24)
    ]

    selected = GdeltDumpCrawler._balanced_sample_entries(entries)

    assert [path.name[8:12] for _, path in selected] == ["0000", "0500", "1000", "1500", "2000"]


def test_compact_persistent_keeps_five_balanced_blocks_for_old_cached_days(tmp_path):
    day = date.today() - timedelta(days=10)
    for clock in ("0000", "0300", "0500", "1000", "1500", "2000"):
        (tmp_path / f"{day:%Y%m%d}{clock}00.gkg.csv.zip").touch()
    crawler = GdeltDumpCrawler(tmp_path, cache_policy="compact_persistent", compact_after_days=3)

    crawler.compact_existing_cache()

    retained = sorted(path.name[8:12] for path in tmp_path.glob(f"{day:%Y%m%d}*.gkg.csv.zip"))
    assert retained == ["0000", "0500", "1000", "1500", "2000"]


def test_compact_persistent_preserves_recent_full_cached_days(tmp_path):
    day = date.today() - timedelta(days=2)
    for clock in ("0000", "0300", "0500", "1000", "1500", "2000"):
        (tmp_path / f"{day:%Y%m%d}{clock}00.gkg.csv.zip").touch()
    crawler = GdeltDumpCrawler(tmp_path, cache_policy="compact_persistent", compact_after_days=3)

    crawler.compact_existing_cache()

    assert len(list(tmp_path.glob(f"{day:%Y%m%d}*.gkg.csv.zip"))) == 6


def test_full_scan_handles_all_master_list_blocks_without_sample_quotas(tmp_path, monkeypatch):
    day = date(2026, 8, 15)
    urls = [
        f"http://example.com/{day:%Y%m%d}000000.gkg.csv.zip",
        f"http://example.com/{day:%Y%m%d}001500.gkg.csv.zip",
    ]
    crawler = GdeltDumpCrawler(tmp_path)
    for index, url in enumerate(urls):
        path = tmp_path / url.rsplit("/", 1)[-1]
        with zipfile.ZipFile(path, "w") as zipped:
            zipped.writestr(
                "sample.gkg.csv",
                f"id\t20260815T0{index}0000Z\t1\texample.com\thttps://example.com/{index}\t\t\t\tECONOMY\n",
            )
    monkeypatch.setattr(crawler, "_day_archive_urls", lambda _day: urls)

    articles = crawler.filter_day(day, "Economy", limit=5, scan_mode="full")

    assert len(articles) == 2
