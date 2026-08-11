"""
topic_formatter.py

주제 뉴스 분석 결과를 Obsidian 마크다운으로 저장한다.

출력 파일: vault/topics/{주제}/{YYYY-MM-DD}.md

lang 파라미터("ko"/"en")는 고정 틀 문구(섹션 제목 등)만 바꾼다. 실제 GPT가 작성한
본문 내용의 언어는 analyzer 호출 시 넘긴 output_language로 이미 결정되어 있다.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from research_lab.analyzer.topic_gpt import TopicAnalysisResult
from research_lab.i18n import file_strings

TOPICS_DIR = "topics"


def _slugify(text: str) -> str:
    """폴더명으로 쓸 수 있게 주제명에서 경로에 쓸 수 없는 문자만 제거한다 (한글은 유지)."""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    return text or "주제"


class TopicDigestFormatter:
    """
    주제 분석 결과를 Obsidian vault/topics/{주제}/ 에 저장한다.

    사용 예:
        formatter = TopicDigestFormatter(Path("vault/"))
        path = formatter.save(result)
    """

    def __init__(self, vault_dir: Path, lang: str = "ko") -> None:
        self.vault_dir = Path(vault_dir)
        self.lang = lang if lang in ("ko", "en") else "ko"
        self.s = file_strings(self.lang)

    def save(self, result: TopicAnalysisResult) -> Path:
        topic_slug = _slugify(result.topic)
        out_dir = self.vault_dir / TOPICS_DIR / topic_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        content = self._render(result)
        path = out_dir / f"{result.date}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _render(self, r: TopicAnalysisResult) -> str:
        s = self.s
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tags = list(s["topic_tags"]) + [t for t in r.suggested_tags if t]
        sections: list[str] = []

        sections.append(
            f"---\n"
            f"date: {r.date}\n"
            f"topic: {r.topic}\n"
            f"tags: [{', '.join(tags)}]\n"
            f"generated_at: \"{now}\"\n"
            f"---\n"
        )

        title = s["topic_title_fmt"].format(topic=r.topic)
        sections.append(f"# {title} ({r.date})\n")

        if r.trend_summary:
            sections.append(f"## {s['topic_trend_heading']}")
            for t in r.trend_summary:
                sections.append(f"- {t}")
            sections.append("")

        if r.highlights:
            sections.append(f"## {s['topic_highlights_heading']}")
            for h in r.highlights:
                h_title = h.get("title", "")
                url = h.get("url", "")
                source = h.get("source", "")
                why = h.get("why_important", "")
                sections.append(f"### [{h_title}]({url})")
                if source:
                    sections.append(f"- {s['source_label']}: {source}")
                if why:
                    sections.append(f"- {why}")
                sections.append("")

        if r.suggested_search_queries:
            heading = "추천 검색어" if self.lang == "ko" else "Suggested Search Queries"
            sections.append(f"## {heading}")
            for q in r.suggested_search_queries:
                sections.append(f"- {q}")
            sections.append("")

        if r.key_takeaways:
            sections.append(f"## {s['topic_takeaways_heading']}")
            for t in r.key_takeaways:
                sections.append(f"- {t}")
            sections.append("")

        return "\n".join(sections)
