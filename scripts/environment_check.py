#!/usr/bin/env python3
"""
environment_check.py

실행 환경을 검증하는 스크립트.
프로젝트 시작 전 또는 CI 파이프라인에서 실행한다.

사용법:
    python scripts/environment_check.py
"""

import os
import sys
from pathlib import Path

# Gracefully fall back when Rich is unavailable.
try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ── Configuration ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent

REQUIRED_PYTHON = (3, 11)

REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
]

OPTIONAL_ENV_VARS = [
    "AI_MODEL",
    "OPENAI_API_BASE",
    "VAULT_PATH",
    "MEMORY_PATH",
    "DEBUG",
    "LOG_LEVEL",
]

REQUIRED_PATHS = [
    "memory/",
    "docs/adr/",
    "src/research_lab/",
    "vault/",
    ".env",
]


# ── Check helpers ───────────────────────────────────────────────────────────
def check_python_version() -> tuple[bool, str]:
    """Python 버전이 요구사항을 만족하는지 확인."""
    current = sys.version_info[:2]
    ok = current >= REQUIRED_PYTHON
    msg = f"{current[0]}.{current[1]} (required: {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+)"
    return ok, msg


def check_env_vars() -> list[tuple[str, bool, str]]:
    """환경 변수 존재 여부 확인."""
    results = []

    for var in REQUIRED_ENV_VARS:
        val = os.environ.get(var)
        ok = val is not None and val.strip() != ""
        status = "✓ SET" if ok else "✗ MISSING (필수!)"
        results.append((var, ok, status))

    for var in OPTIONAL_ENV_VARS:
        val = os.environ.get(var)
        ok = val is not None
        status = f"✓ {val}" if ok else "- not set (선택)"
        results.append((var, True, status))  # optional은 항상 pass

    return results


def check_paths() -> list[tuple[str, bool, str]]:
    """필수 경로 존재 여부 확인."""
    results = []
    for path_str in REQUIRED_PATHS:
        path = PROJECT_ROOT / path_str
        ok = path.exists()
        status = "✓ exists" if ok else "✗ NOT FOUND"
        results.append((path_str, ok, status))
    return results


def check_dotenv() -> tuple[bool, str]:
    """.env 파일 로드 가능 여부 확인."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return False, ".env 파일 없음 → cp .env.example .env 실행 필요"
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        return True, ".env 로드 성공"
    except ImportError:
        return False, "python-dotenv 미설치 → uv sync 실행 필요"


# ── Output ──────────────────────────────────────────────────────────────────
def print_results(
    python_ok: bool,
    python_msg: str,
    env_results: list,
    path_results: list,
    dotenv_ok: bool,
    dotenv_msg: str,
) -> bool:
    """결과를 출력하고 전체 성공 여부를 반환."""
    all_ok = True

    if HAS_RICH:
        _print_rich(python_ok, python_msg, env_results, path_results, dotenv_ok, dotenv_msg)
    else:
        _print_plain(python_ok, python_msg, env_results, path_results, dotenv_ok, dotenv_msg)

    # Determine the overall result.
    if not python_ok:
        all_ok = False
    if not dotenv_ok:
        all_ok = False
    for _, ok, _ in env_results:
        if not ok:
            all_ok = False
    for _, ok, _ in path_results:
        if not ok:
            all_ok = False

    return all_ok


def _print_rich(python_ok, python_msg, env_results, path_results, dotenv_ok, dotenv_msg):
    console.print("\n[bold cyan]🔍 AI Research Lab — Environment Check[/bold cyan]\n")

    # Python version
    icon = "✅" if python_ok else "❌"
    console.print(f"  {icon} Python: {python_msg}")

    # .env
    icon = "✅" if dotenv_ok else "⚠️ "
    console.print(f"  {icon} dotenv: {dotenv_msg}")

    # Environment variables
    console.print("\n  [bold]환경 변수[/bold]")
    for var, ok, status in env_results:
        icon = "✅" if ok else "❌"
        console.print(f"    {icon} {var}: {status}")

    # Paths
    console.print("\n  [bold]필수 경로[/bold]")
    for path, ok, status in path_results:
        icon = "✅" if ok else "⚠️ "
        console.print(f"    {icon} {path}: {status}")


def _print_plain(python_ok, python_msg, env_results, path_results, dotenv_ok, dotenv_msg):
    print("\n=== AI Research Lab — Environment Check ===\n")
    print(f"  Python: {'OK' if python_ok else 'FAIL'} — {python_msg}")
    print(f"  dotenv: {'OK' if dotenv_ok else 'WARN'} — {dotenv_msg}")
    print("\n  환경 변수:")
    for var, ok, status in env_results:
        print(f"    {'OK' if ok else 'FAIL'} {var}: {status}")
    print("\n  필수 경로:")
    for path, ok, status in path_results:
        print(f"    {'OK' if ok else 'WARN'} {path}: {status}")


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    dotenv_ok, dotenv_msg = check_dotenv()
    python_ok, python_msg = check_python_version()
    env_results = check_env_vars()
    path_results = check_paths()

    all_ok = print_results(
        python_ok, python_msg,
        env_results, path_results,
        dotenv_ok, dotenv_msg,
    )

    if all_ok:
        print("\n✅ 모든 환경 체크 통과! 개발 시작 가능.\n")
        return 0
    else:
        print("\n❌ 일부 체크 실패. 위 항목을 확인하세요.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
