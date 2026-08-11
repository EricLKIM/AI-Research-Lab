"""
exporter.py

KnowledgeGraph → Obsidian vault/knowledge/ 내보내기.

각 노드를 Obsidian 네이티브 마크다운으로 변환:
  - YAML frontmatter: id, tags, created_at, source
  - [[wikilinks]]: 연결된 노드를 Obsidian 링크로
  - #tags: Obsidian 태그 시스템 연동
  - _index.md (MOC): 전체 Knowledge Map

내보내기 형식 예시:
    ---
    id: adr
    tags: [설계, 문서]
    created_at: 2026-07-25
    source: ""
    ---

    # ADR

    아키텍처 결정 기록

    ## 연결된 개념

    - [[소프트웨어-설계]] (part_of)

    ---
    #설계 #문서
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from research_lab.knowledge.graph import KnowledgeGraph, Node, RelationType

VAULT_KNOWLEDGE_DIR = "knowledge"

# 한국어/영어 혼용 제목을 파일명으로 변환하는 함수
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|#^\[\]]')


def title_to_filename(title: str) -> str:
    """노드 제목을 Obsidian 안전 파일명으로 변환한다."""
    name = _UNSAFE_CHARS.sub("", title)
    name = name.strip().replace(" ", "-")
    # 연속 하이픈 정리
    name = re.sub(r"-{2,}", "-", name)
    return name or "unnamed"


RELATION_LABEL: dict[RelationType, str] = {
    RelationType.RELATED_TO:  "관련",
    RelationType.BUILDS_ON:   "기반",
    RelationType.CONTRADICTS: "반박",
    RelationType.EXEMPLIFIES: "예시",
    RelationType.PART_OF:     "포함",
}


@dataclass
class ExportResult:
    node_id: str
    filename: str
    status: str   # "exported" | "skipped" | "dry"


class GraphExporter:
    """
    KnowledgeGraph를 Obsidian vault/knowledge/ 폴더로 내보낸다.

    사용 예:
        exporter = GraphExporter(Path("vault/knowledge_graph.json"), Path("vault/"))
        exporter.export()
    """

    def __init__(self, graph_path: Path, vault_dir: Path, dry_run: bool = False) -> None:
        self.graph_path  = Path(graph_path)
        self.vault_dir   = Path(vault_dir)
        self.target_dir  = self.vault_dir / VAULT_KNOWLEDGE_DIR
        self.dry_run     = dry_run

    # ── 상태 ──────────────────────────────────────────────────────────────

    def print_status(self) -> None:
        print("\n=== Knowledge Graph 내보내기 상태 ===")
        if not self.graph_path.exists():
            print(f"  ❌ Graph 파일 없음: {self.graph_path}")
            return
        kg = KnowledgeGraph.load(self.graph_path)
        print(f"  📊 {kg.summary()}")
        print(f"  📁 내보내기 경로: {self.target_dir}")
        existing = list(self.target_dir.glob("*.md")) if self.target_dir.exists() else []
        print(f"  📄 현재 vault/knowledge/에 있는 파일: {len(existing)}개")

    # ── 변환 ──────────────────────────────────────────────────────────────

    def _node_to_markdown(self, node: Node, kg: KnowledgeGraph) -> str:
        """노드 하나를 Obsidian 마크다운 문자열로 변환한다."""

        # YAML frontmatter
        tags_yaml = ", ".join(f'"{t}"' for t in node.tags)
        frontmatter = (
            f"---\n"
            f"id: {node.id}\n"
            f"tags: [{tags_yaml}]\n"
            f"created_at: {node.created_at}\n"
            f"source: \"{node.source}\"\n"
            f"---\n"
        )

        # 본문
        body = f"\n# {node.title}\n\n{node.content}\n"

        # 연결된 노드 섹션
        related = kg.get_related(node.id)
        links_section = ""
        if related:
            lines = ["\n## 연결된 개념\n"]
            for rel_node, relation, direction in related:
                label = RELATION_LABEL.get(relation, relation.value)
                arrow = "→" if direction == "outgoing" else "←"
                filename = title_to_filename(rel_node.title)
                lines.append(f"- {arrow} [[{filename}]] ({label})")
            links_section = "\n".join(lines) + "\n"

        # 태그 footer (Obsidian 태그 패널 연동)
        tags_footer = ""
        if node.tags:
            tag_str = " ".join(f"#{t}" for t in node.tags)
            tags_footer = f"\n---\n{tag_str}\n"

        return frontmatter + body + links_section + tags_footer

    def _build_moc(self, kg: KnowledgeGraph) -> str:
        """MOC (Map of Content) — vault/knowledge/_index.md 생성."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "---",
            'tags: ["MOC", "Knowledge-Graph"]',
            "---",
            "",
            "# Knowledge Graph — Map of Content",
            "",
            f"> 자동 생성: {now}  ",
            f"> 노드: {kg.node_count}개 | 엣지: {kg.edge_count}개",
            "",
            "## 노드 목록",
            "",
        ]

        # 태그별로 그루핑
        all_tags = kg.get_all_tags()
        tagged_nodes: dict[str, list[Node]] = {tag: kg.search_by_tag(tag) for tag in all_tags}
        untagged = [n for n in kg._nodes.values() if not n.tags]

        if all_tags:
            for tag in all_tags:
                lines.append(f"### #{tag}")
                for node in tagged_nodes[tag]:
                    filename = title_to_filename(node.title)
                    lines.append(f"- [[{filename}]]")
                lines.append("")

        if untagged:
            lines.append("### 태그 없음")
            for node in untagged:
                filename = title_to_filename(node.title)
                lines.append(f"- [[{filename}]]")
            lines.append("")

        # 관계 목록
        lines += [
            "## 관계 목록",
            "",
            "| From | 관계 | To |",
            "|------|------|----|",
        ]
        for edge in kg._edges:
            src = kg.get_node(edge.source_id)
            tgt = kg.get_node(edge.target_id)
            if src and tgt:
                src_link = f"[[{title_to_filename(src.title)}]]"
                tgt_link = f"[[{title_to_filename(tgt.title)}]]"
                label = RELATION_LABEL.get(edge.relation, edge.relation.value)
                lines.append(f"| {src_link} | {label} | {tgt_link} |")

        return "\n".join(lines) + "\n"

    # ── 내보내기 ──────────────────────────────────────────────────────────

    def export(self) -> list[ExportResult]:
        """
        KnowledgeGraph의 모든 노드를 vault/knowledge/ 에 내보낸다.

        그래프 파일이 없으면 경고 후 종료.
        """
        if not self.graph_path.exists():
            print(f"  ⚠️  Graph 파일 없음: {self.graph_path}")
            print("  → 먼저 KnowledgeGraph를 생성하고 save()하세요.")
            return []

        kg = KnowledgeGraph.load(self.graph_path)

        if kg.node_count == 0:
            print("  ℹ️  그래프에 노드가 없습니다.")
            return []

        if not self.dry_run:
            self.target_dir.mkdir(parents=True, exist_ok=True)

        results: list[ExportResult] = []

        # 노드별 .md 파일 생성
        for node in kg._nodes.values():
            filename = title_to_filename(node.title) + ".md"
            target   = self.target_dir / filename
            content  = self._node_to_markdown(node, kg)

            if self.dry_run:
                print(f"  📋 dry    {filename}")
                results.append(ExportResult(node.id, filename, "dry"))
            else:
                target.write_text(content, encoding="utf-8")
                print(f"  ✅ export {filename}")
                results.append(ExportResult(node.id, filename, "exported"))

        # MOC (_index.md)
        moc_content = self._build_moc(kg)
        moc_path    = self.target_dir / "_index.md"

        if self.dry_run:
            print(f"  📋 dry    _index.md (MOC)")
        else:
            moc_path.write_text(moc_content, encoding="utf-8")
            print(f"  ✅ export _index.md (MOC)")

        exported = sum(1 for r in results if r.status == "exported")
        print(f"\n  완료: {exported}개 노드 + MOC 파일 → {self.target_dir}")
        return results
