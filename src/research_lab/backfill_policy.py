"""Small, deterministic policies shared by manual and scheduled backfill."""
from __future__ import annotations


def resolve_dump_scan_mode(mode: str, day_count: int, full_scan_max_days: int) -> str:
    """Resolve an explicit or automatic GDELT dump scan mode."""
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode in {"sample", "full"}:
        return normalized_mode
    threshold = max(1, min(365, int(full_scan_max_days)))
    return "full" if max(1, int(day_count)) <= threshold else "sample"
