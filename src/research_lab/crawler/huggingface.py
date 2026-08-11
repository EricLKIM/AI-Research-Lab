"""
huggingface.py

HuggingFace 트렌딩 모델 크롤러.
HuggingFace Hub API를 우선 사용하고, 실패 시 웹 파싱으로 fallback한다.

반환 형식:
    [
        {
            "source": "HuggingFace",
            "title": "모델명",
            "url": "https://huggingface.co/...",
            "summary": "task • 파라미터 수 • 다운로드 수",
            "date": "updated N days ago",
            "category": "task 유형",
        },
        ...
    ]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HF_API_URL = "https://huggingface.co/api/models"
HF_WEB_URL = "https://huggingface.co/models?sort=trending"
HF_BASE_URL = "https://huggingface.co"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


@dataclass
class HFModel:
    model_id: str
    task: str = ""
    downloads: int = 0
    likes: int = 0
    last_modified: str = ""
    params: str = ""

    @property
    def url(self) -> str:
        return f"{HF_BASE_URL}/{self.model_id}"

    def to_dict(self) -> dict:
        parts = [p for p in [self.task, self.params,
                              f"↓{self.downloads:,}" if self.downloads else "",
                              f"♥{self.likes:,}" if self.likes else ""] if p]
        return {
            "source": "HuggingFace",
            "title": self.model_id,
            "url": self.url,
            "summary": " • ".join(parts),
            "date": self.last_modified,
            "category": self.task or "Unknown",
        }


class HuggingFaceCrawler:
    """
    HuggingFace 트렌딩 모델 크롤러.

    우선순위:
    1. HF Hub API (가장 정확)
    2. 웹 파싱 fallback

    사용 예:
        crawler = HuggingFaceCrawler()
        models = crawler.fetch(limit=5)
    """

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, limit: int = 5) -> list[dict]:
        """트렌딩 모델을 limit개 가져온다."""
        results = self._fetch_from_api(limit)
        if results:
            return results
        print("  ℹ️  HF API 실패 → 웹 파싱으로 전환")
        return self._fetch_from_web(limit)

    # ── API ───────────────────────────────────────────────────────────────

    def _fetch_from_api(self, limit: int) -> list[dict]:
        """HuggingFace Hub API에서 트렌딩 모델 조회."""
        try:
            resp = self.session.get(
                HF_API_URL,
                params={"sort": "trending", "limit": limit, "full": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  HF API 오류: {e}")
            return []

        if not isinstance(data, list):
            print(f"  ⚠️  HF API 응답 형식이 예상과 다릅니다: {type(data).__name__}")
            return []

        results = []
        for item in data[:limit]:
            model = HFModel(
                model_id=item.get("modelId") or item.get("id", ""),
                task=item.get("pipeline_tag", ""),
                downloads=item.get("downloads", 0),
                likes=item.get("likes", 0),
                last_modified=(item.get("lastModified") or "")[:10],
            )
            if model.model_id:
                results.append(model.to_dict())
        return results

    # ── 웹 파싱 fallback ──────────────────────────────────────────────────

    def _fetch_from_web(self, limit: int) -> list[dict]:
        """HuggingFace 모델 목록 페이지 파싱."""
        try:
            resp = self.session.get(HF_WEB_URL, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠️  HuggingFace 웹 파싱 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        seen: set[str] = set()

        # 모델 카드 링크 추출 (패턴: /username/modelname)
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            # HF 모델 URL 패턴: /org/model (슬래시 하나)
            if not re.match(r"^/[^/]+/[^/]+$", href):
                continue
            if href in seen:
                continue
            # UI/nav 링크 제외
            if any(skip in href for skip in ["/models", "/datasets", "/spaces",
                                              "/docs", "/blog", "/settings"]):
                continue
            seen.add(href)

            text = a.get_text(separator=" ", strip=True)
            # 모델명 포함 여부 확인 (org/model 형식)
            model_id = href.lstrip("/")
            if "/" not in model_id:
                continue

            # 부모 요소에서 메타 정보 추출
            parent = a.find_parent(["article", "li", "div"])
            task, date, params = "", "", ""
            if parent:
                full_text = parent.get_text(separator=" ", strip=True)
                # task 추출 (Text Generation, Image-to-Text 등)
                task_match = re.search(
                    r"(Text Generation|Image-Text-to-Text|Text-to-Image|"
                    r"Text-to-Speech|Text-to-Video|Image-to-Image|Any-to-Any)",
                    full_text
                )
                task = task_match.group(1) if task_match else ""
                # 파라미터 추출 (7B, 70B 등)
                param_match = re.search(r"(\d+(?:\.\d+)?[BKMT])\b", full_text)
                params = param_match.group(1) if param_match else ""
                # 날짜
                date_match = re.search(r"Updated (.+?)(?:•|$)", full_text)
                date = date_match.group(1).strip() if date_match else ""

            model = HFModel(
                model_id=model_id,
                task=task,
                last_modified=date,
                params=params,
            )
            results.append(model.to_dict())

            if len(results) >= limit:
                break

        return results
