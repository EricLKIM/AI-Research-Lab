"""
favorites.py

자주 쓰는 리서치 주제 목록(즐겨찾기)을 관리한다.
프로젝트 루트의 topics_favorites.json 에 저장하며, 매번 타이핑하지 않고
번호 선택만으로 원하는 주제를 고를 수 있게 해준다.

기본 즐겨찾기는 출력 언어에 맞춰 표시한다. 사용자가 직접 수정한 즐겨찾기
목록은 언어를 바꿔도 보존하며, 기존 프로그램 기본값만 저장되어 있는 경우에만
현재 언어의 기본값으로 안전하게 마이그레이션한다.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_FAVORITES_BY_LANG = {
    "ko": ["경제", "반도체", "부동산"],
    "en": ["Economy", "Semiconductors", "Real Estate"],
    "ja": ["経済", "半導体", "不動産"],
    "zh": ["经济", "半导体", "房地产"],
    "es": ["Economía", "Semiconductores", "Bienes raíces"],
    "fr": ["Économie", "Semi-conducteurs", "Immobilier"],
    "de": ["Wirtschaft", "Halbleiter", "Immobilien"],
    "vi": ["Kinh tế", "Chất bán dẫn", "Bất động sản"],
}

# 구버전 기본값 및 언어별 기본값을 구분해 두면, 사용자가 직접 추가한 항목을
# 실수로 덮어쓰지 않으면서 언어 변경 시 기본 목록만 자동 전환할 수 있다.
LEGACY_DEFAULT_FAVORITES = ["경제", "반도체", "부동산"]
_KNOWN_DEFAULT_SETS = {
    tuple(items) for items in DEFAULT_FAVORITES_BY_LANG.values()
}
_KNOWN_DEFAULT_SETS.add(tuple(LEGACY_DEFAULT_FAVORITES))


def _normalize_lang(lang: str | None) -> str:
    raw = (lang or "en").strip().lower()
    aliases = {
        "kr": "ko", "korean": "ko", "한국어": "ko",
        "english": "en", "en-us": "en", "en-gb": "en",
        "japanese": "ja", "日本語": "ja",
        "chinese": "zh", "中文": "zh", "zh-cn": "zh",
        "spanish": "es", "español": "es",
        "french": "fr", "français": "fr",
        "german": "de", "deutsch": "de",
        "vietnamese": "vi", "tiếng việt": "vi",
    }
    return aliases.get(raw, raw.split("-")[0])


class TopicFavorites:
    """즐겨찾기 주제 목록을 읽고 쓴다."""

    def __init__(self, path: Path, lang: str = "en") -> None:
        self.path = path
        self.lang = _normalize_lang(lang)
        self.default_favorites = list(
            DEFAULT_FAVORITES_BY_LANG.get(self.lang, DEFAULT_FAVORITES_BY_LANG["en"])
        )

    def _migrate_if_default(self, topics: list[str]) -> list[str]:
        """현재 저장 목록이 프로그램의 기본값일 때만 현재 언어 기본값으로 전환한다."""
        if tuple(topics) in _KNOWN_DEFAULT_SETS:
            if topics != self.default_favorites:
                self.save(self.default_favorites)
                return list(self.default_favorites)
        return topics

    def load(self) -> list[str]:
        """저장된 목록을 불러온다. 파일이 없으면 현재 언어 기본값으로 새로 만든다."""
        if not self.path.exists():
            self.save(self.default_favorites)
            return list(self.default_favorites)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                topics = [str(t).strip() for t in data if str(t).strip()]
                return self._migrate_if_default(topics)
        except (json.JSONDecodeError, OSError, TypeError):
            pass
        return list(self.default_favorites)

    def save(self, topics: list[str]) -> None:
        self.path.write_text(
            json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, topic: str) -> list[str]:
        """새 주제를 목록에 추가한다 (중복이면 그대로 둠)."""
        topics = self.load()
        if topic not in topics:
            topics.append(topic)
            self.save(topics)
        return topics

    def remove(self, index: int) -> list[str]:
        """0-based 인덱스로 항목을 제거한다."""
        topics = self.load()
        if 0 <= index < len(topics):
            topics.pop(index)
            self.save(topics)
        return topics
