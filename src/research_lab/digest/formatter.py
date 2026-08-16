"""
formatter.py

GPT 분석 결과를 Obsidian 마크다운 형식으로 변환한다.

출력 파일: vault/digest/YYYY-MM-DD.md

Obsidian 형식 특징:
- YAML frontmatter (date, tags, source)
- [[wikilinks]] 로 Knowledge Graph 노드 연결
- #태그
- 접을 수 있는 섹션 (> [!note] callout)

lang 파라미터("ko"/"en")는 고정 틀 문구(섹션 제목 등)만 바꾼다. 실제 GPT가 작성한
본문 내용의 언어는 analyzer 호출 시 넘긴 output_language로 이미 결정되어 있다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from research_lab.analyzer.gpt import AnalysisResult
from research_lab.i18n import file_strings

DIGEST_DIR = "digest"


class DigestFormatter:
    """
    분석 결과를 Obsidian vault/digest/ 에 저장한다.

    사용 예:
        formatter = DigestFormatter(Path("vault/"))
        path = formatter.save(result)
        print(f"저장됨: {path}")
    """

    def __init__(self, vault_dir: Path, lang: str = "ko") -> None:
        self.vault_dir  = Path(vault_dir)
        self.digest_dir = self.vault_dir / DIGEST_DIR
        self.lang = lang if lang in ("ko", "en") else "ko"
        self.s = file_strings(self.lang)

    def save(self, result: AnalysisResult) -> Path:
        """분석 결과를 Obsidian 마크다운 파일로 저장한다."""
        self.digest_dir.mkdir(parents=True, exist_ok=True)
        content = self._render(result)
        path = self.digest_dir / f"{result.date}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _render(self, r: AnalysisResult) -> str:
        """AnalysisResult → Obsidian 마크다운 문자열."""
        s = self.s
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections: list[str] = []

        # ── YAML Frontmatter ──────────────────────────────────────────────
        tag_str = ", ".join(s["digest_tags"])
        sections.append(
            f"---\n"
            f"date: {r.date}\n"
            f"tags: [{tag_str}]\n"
            f"sources: [AI Times, HuggingFace]\n"
            f"generated_at: \"{now}\"\n"
            f"---\n"
        )

        # ── Title ──────────────────────────────────────────────────────────
        sections.append(f"# 🤖 {s['digest_title']} — {r.date}\n")
        sections.append(
            f"> [!info] {s['auto_generated_note']}\n"
            f"> {s['auto_generated_body']}\n"
            f"> {s['generated_at']}: {now}\n"
        )

        # ── Trend summary ──────────────────────────────────────────────────
        if r.trend_summary:
            sections.append(f"## 📊 {s['trend_summary_heading']}\n")
            for i, trend in enumerate(r.trend_summary, 1):
                sections.append(f"{i}. {trend}")
            sections.append("")

        # ── Highlights ─────────────────────────────────────────────────────
        if r.highlights:
            sections.append(f"## 🔥 {s['highlights_heading']}\n")
            for h in r.highlights:
                title = h.get("title", "")
                source = h.get("source", "")
                url = h.get("url", "")
                why = h.get("why_important", "")

                link = f"[{title}]({url})" if url else title
                sections.append(f"### {link}")
                sections.append(f"> **{s['source_label']}**: {source}")
                if why:
                    sections.append(f"\n{why}\n")
            sections.append("")

        # ── Research implications ──────────────────────────────────────────
        if r.research_implications:
            sections.append(f"## 🔬 {s['research_implications_heading']}\n")
            for impl in r.research_implications:
                sections.append(f"- {impl}")
            sections.append("")

        # ── IP/patent perspective ──────────────────────────────────────────
        if r.ip_perspective:
            sections.append(f"## ⚖️ {s['ip_perspective_heading']}\n")
            sections.append(
                f"> [!tip] {s['ip_perspective_heading']}\n"
                + "\n".join(f"> {line}" for line in r.ip_perspective.split("\n"))
            )
            sections.append("")

        # ── Suggested Knowledge Graph nodes ────────────────────────────────
        if r.suggested_nodes:
            sections.append(f"## 🧠 {s['kg_suggestion_heading']}\n")
            sections.append(
                f"> [!note] {s['kg_suggestion_body']}\n"
                "> `uv run python scripts/research_digest.py --apply-nodes`\n"
            )
            for node in r.suggested_nodes:
                node_id = node.get("id", "")
                title  = node.get("title", "")
                content = node.get("content", "")
                tags   = node.get("tags", [])
                node_tag_str = " ".join(f"#{t}" for t in tags)

                sections.append(f"### [[{title}]]")
                sections.append(f"- **{s['kg_id_label']}**: `{node_id}`")
                sections.append(f"- **{s['kg_content_label']}**: {content}")
                if tags:
                    sections.append(f"- **{s['kg_tags_label']}**: {node_tag_str}")
                sections.append("")

        # ── Error display ──────────────────────────────────────────────────
        if r.error:
            sections.append(f"## ⚠️ {s['error_heading']}\n")
            sections.append(
                f"> [!warning] {s['error_occurred_note']}\n"
                f"> {r.error}\n"
            )

        # ── Tag footer ─────────────────────────────────────────────────────
        sections.append("---")
        sections.append(" ".join(f"#{t}" for t in s["digest_tags"]))

        return "\n".join(sections) + "\n"
