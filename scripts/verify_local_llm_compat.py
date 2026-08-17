#!/usr/bin/env python3
"""Run the no-model OpenAI-compatible endpoint compatibility smoke test."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_openai_server import start_mock_server
from research_lab.analyzer.analysis_gpt import AnalysisGPTAnalyzer
from research_lab.analyzer.topic_gpt import TopicAnalyzer
from research_lab.digest.topic_formatter import TopicDigestFormatter


def main() -> int:
    server, _thread = start_mock_server()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        article = {
            "source": "Compatibility Test",
            "title": "Synthetic local endpoint test article",
            "url": "https://example.invalid/local-llm-test",
            "summary": "No external model or source is used.",
            "date": "20260817T000000Z",
            "kind": "news",
        }
        topic_result = TopicAnalyzer("mock-key", model="mock-local-model", base_url=base_url).analyze(
            "AI", [article], today="2026-08-17", output_language="English"
        )
        if not topic_result.is_success:
            print(f"FAIL: Topic Research compatibility check failed: {topic_result.error}")
            return 1
        with tempfile.TemporaryDirectory() as directory:
            output = TopicDigestFormatter(Path(directory), lang="en").save(topic_result)
            if not output.exists():
                print("FAIL: Topic Research result was not written to Markdown.")
                return 1
        analysis_result = AnalysisGPTAnalyzer("mock-key", model="mock-local-model", base_url=base_url).analyze(
            "AI", [article], output_language="English"
        )
        if not analysis_result.is_success:
            print(f"FAIL: Trend Analysis compatibility check failed: {analysis_result.error}")
            return 1
        print(f"PASS: OpenAI-compatible local endpoint works at {base_url}")
        print("Verified: Topic Research request/JSON/Markdown and Trend Analysis request/JSON.")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
