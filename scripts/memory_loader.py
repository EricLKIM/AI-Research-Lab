#!/usr/bin/env python3
"""
memory_loader.py

memory/ 디렉토리의 마크다운 파일들을 로드하고
현재 프로젝트 컨텍스트를 요약해서 출력하는 스크립트.

사용법:
    python scripts/memory_loader.py           # 전체 요약
    python scripts/memory_loader.py --file 05  # 특정 파일만
"""

import sys
from pathlib import Path

# Add the project root to sys.path.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_lab.memory.loader import MemoryLoader


def main():
    import argparse

    parser = argparse.ArgumentParser(description="프로젝트 메모리 로더")
    parser.add_argument(
        "--file",
        default=None,
        help="특정 메모리 파일 번호 (예: 05 → 05_Current_Status.md)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=False,
        help="한 줄 요약만 출력",
    )
    args = parser.parse_args()

    loader = MemoryLoader(PROJECT_ROOT / "memory")

    if args.file:
        content = loader.load_by_prefix(args.file)
        if content:
            print(content)
        else:
            print(f"❌ '{args.file}'로 시작하는 메모리 파일을 찾을 수 없습니다.")
            sys.exit(1)
    elif args.summary:
        print(loader.get_summary())
    else:
        loader.print_all()


if __name__ == "__main__":
    main()
