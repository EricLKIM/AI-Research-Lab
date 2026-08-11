"""LLM layer for weighted trend analysis of Topic Research sources."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from research_lab.i18n import language_instruction

ANALYSIS_SYSTEM_PROMPT = """You are an evidence-aware research trend analyst.
Analyze the supplied Topic Research sources without treating model-generated confidence as truth.
Return JSON only.

Goals:
1. Evaluate each source's reliability (0-100) using source quality, evidence, specificity, and verifiability.
2. Identify claims/trends supported by multiple independent sources.
3. Separate findings into exactly three categories:
   - confirmed_trends: well-supported, high-evidence trends. This is NOT a claim of absolute truth.
   - emerging_signals: plausible early signals with incomplete or mixed evidence.
   - rumors: unverified claims, speculation, gossip, or weakly supported reports.
4. Identify contradictions when credible sources disagree.
5. Generate concise tags/topics and assign each tag an aggregate confidence/weight based on the evidence.

Important:
- A fresh source is not automatically reliable.
- A gossip/community source can be useful as an early signal but must not be promoted to confirmed solely because it is recent.
- Multiple copies of the same report are NOT independent evidence.
- Keep source indices so every conclusion can be traced back to the supplied sources.

JSON schema:
{
  "source_assessments": [
    {"index": 0, "reliability": 0, "evidence": 0, "reason": "..."}
  ],
  "confirmed_trends": [
    {"title":"...", "summary":"...", "sentiment":-1.0, "source_indices":[0,2], "tags":["..."], "evidence_score":0}
  ],
  "emerging_signals": [
    {"title":"...", "summary":"...", "sentiment":0.5, "source_indices":[1], "tags":["..."], "evidence_score":0}
  ],
  "rumors": [
    {"title":"...", "summary":"...", "sentiment":0.0, "source_indices":[3], "tags":["..."], "evidence_score":0}
  ],
  "contradictions": [
    {"topic":"...", "summary":"...", "source_indices":[0,4]}
  ],
  "overall_summary":"..."
}
"""

@dataclass
class AnalysisGPTResult:
    source_assessments: list[dict] = field(default_factory=list)
    confirmed_trends: list[dict] = field(default_factory=list)
    emerging_signals: list[dict] = field(default_factory=list)
    rumors: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    overall_summary: str = ""
    raw_response: str = ""
    error: str = ""

    @property
    def is_success(self) -> bool:
        return not self.error

    @classmethod
    def error_result(cls, error: str) -> "AnalysisGPTResult":
        return cls(error=error)

class AnalysisGPTAnalyzer:
    def __init__(self, api_key: str, model: str = "gpt-5.4-nano", timeout: int = 60, base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = base_url or None

    def analyze(self, topic: str, sources: list[dict], output_language: str = "한국어") -> AnalysisGPTResult:
        if not sources:
            return AnalysisGPTResult.error_result("분석할 자료가 없습니다.")
        prompt = self._build_user_message(topic, sources, output_language)
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT + language_instruction(output_language)},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=5000,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            return AnalysisGPTResult.error_result(str(e))
        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return AnalysisGPTResult.error_result(f"JSON 파싱 실패: {e}: {raw[:300]}")
        return AnalysisGPTResult(
            source_assessments=data.get("source_assessments", []),
            confirmed_trends=data.get("confirmed_trends", []),
            emerging_signals=data.get("emerging_signals", []),
            rumors=data.get("rumors", []),
            contradictions=data.get("contradictions", []),
            overall_summary=data.get("overall_summary", ""),
            raw_response=raw,
        )

    def _build_user_message(self, topic: str, sources: list[dict], output_language: str) -> str:
        lines = [f"Topic: {topic}", f"Output language: {output_language}", "", "Sources:"]
        for i, s in enumerate(sources):
            lines.append(
                f"[{i}] title={s.get('title','')} | source={s.get('source','')} | kind={s.get('kind','news')} "
                f"| date={s.get('date','')} | freshness={s.get('freshness_score',0):.2f} "
                f"| baseline_reliability={s.get('baseline_reliability',0):.2f} | url={s.get('url','')}"
            )
            if s.get("summary"):
                lines.append(f"    summary={s['summary'][:1200]}")
        lines.append("\nClassify evidence conservatively and keep source indices traceable.")
        return "\n".join(lines)
