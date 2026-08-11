"""
gpt.py

GPT API 호출 모듈.
크롤링된 AI 동향 데이터를 받아서 구조화된 분석 결과를 반환한다.

분석 항목:
- 핵심 트렌드 요약 (3줄)
- 주목할 모델/기사 TOP 3
- 연구 시사점 (특허법/IP 관점 포함)
- Knowledge Graph에 추가할 노드 제안
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from research_lab.i18n import language_instruction

ANALYSIS_SYSTEM_PROMPT = """당신은 AI 연구 파트너입니다.
제공된 최신 AI 동향 데이터를 분석하고, 연구자에게 유용한 인사이트를 제공합니다.

분석 관점:
1. 기술적 트렌드 (어떤 기술이 주목받는가)
2. 연구 시사점 (학술/연구 관점에서 중요한 것)
3. IP/특허 관점 (새로운 기술이 특허법/IP 전략에 미치는 영향)

반드시 아래 JSON 형식으로만 응답하세요:
{
  "date": "분석 날짜 (YYYY-MM-DD)",
  "trend_summary": ["트렌드 요약 1", "트렌드 요약 2", "트렌드 요약 3"],
  "highlights": [
    {
      "title": "모델/기사명",
      "source": "출처",
      "why_important": "왜 중요한가 (1-2문장)",
      "url": "URL"
    }
  ],
  "research_implications": ["연구 시사점 1", "연구 시사점 2"],
  "ip_perspective": "IP/특허 관점에서의 분석 (2-3문장)",
  "suggested_nodes": [
    {
      "id": "노드_id (영어, 언더스코어)",
      "title": "노드 제목",
      "content": "노드 내용",
      "tags": ["태그1", "태그2"]
    }
  ]
}"""


@dataclass
class AnalysisResult:
    """GPT 분석 결과."""
    date: str
    trend_summary: list[str]
    highlights: list[dict]
    research_implications: list[str]
    ip_perspective: str
    suggested_nodes: list[dict]
    raw_response: str = ""
    error: str = ""

    @property
    def is_success(self) -> bool:
        return not self.error

    @classmethod
    def error_result(cls, error: str, date: str) -> "AnalysisResult":
        return cls(
            date=date,
            trend_summary=[],
            highlights=[],
            research_implications=[],
            ip_perspective="",
            suggested_nodes=[],
            error=error,
        )


class GPTAnalyzer:
    """
    GPT API를 이용한 AI 동향 분석기.

    사용 예:
        analyzer = GPTAnalyzer(api_key="sk-...")
        result = analyzer.analyze(articles=[], models=[])
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4-nano",
        max_tokens: int = 2000,
        timeout: int = 60,
        base_url: str | None = None,
    ) -> None:
        self.api_key  = api_key
        self.model    = model
        self.max_tokens = max_tokens
        self.timeout  = timeout
        # 커스텀 엔드포인트 (사내 프록시, Azure OpenAI 호환 서버, 로컬 LLM 서버 등).
        # 비어있으면 OpenAI 공식 엔드포인트를 그대로 사용한다.
        self.base_url = base_url or None

    def analyze(
        self,
        articles: list[dict],
        models: list[dict],
        today: str = "",
        output_language: str = "한국어",
    ) -> AnalysisResult:
        """
        크롤링 데이터를 GPT에 보내서 분석 결과를 받아온다.

        Args:
            articles: AITimesCrawler에서 받은 기사 목록
            models:   HuggingFaceCrawler에서 받은 모델 목록
            today:    날짜 문자열 (YYYY-MM-DD), 비어있으면 오늘 날짜
            output_language: 응답 내용(trend_summary, highlights 등)을 작성할 언어.
                              "한국어"(기본), "English", "日本語" 등 자유롭게 지정 가능.
        """
        from datetime import date
        if not today:
            today = date.today().isoformat()

        user_message = self._build_user_message(articles, models, today)
        system_prompt = ANALYSIS_SYSTEM_PROMPT + language_instruction(output_language)

        try:
            import openai
        except ImportError:
            return AnalysisResult.error_result(
                "openai 패키지 미설치. `uv add openai` 실행 필요.", today
            )

        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            return AnalysisResult.error_result(str(e), today)

        raw = response.choices[0].message.content or ""

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return AnalysisResult.error_result(f"JSON 파싱 실패: {e}\n{raw[:200]}", today)

        return AnalysisResult(
            date=data.get("date", today),
            trend_summary=data.get("trend_summary", []),
            highlights=data.get("highlights", []),
            research_implications=data.get("research_implications", []),
            ip_perspective=data.get("ip_perspective", ""),
            suggested_nodes=data.get("suggested_nodes", []),
            raw_response=raw,
        )

    def _build_user_message(
        self,
        articles: list[dict],
        models: list[dict],
        today: str,
    ) -> str:
        """GPT에 보낼 사용자 메시지를 구성한다."""
        lines = [f"# AI 동향 데이터 ({today})\n"]

        if articles:
            lines.append("## AI Times 최신 기사")
            for i, a in enumerate(articles, 1):
                lines.append(f"{i}. [{a['title']}]({a['url']})")
                if a.get("summary"):
                    lines.append(f"   요약: {a['summary']}")
                if a.get("category"):
                    lines.append(f"   카테고리: {a['category']}")
            lines.append("")

        if models:
            lines.append("## HuggingFace 트렌딩 모델")
            for i, m in enumerate(models, 1):
                lines.append(f"{i}. [{m['title']}]({m['url']})")
                if m.get("summary"):
                    lines.append(f"   정보: {m['summary']}")
            lines.append("")

        lines.append(
            "위 데이터를 분석해서 요청한 JSON 형식으로 응답해주세요.\n"
            "highlights는 최대 3개, suggested_nodes는 최대 3개로 제한합니다."
        )

        return "\n".join(lines)
