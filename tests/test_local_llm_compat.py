import sys
from pathlib import Path

from research_lab.analyzer.analysis_gpt import AnalysisGPTAnalyzer
from research_lab.analyzer.topic_gpt import TopicAnalyzer


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from mock_openai_server import start_mock_server  # noqa: E402


def test_openai_compatible_loopback_server_supports_topic_and_trend_requests():
    server, _thread = start_mock_server()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    article = {"source": "Test", "title": "Synthetic AI test", "url": "https://example.invalid/test", "kind": "news"}
    try:
        topic = TopicAnalyzer("mock-key", model="mock-local-model", base_url=base_url).analyze(
            "AI", [article], today="2026-08-17", output_language="English"
        )
        analysis = AnalysisGPTAnalyzer("mock-key", model="mock-local-model", base_url=base_url).analyze(
            "AI", [article], output_language="English"
        )
    finally:
        server.shutdown()
        server.server_close()

    assert topic.is_success
    assert topic.suggested_tags == ["local-llm-test"]
    assert analysis.is_success
    assert analysis.confirmed_trends[0]["title"] == "Mock local endpoint"
