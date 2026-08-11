"""
credibility.py

크롤링된 기사/모델 항목의 신뢰성을 GPT로 평가하는 선택(opt-in) 기능.

기본적으로는 꺼져 있다 — 켜면 크롤링된 항목을 평가하기 위한 GPT 호출이
추가로 발생해서 API 토큰을 더 소모한다 (설정 화면에도 이 점을 안내한다).

사용자가 지정한 신뢰도 임계값(threshold, 0~100)을 기준으로 필터링한다:

- 임계값이 높을수록(예: 80) 신뢰도가 검증된 항목만 남기고, 확인되지 않은
  루머·가십성 정보는 걸러낸다. → "정확도 중심"
- 임계값이 낮을수록(예: 10) 아직 검증되지 않았더라도 새로운 소식이나
  화제성 있는 정보를 더 많이 통과시킨다. → "신규성 · 가십 허용"
  (예: 경제 뉴스에서 확인되지 않은 "찌라시"성 정보도 놓치지 싶지 않은 사용자)

평가 자체가 실패하면(네트워크 오류, JSON 파싱 실패 등) 안전하게 모든 항목을
그대로 통과시킨다(fail-open) — 신뢰성 평가는 부가 기능이므로, 이 기능의
오류가 전체 파이프라인을 막아서는 안 된다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

CREDIBILITY_SYSTEM_PROMPT = """당신은 정보의 신뢰성을 평가하는 팩트체커입니다.
아래 기사/모델 항목 목록을 보고, 각 항목에 대해 0~100 사이의 신뢰도 점수를 매기세요.

평가 기준:
- 출처의 공식성/신뢰도 (공식 언론사·기관 발표 vs 익명 커뮤니티·미확인 SNS·블로그)
- 내용의 구체성과 검증 가능성 (구체적 수치·인용·공식 발표 vs 추측·소문·과장된 제목)
- 선정성/가십성 (자극적인 제목이거나 확인되지 않은 주장일수록 낮은 점수)

반드시 아래 JSON 형식으로만 응답하세요:
{
  "scores": [
    {"index": 0, "score": 85, "reason": "공식 발표를 인용하고 구체적 수치를 포함함"},
    {"index": 1, "score": 20, "reason": "출처 불명, 확인되지 않은 추측성 제목"}
  ]
}"""


@dataclass
class CredibilityResult:
    """일괄 평가 결과. scores/reasons의 key는 입력 리스트의 index다."""
    scores: dict[int, int] = field(default_factory=dict)
    reasons: dict[int, str] = field(default_factory=dict)
    error: str = ""

    @property
    def is_success(self) -> bool:
        return not self.error


class CredibilityScorer:
    """
    크롤링된 항목들의 신뢰도를 한 번의 GPT 호출로 일괄 평가한다.

    사용 예:
        scorer = CredibilityScorer(api_key="sk-...")
        result = scorer.score(articles)
        kept, dropped = filter_by_threshold(articles, result, threshold=40)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4-nano",
        max_tokens: int = 1500,
        timeout: int = 60,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.base_url = base_url or None

    def score(self, items: list[dict]) -> CredibilityResult:
        """items(기사/모델 dict 목록)에 대해 신뢰도 점수를 매긴다."""
        if not items:
            return CredibilityResult()

        try:
            import openai
        except ImportError:
            return CredibilityResult(error="openai 패키지 미설치. `uv add openai` 실행 필요.")

        try:
            client = openai.OpenAI(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CREDIBILITY_SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_message(items)},
                ],
                max_tokens=self.max_tokens,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
        except Exception as e:  # noqa: BLE001 — 평가 실패는 fail-open으로 처리
            return CredibilityResult(error=str(e))

        scores: dict[int, int] = {}
        reasons: dict[int, str] = {}
        for entry in data.get("scores", []):
            try:
                idx = int(entry.get("index"))
            except (TypeError, ValueError):
                continue
            try:
                scores[idx] = max(0, min(100, int(entry.get("score", 100))))
            except (TypeError, ValueError):
                scores[idx] = 100
            reasons[idx] = str(entry.get("reason", ""))

        return CredibilityResult(scores=scores, reasons=reasons)

    @staticmethod
    def _build_message(items: list[dict]) -> str:
        lines = [f"아래 {len(items)}개 항목을 평가하세요:\n"]
        for i, item in enumerate(items):
            lines.append(f"[{i}] 제목: {item.get('title', '')}")
            if item.get("source"):
                lines.append(f"    출처: {item['source']}")
            if item.get("summary"):
                lines.append(f"    요약: {item['summary'][:200]}")
            if item.get("url"):
                lines.append(f"    URL: {item['url']}")
        return "\n".join(lines)


def filter_by_threshold(
    items: list[dict], result: CredibilityResult, threshold: int
) -> tuple[list[dict], list[dict]]:
    """
    신뢰도 점수가 threshold 이상인 항목만 (kept, dropped)로 나눠 반환한다.

    평가 자체가 실패했으면 안전하게 전부 통과시킨다(fail-open).
    점수가 매겨진 항목은 원본을 복사해서 credibility_score/credibility_reason을 채워 넣는다.
    """
    if not result.is_success:
        return list(items), []

    kept: list[dict] = []
    dropped: list[dict] = []
    for i, item in enumerate(items):
        score = result.scores.get(i)
        annotated = dict(item)
        if score is not None:
            annotated["credibility_score"] = score
            annotated["credibility_reason"] = result.reasons.get(i, "")
        if score is None or score >= threshold:
            kept.append(annotated)
        else:
            dropped.append(annotated)
    return kept, dropped
