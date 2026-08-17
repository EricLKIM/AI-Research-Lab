"""
loader.py

memory/ 디렉토리의 마크다운 파일을 읽고 쓰는 핵심 모듈.

읽기:
    - load_all(): 전체 로드 (캐시)
    - load_by_prefix("05"): prefix로 특정 파일 내용 반환

쓰기:
    - write_section(): 특정 섹션 내용 업데이트
    - append_log(): 날짜 기반 로그 항목 추가
    - update_status(): 05_Current_Status.md 태스크 상태 변경
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass
class MemoryFile:
    """단일 메모리 파일의 파싱 결과."""

    filename: str
    title: str
    content: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        """파일명 앞의 숫자 prefix를 반환 (예: '05')."""
        match = re.match(r"^(\d+)", self.filename)
        return match.group(1) if match else ""

    @property
    def summary(self) -> str:
        """첫 번째 섹션 또는 첫 단락을 요약으로 반환."""
        if self.sections:
            first_key = next(iter(self.sections))
            text = self.sections[first_key].strip()
            lines = [l for l in text.split("\n") if l.strip()][:2]
            return " | ".join(lines)
        lines = [l for l in self.content.split("\n") if l.strip()]
        return lines[1] if len(lines) > 1 else self.title


class MemoryLoader:
    """
    memory/ 디렉토리를 로드·파싱·수정하는 클래스.

    읽기 예:
        loader = MemoryLoader(Path("memory/"))
        print(loader.load_by_prefix("05"))

    쓰기 예:
        loader.write_section("05_Current_Status.md", "현재 블로커", "없음")
        loader.append_log("04_Learning_Progress.md", "Knowledge Graph 기초 학습 완료")
        loader.update_status("05_Current_Status.md", "memory_loader 쓰기 기능", "✅ 완료")
    """

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = Path(memory_dir)
        self._cache: dict[str, MemoryFile] | None = None

    # ── Parsing ───────────────────────────────────────────────────────────

    def _parse_file(self, path: Path) -> MemoryFile:
        """마크다운 파일을 파싱해서 MemoryFile로 반환."""
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")

        title = path.stem
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        sections: dict[str, str] = {}
        current_section = ""
        current_content: list[str] = []

        for line in lines:
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return MemoryFile(
            filename=path.name,
            title=title,
            content=content,
            sections=sections,
        )

    # ── Reading ───────────────────────────────────────────────────────────

    def load_all(self) -> dict[str, MemoryFile]:
        """모든 메모리 파일을 로드하고 캐시한다."""
        if self._cache is not None:
            return self._cache

        if not self.memory_dir.exists():
            return {}

        result: dict[str, MemoryFile] = {}
        for md_file in sorted(self.memory_dir.glob("*.md")):
            result[md_file.name] = self._parse_file(md_file)

        self._cache = result
        return result

    def load_by_prefix(self, prefix: str) -> str | None:
        """prefix로 시작하는 메모리 파일의 내용을 반환."""
        for filename, mem_file in self.load_all().items():
            if mem_file.prefix == prefix:
                return mem_file.content
        return None

    def get_file_path(self, filename: str) -> Path | None:
        """파일명으로 실제 경로를 반환. prefix도 허용 (예: '05')."""
        # Exact filename match
        exact = self.memory_dir / filename
        if exact.exists():
            return exact
        # Prefix match
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if re.match(rf"^{re.escape(filename)}", md_file.name):
                return md_file
        return None

    def get_summary(self) -> str:
        """모든 메모리 파일의 한 줄 요약을 반환."""
        all_files = self.load_all()
        if not all_files:
            return "메모리 파일이 없습니다."

        lines = ["=== Project Memory Summary ===\n"]
        for _, mem_file in all_files.items():
            lines.append(f"[{mem_file.prefix}] {mem_file.title}")
            lines.append(f"     → {mem_file.summary[:80]}")
            lines.append("")
        return "\n".join(lines)

    def print_all(self) -> None:
        """모든 메모리 파일 내용을 출력."""
        all_files = self.load_all()
        if not all_files:
            print("메모리 파일이 없습니다.")
            return
        for filename, mem_file in all_files.items():
            print(f"\n{'='*60}")
            print(f"📄 {filename}")
            print("=" * 60)
            print(mem_file.content)

    # ── Writing ───────────────────────────────────────────────────────────

    def write_section(self, filename: str, section_name: str, new_content: str) -> bool:
        """
        특정 섹션의 내용을 교체한다.

        Args:
            filename: 대상 파일명 또는 prefix (예: '05' or '05_Current_Status.md')
            section_name: 교체할 섹션 제목 (## 뒤의 텍스트)
            new_content: 새 섹션 내용

        Returns:
            성공 여부

        Example:
            loader.write_section("05", "현재 블로커", "없음")
        """
        path = self.get_file_path(filename)
        if path is None:
            raise FileNotFoundError(f"메모리 파일을 찾을 수 없습니다: {filename}")

        content = path.read_text(encoding="utf-8")

        # Section pattern: heading through the next heading, footer, or end of file.
        pattern = rf"(## {re.escape(section_name)}\n)(.*?)(?=\n## |\n\*마지막|\Z)"
        replacement = rf"\g<1>{new_content}\n"

        new_content_full, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

        if count == 0:
            # Add the section at the end when it does not exist.
            new_content_full = content.rstrip() + f"\n\n## {section_name}\n\n{new_content}\n"

        # Refresh the last-updated date.
        today = date.today().strftime("%Y-%m-%d")
        new_content_full = re.sub(
            r"\*마지막 업데이트: .*?\*",
            f"*마지막 업데이트: {today}*",
            new_content_full,
        )

        path.write_text(new_content_full, encoding="utf-8")
        self.invalidate_cache()
        return True

    def append_log(self, filename: str, log_entry: str, section_name: str = "학습 로그") -> bool:
        """
        로그 섹션에 날짜 기반 항목을 추가한다.

        Args:
            filename: 대상 파일명 또는 prefix
            log_entry: 추가할 로그 내용
            section_name: 로그를 추가할 섹션 이름 (기본: '학습 로그')

        Example:
            loader.append_log("04", "Knowledge Graph 기초 개념 정리 완료")
        """
        path = self.get_file_path(filename)
        if path is None:
            raise FileNotFoundError(f"메모리 파일을 찾을 수 없습니다: {filename}")

        content = path.read_text(encoding="utf-8")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"\n### {now}\n- {log_entry}\n"

        # Find the section and append to it.
        pattern = rf"(## {re.escape(section_name)}\n)(.*?)(?=\n## |\Z)"

        def add_entry(m: re.Match) -> str:
            return m.group(1) + m.group(2).rstrip() + new_entry + "\n"

        new_content, count = re.subn(pattern, add_entry, content, flags=re.DOTALL)

        if count == 0:
            # Create the section when it does not exist.
            new_content = content.rstrip() + f"\n\n## {section_name}\n{new_entry}"

        path.write_text(new_content, encoding="utf-8")
        self.invalidate_cache()
        return True

    def update_status(self, filename: str, task_name: str, new_status: str) -> bool:
        """
        Current Status 파일의 태스크 상태를 변경한다.
        마크다운 테이블의 태스크명을 찾아서 상태 셀을 교체한다.

        Args:
            filename: 대상 파일명 또는 prefix (예: '05')
            task_name: 테이블에서 찾을 태스크명
            new_status: 새 상태 값 (예: '✅ 완료', '🔄 진행 중', '⏳ 예정')

        Example:
            loader.update_status("05", "memory_loader 쓰기 기능", "✅ 완료")
        """
        path = self.get_file_path(filename)
        if path is None:
            raise FileNotFoundError(f"메모리 파일을 찾을 수 없습니다: {filename}")

        content = path.read_text(encoding="utf-8")

        # Table-row pattern: | task name | status | ... |
        pattern = rf"(\|\s*{re.escape(task_name)}\s*\|\s*)([^|]+)(\|)"
        replacement = rf"\g<1>{new_status} \g<3>"

        new_content, count = re.subn(pattern, replacement, content)

        if count == 0:
            return False  # 태스크를 찾지 못함

        path.write_text(new_content, encoding="utf-8")
        self.invalidate_cache()
        return True

    def create_file(self, prefix: str, name: str, initial_content: str = "") -> Path:
        """
        새 메모리 파일을 생성한다.

        Args:
            prefix: 파일 번호 (예: '06')
            name: 파일명 (예: 'Research_Topics')
            initial_content: 초기 마크다운 내용

        Returns:
            생성된 파일 경로
        """
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}_{name}.md"
        path = self.memory_dir / filename

        if path.exists():
            raise FileExistsError(f"이미 존재하는 파일: {filename}")

        if not initial_content:
            today = date.today().strftime("%Y-%m-%d")
            initial_content = (
                f"# {prefix}. {name.replace('_', ' ')}\n\n"
                f"> 설명을 여기에 작성하세요.\n\n"
                f"---\n\n"
                f"*마지막 업데이트: {today}*\n"
            )

        path.write_text(initial_content, encoding="utf-8")
        self.invalidate_cache()
        return path

    # ── Cache ─────────────────────────────────────────────────────────────

    def invalidate_cache(self) -> None:
        """캐시를 무효화한다 (파일 변경 후 재로드 필요 시)."""
        self._cache = None
