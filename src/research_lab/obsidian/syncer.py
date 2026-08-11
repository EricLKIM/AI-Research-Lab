"""
syncer.py

memory/ 디렉토리를 vault/AI-Research-Lab/ 으로 동기화한다.
변경된 파일만 복사하는 증분 동기화(incremental sync).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

VAULT_SUBDIR = "AI-Research-Lab"


@dataclass
class SyncResult:
    filename: str
    status: str   # "synced" | "skipped" | "dry"


class MemorySyncer:
    """
    memory/ → vault/AI-Research-Lab/ 단방향 동기화.

    사용 예:
        syncer = MemorySyncer(memory_dir, vault_dir)
        syncer.sync()
    """

    def __init__(self, memory_dir: Path, vault_dir: Path, dry_run: bool = False) -> None:
        self.memory_dir = Path(memory_dir)
        self.vault_dir  = Path(vault_dir)
        self.target_dir = self.vault_dir / VAULT_SUBDIR
        self.dry_run    = dry_run

    # ── 상태 ──────────────────────────────────────────────────────────────

    def get_status(self) -> list[dict]:
        """memory/와 vault/ 간의 동기화 상태 목록을 반환."""
        results = []
        for mem_file in sorted(self.memory_dir.glob("*.md")):
            vault_file = self.target_dir / mem_file.name
            if not vault_file.exists():
                status = "NOT_SYNCED"
            elif vault_file.stat().st_mtime < mem_file.stat().st_mtime:
                status = "OUTDATED"
            else:
                status = "UP_TO_DATE"
            results.append({"file": mem_file.name, "status": status,
                             "source": mem_file, "target": vault_file})
        return results

    def print_status(self) -> None:
        print("\n=== Memory Sync 상태 ===")
        icons = {"UP_TO_DATE": "✅", "OUTDATED": "⚠️ ", "NOT_SYNCED": "❌"}
        for item in self.get_status():
            print(f"  {icons.get(item['status'], '?')} {item['file']}: {item['status']}")

    # ── 동기화 ────────────────────────────────────────────────────────────

    def sync(self) -> list[SyncResult]:
        """증분 동기화: 변경/누락 파일만 복사한다."""
        if not self.dry_run:
            self.target_dir.mkdir(parents=True, exist_ok=True)

        results: list[SyncResult] = []
        for item in self.get_status():
            if item["status"] == "UP_TO_DATE":
                print(f"  ✓ skip    {item['file']}")
                results.append(SyncResult(item["file"], "skipped"))
                continue

            if self.dry_run:
                print(f"  📋 dry    {item['file']}")
                results.append(SyncResult(item["file"], "dry"))
            else:
                shutil.copy2(item["source"], item["target"])
                print(f"  ✅ synced {item['file']}")
                results.append(SyncResult(item["file"], "synced"))

        # 메타 기록
        if not self.dry_run:
            synced_count = sum(1 for r in results if r.status == "synced")
            self._write_meta(synced_count)

        return results

    def _write_meta(self, synced_count: int) -> None:
        meta = self.target_dir / "_sync_meta.md"
        meta.write_text(
            f"# Sync Meta\n\n"
            f"- 마지막 동기화: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 동기화된 파일: {synced_count}개\n",
            encoding="utf-8",
        )
