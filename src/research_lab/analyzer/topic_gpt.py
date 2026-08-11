"""
topic_gpt.py

사용자가 입력한 주제(경제, 반도체, 부동산 등)에 대한 뉴스 데이터를
GPT로 분석/정리하는 모듈. 기존 analyzer/gpt.py(AI 연구 특화)는 건드리지 않고
별도로 분리했다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from research_lab.i18n import language_instruction

TOPIC_SYSTEM_PROMPT = """당신은 리서치 어시스턴트입니다.
제공된 특정 주제의 최신 뉴스 기사들을 분석해서, 핵심을 빠르게 파악할 수 있도록 정리합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "date": "분석 날짜 (YYYY-MM-DD)",
  "topic": "주제명",
  "trend_summary": ["핵심 동향 요약 1", "핵심 동향 요약 2", "핵심 동향 요약 3"],
  "highlights": [
    {
      "title": "기사 제목",
      "source": "출처",
      "why_important": "왜 주목해야 하는가 (1-2문장)",
      "url": "URL"
    }
  ],
  "key_takeaways": ["시사점/요약 포인트 1", "시사점/요약 포인트 2"],
  "suggested_tags": ["관련 태그1", "관련 태그2"],
  "suggested_search_queries": ["후속 조사에 사용할 검색어 1", "후속 조사에 사용할 검색어 2", "후속 조사에 사용할 검색어 3"]
}"""


@dataclass
class TopicAnalysisResult:
    """주제 뉴스에 대한 GPT 분석 결과."""
    date: str
    topic: str
    trend_summary: list[str]
    highlights: list[dict]
    key_takeaways: list[str]
    suggested_tags: list[str]
    suggested_search_queries: list[str]
    raw_response: str = ""
    error: str = ""

    @property
    def is_success(self) -> bool:
        return not self.error

    @classmethod
    def error_result(cls, error: str, date: str, topic: str) -> "TopicAnalysisResult":
        return cls(
            date=date,
            topic=topic,
            trend_summary=[],
            highlights=[],
            key_takeaways=[],
            suggested_tags=[],
            suggested_search_queries=[],
            error=error,
        )


class TopicAnalyzer:
    """
    GPT API를 이용해 사용자가 입력한 주제의 뉴스를 분석/정리한다.

    사용 예:
        analyzer = TopicAnalyzer(api_key="sk-...")
        result = analyzer.analyze(topic="경제", articles=[...])
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4-nano",
        max_tokens: int = 2000,
        timeout: int = 60,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        # 커스텀 엔드포인트 (사내 프록시, Azure OpenAI 호환 서버, 로컬 LLM 서버 등).
        # 비어있으면 OpenAI 공식 엔드포인트를 그대로 사용한다.
        self.base_url = base_url or None

    def analyze(
        self, topic: str, articles: list[dict], today: str = "", output_language: str = "한국어"
    ) -> TopicAnalysisResult:
        from datetime import date
        if not today:
            today = date.today().isoformat()

        if not articles:
            return TopicAnalysisResult.error_result(
                f"'{topic}' 관련 기사를 찾지 못했습니다. 주제어를 다르게 시도해보세요.",
                today, topic,
            )

        user_message = self._build_user_message(topic, articles, today)
        system_prompt = TOPIC_SYSTEM_PROMPT + language_instruction(output_language)

        try:
            import openai
        except ImportError:
            return TopicAnalysisResult.error_result(
                "openai 패키지 미설치. `uv add openai` 실행 필요.", today, topic
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
                    {"role": "user", "content": user_message},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            return TopicAnalysisResult.error_result(str(e), today, topic)

        raw = response.choices[0].message.content or ""

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return TopicAnalysisResult.error_result(
                f"JSON 파싱 실패: {e}\n{raw[:200]}", today, topic
            )

        return TopicAnalysisResult(
            date=data.get("date", today),
            # 주의: topic은 GPT가 JSON에 적어낸 값이 아니라 항상 사용자가 입력한 원래
            # 주제어를 그대로 사용한다. GPT가 매번 표현을 조금씩 다르게 응답하면
            # (예: "반도체" -> "반도체 산업") topic_formatter가 매번 다른 폴더를
            # 만들어버리는 문제가 있었다.
            topic=topic,
            trend_summary=data.get("trend_summary", []),
            highlights=data.get("highlights", []),
            key_takeaways=data.get("key_takeaways", []),
            suggested_tags=data.get("suggested_tags", []),
            suggested_search_queries=data.get("suggested_search_queries", []),
            raw_response=raw,
        )

    def _build_user_message(self, topic: str, articles: list[dict], today: str) -> str:
        lines = [f"# 주제: {topic} ({today})\n"]
        lines.append(f"## 관련 최신 기사 ({len(articles)}건)")
        for i, a in enumerate(articles, 1):
            kind = a.get("kind", "news")
            lines.append(f"{i}. [{a['title']}]({a['url']}) - {a.get('source', '')} [자료유형: {kind}]")
            if a.get("summary"):
                lines.append(f"   요약: {a['summary']}")
            if a.get("date"):
                lines.append(f"   날짜: {a['date']}")
        lines.append("")
        gossip_count = sum(1 for a in articles if a.get("kind") == "gossip")
        lines.append(
            f"수집 자료 중 개인/커뮤니티성 자료는 {gossip_count}건입니다. 이 자료는 사실로 단정하지 말고 "
            "주장·여론·소문·개인 의견의 신호로 취급하세요.\n"
            "위 자료들을 분석해서 요청한 JSON 형식으로 응답해주세요.\n"
            "highlights는 최대 5개로 제한하고, gossip 자료를 근거로 삼을 때는 사실 확인이 필요한 주장임을 명시하세요. "
            "suggested_search_queries에는 이 주제를 더 조사하기 위한 검색어 3개를 제안하세요. "
            "이 검색어는 반드시 사용자가 지정한 output_language로 작성하세요. English라면 영어 검색어를, 日本語라면 일본어 검색어를 사용하세요. "
            "검색어는 짧고 실제 Google 검색창에 바로 붙여 넣을 수 있는 형태로 작성하세요."
        )
        return "\n".join(lines)
