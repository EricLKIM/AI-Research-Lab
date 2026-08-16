from research_lab.pending_backfills import pending_days, record_failure, resolve_day


def test_pending_backfill_is_deduplicated_and_resolved(tmp_path):
    record_failure(tmp_path, "Semiconductors", "2026-08-14", "gdelt_dump", "certificate error", needs_http_consent=True)
    record_failure(tmp_path, "Semiconductors", "2026-08-14", "gdelt_dump", "certificate error again", needs_http_consent=True)

    assert pending_days(tmp_path, "Semiconductors") == ["2026-08-14"]

    resolve_day(tmp_path, "Semiconductors", "2026-08-14")

    assert pending_days(tmp_path, "Semiconductors") == []
