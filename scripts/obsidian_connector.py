#!/usr/bin/env python3
"""
obsidian_connector.py

두 가지 기능을 담당한다:

1. Memory Sync: memory/ → vault/AI-Research-Lab/ 동기화
2. Graph Export: KnowledgeGraph → vault/knowledge/ Obsidian 네이티브 형식 내보내기
   - 각 노드를 .md 파일로 변환 (YAML frontmatter + wikilinks)
   - _index.md (MOC) 자동 생성

사용법:
    python scripts/obsidian_connector.py --sync          # memory 동기화
    python scripts/obsidian_connector.py --export-graph  # graph 내보내기
    python scripts/obsidian_connector.py --all           # 둘 다
    python scripts/obsidian_connector.py --status        # 상태 확인
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_lab.knowledge.graph import KnowledgeGraph
from research_lab.obsidian.exporter import GraphExporter
from research_lab.obsidian.syncer import MemorySyncer


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Obsidian Vault 동기화 & Knowledge Graph 내보내기"
    )
    parser.add_argument("--sync", action="store_true", help="memory/ → vault 동기화")
    parser.add_argument("--export-graph", action="store_true", help="KnowledgeGraph → vault/knowledge/")
    parser.add_argument("--all", action="store_true", help="sync + export-graph 모두 실행")
    parser.add_argument("--status", action="store_true", help="동기화 상태 확인")
    parser.add_argument("--dry-run", action="store_true", help="실제 파일 변경 없이 미리보기")
    parser.add_argument(
        "--graph-file",
        default=str(PROJECT_ROOT / "vault" / "knowledge_graph.json"),
        help="KnowledgeGraph JSON 파일 경로 (기본: vault/knowledge_graph.json)",
    )
    args = parser.parse_args()

    memory_dir = PROJECT_ROOT / "memory"
    vault_dir  = PROJECT_ROOT / "vault"

    syncer   = MemorySyncer(memory_dir, vault_dir, dry_run=args.dry_run)
    graph_path = Path(args.graph_file)
    exporter = GraphExporter(graph_path, vault_dir, dry_run=args.dry_run)

    ran_something = False

    if args.status:
        syncer.print_status()
        exporter.print_status()
        ran_something = True

    if args.sync or args.all:
        print(f"\n{'[dry-run] ' if args.dry_run else ''}🔄 Memory 동기화 시작...\n")
        syncer.sync()
        ran_something = True

    if args.export_graph or args.all:
        print(f"\n{'[dry-run] ' if args.dry_run else ''}📤 Knowledge Graph 내보내기 시작...\n")
        exporter.export()
        ran_something = True

    if not ran_something:
        parser.print_help()


if __name__ == "__main__":
    main()
