"""
graph.py

Knowledge Graph — 노드(개념)와 엣지(관계)를 관리한다.
JSON 파일로 영속성을 지원한다. (재시작해도 데이터 유지)

저장 형식:
    {
        "nodes": { "id": { "id", "title", "content", "tags", "created_at", "source" } },
        "edges": [ { "source_id", "target_id", "relation", "note" } ]
    }

사용 예:
    kg = KnowledgeGraph.load(Path("vault/knowledge_graph.json"))
    kg.add_node(Node(id="adr", title="ADR", content="..."))
    kg.add_edge(Edge("adr", "swe", RelationType.PART_OF))
    kg.save()
    related = kg.get_related("adr")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path


class RelationType(str, Enum):
    """노드 간 관계 유형. str 상속으로 JSON 직렬화 지원."""
    RELATED_TO   = "related_to"    # 일반적 연관
    BUILDS_ON    = "builds_on"     # 위에 쌓이는 관계 (A가 B를 기반으로)
    CONTRADICTS  = "contradicts"   # 모순/반박 관계
    EXEMPLIFIES  = "exemplifies"   # 구체적 예시 관계
    PART_OF      = "part_of"       # 포함 관계


@dataclass
class Node:
    """지식 그래프의 노드 — 하나의 개념/아이디어."""
    id: str
    title: str
    content: str
    tags: list[str]          = field(default_factory=list)
    created_at: str          = field(default_factory=lambda: date.today().isoformat())
    source: str              = ""

    def __hash__(self):
        return hash(self.id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(**d)


@dataclass
class Edge:
    """두 노드 간의 관계."""
    source_id: str
    target_id: str
    relation: RelationType
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            source_id=d["source_id"],
            target_id=d["target_id"],
            relation=RelationType(d["relation"]),
            note=d.get("note", ""),
        )


class KnowledgeGraph:
    """
    JSON 영속성을 지원하는 Knowledge Graph.

    파일 없이 인메모리로만 사용:
        kg = KnowledgeGraph()

    파일에서 로드 (없으면 빈 그래프 생성):
        kg = KnowledgeGraph.load(Path("vault/knowledge_graph.json"))
        kg.save()  # 저장

    자동 저장 컨텍스트 매니저:
        with KnowledgeGraph.open(path) as kg:
            kg.add_node(...)
        # 블록 종료 시 자동 저장
    """

    def __init__(self, save_path: Path | None = None) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._save_path = save_path

    # ── 영속성 ────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> "KnowledgeGraph":
        """JSON 파일에서 그래프를 로드한다. 파일이 없으면 빈 그래프를 반환."""
        path = Path(path)
        kg = cls(save_path=path)

        if not path.exists():
            return kg

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Knowledge Graph 파일 로드 실패: {e}") from e

        for node_data in data.get("nodes", {}).values():
            kg._nodes[node_data["id"]] = Node.from_dict(node_data)

        for edge_data in data.get("edges", []):
            kg._edges.append(Edge.from_dict(edge_data))

        return kg

    def save(self, path: Path | None = None) -> Path:
        """그래프를 JSON 파일로 저장한다."""
        target = path or self._save_path
        if target is None:
            raise ValueError("저장 경로가 지정되지 않았습니다. save(path=...) 또는 load()로 경로를 지정하세요.")

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "meta": {
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
                "last_saved": date.today().isoformat(),
            },
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
            "edges": [edge.to_dict() for edge in self._edges],
        }

        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @classmethod
    def open(cls, path: Path) -> "_KnowledgeGraphContext":
        """with 문에서 사용할 컨텍스트 매니저를 반환한다."""
        return _KnowledgeGraphContext(path)

    # ── 노드 조작 ─────────────────────────────────────────────────────────

    def add_node(self, node: Node) -> None:
        """노드를 추가한다. 같은 id면 덮어쓴다."""
        self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> bool:
        """노드와 연결된 모든 엣지를 삭제한다."""
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        self._edges = [
            e for e in self._edges
            if e.source_id != node_id and e.target_id != node_id
        ]
        return True

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def update_node(self, node_id: str, **kwargs) -> bool:
        """노드의 특정 필드를 업데이트한다."""
        node = self._nodes.get(node_id)
        if node is None:
            return False
        for key, value in kwargs.items():
            if hasattr(node, key):
                object.__setattr__(node, key, value) if hasattr(node, "__dataclass_fields__") else setattr(node, key, value)
        # dataclass는 mutable이므로 직접 수정
        node_dict = node.to_dict()
        node_dict.update(kwargs)
        self._nodes[node_id] = Node.from_dict(node_dict)
        return True

    # ── 엣지 조작 ─────────────────────────────────────────────────────────

    def add_edge(self, edge: Edge) -> None:
        """엣지를 추가한다. 양쪽 노드가 존재해야 한다."""
        if edge.source_id not in self._nodes:
            raise ValueError(f"소스 노드 없음: {edge.source_id}")
        if edge.target_id not in self._nodes:
            raise ValueError(f"타겟 노드 없음: {edge.target_id}")
        # 중복 엣지 방지
        for existing in self._edges:
            if (existing.source_id == edge.source_id and
                    existing.target_id == edge.target_id and
                    existing.relation == edge.relation):
                return  # 이미 존재하는 관계
        self._edges.append(edge)

    def remove_edge(self, source_id: str, target_id: str, relation: RelationType) -> bool:
        """특정 엣지를 삭제한다."""
        before = len(self._edges)
        self._edges = [
            e for e in self._edges
            if not (e.source_id == source_id and
                    e.target_id == target_id and
                    e.relation == relation)
        ]
        return len(self._edges) < before

    # ── 조회 ──────────────────────────────────────────────────────────────

    def get_related(self, node_id: str) -> list[tuple[Node, RelationType, str]]:
        """
        특정 노드와 연결된 모든 노드를 반환한다.

        Returns:
            [(Node, RelationType, direction), ...]
            direction: 'outgoing' | 'incoming'
        """
        results = []
        for edge in self._edges:
            if edge.source_id == node_id:
                target = self._nodes.get(edge.target_id)
                if target:
                    results.append((target, edge.relation, "outgoing"))
            elif edge.target_id == node_id:
                source = self._nodes.get(edge.source_id)
                if source:
                    results.append((source, edge.relation, "incoming"))
        return results

    def search_by_tag(self, tag: str) -> list[Node]:
        """태그로 노드를 검색한다."""
        return [n for n in self._nodes.values() if tag in n.tags]

    def search_by_title(self, query: str, case_sensitive: bool = False) -> list[Node]:
        """제목으로 노드를 검색한다 (부분 매칭)."""
        if not case_sensitive:
            query = query.lower()
        return [
            n for n in self._nodes.values()
            if query in (n.title if case_sensitive else n.title.lower())
        ]

    def get_all_tags(self) -> list[str]:
        """그래프에 있는 모든 태그 목록을 반환한다."""
        tags: set[str] = set()
        for node in self._nodes.values():
            tags.update(node.tags)
        return sorted(tags)

    # ── 통계 ──────────────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def summary(self) -> str:
        tags = self.get_all_tags()
        return (
            f"KnowledgeGraph("
            f"nodes={self.node_count}, "
            f"edges={self.edge_count}, "
            f"tags={tags}"
            f")"
        )

    def __repr__(self) -> str:
        return self.summary()


class _KnowledgeGraphContext:
    """with 문을 위한 컨텍스트 매니저."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._kg: KnowledgeGraph | None = None

    def __enter__(self) -> KnowledgeGraph:
        self._kg = KnowledgeGraph.load(self._path)
        return self._kg

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._kg is not None and exc_type is None:
            self._kg.save()
        return False  # 예외 전파
