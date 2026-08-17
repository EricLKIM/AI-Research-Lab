from research_lab.backfill_policy import resolve_dump_scan_mode


def test_auto_dump_scan_uses_configured_full_period_threshold():
    assert resolve_dump_scan_mode("auto", 3, 3) == "full"
    assert resolve_dump_scan_mode("auto", 4, 3) == "sample"


def test_explicit_dump_scan_mode_overrides_automatic_threshold():
    assert resolve_dump_scan_mode("full", 90, 3) == "full"
    assert resolve_dump_scan_mode("sample", 1, 90) == "sample"
