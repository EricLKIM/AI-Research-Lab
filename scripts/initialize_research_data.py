#!/usr/bin/env python3
"""Remove only AI Research Lab's collected/generated data for a clean test run.

This intentionally leaves .env, gui_settings.json, topics_favorites.json, and
any .obsidian configuration untouched.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).parent.parent
DEFAULT_DATA_DIR = ROOT / "vault"


def configured_output_dir() -> Path:
    """Read the configured human-readable output location without modifying it."""
    settings_path = ROOT / "gui_settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        value = settings.get("vault_path")
        if value:
            return Path(str(value))
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_DATA_DIR


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize only collected/generated AI Research Lab data.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="machine-data vault (default: project vault)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Markdown output folder (default: read-only lookup from gui_settings.json)")
    parser.add_argument("--keep-dump-cache", action="store_true", help="preserve downloaded GDELT archive cache")
    parser.add_argument("--confirm", action="store_true", help="actually delete; without this, only print the plan")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    output_dir = (args.output_dir or configured_output_dir()).resolve()
    targets = [
        data_dir / "topics",                 # snapshots, analysis JSON, per-topic state
        data_dir / "pending_backfills.json", # retry queue
        data_dir / "_analysis_tag_index.json",
        output_dir / "topics",               # generated Markdown / baseline notes only
    ]
    if not args.keep_dump_cache:
        targets.append(data_dir / "gdelt-cache")
    targets = _unique(targets)

    print("Research-data initialization plan")
    print("Preserved: .env, gui_settings.json, topics_favorites.json, .obsidian, and all files outside the listed targets.")
    for target in targets:
        state = "will remove" if target.exists() else "already absent"
        print(f"- {state}: {target}")
    if not args.confirm:
        print("\nDry run only. Re-run with --confirm to remove these targets.")
        return 0

    for target in targets:
        if target.exists():
            _remove(target)
            print(f"Removed: {target}")
    print("Initialization complete. Your API key and personal settings were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
