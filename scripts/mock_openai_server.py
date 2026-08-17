#!/usr/bin/env python3
"""A dependency-free loopback server for OpenAI-compatible API smoke tests.

It never runs a model and never forwards requests.  It returns deterministic
JSON for the two chat-completions shapes used by Topic Research and Analysis.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _topic_payload() -> dict:
    return {
        "date": "2026-08-17",
        "topic": "Mock topic",
        "trend_summary": ["Mock endpoint accepted a Topic Research request."],
        "highlights": [],
        "key_takeaways": ["This is a local compatibility test, not research output."],
        "suggested_tags": ["local-llm-test"],
        "suggested_search_queries": ["OpenAI-compatible local endpoint"],
    }


def _analysis_payload() -> dict:
    return {
        "source_assessments": [{"source_index": 0, "reliability": 0.8, "freshness": 0.8}],
        "confirmed_trends": [{"title": "Mock local endpoint", "summary": "Trend Analysis request accepted.", "source_indices": [0], "tags": ["local-llm-test"]}],
        "emerging_signals": [],
        "rumors": [],
        "contradictions": [],
        "overall_summary": "The local OpenAI-compatible request and JSON response path work.",
    }


class MockOpenAIHandler(BaseHTTPRequestHandler):
    server_version = "AIResearchLabMockOpenAI/1.0"

    def log_message(self, format: str, *args) -> None:
        print(f"[Mock OpenAI] {format % args}", flush=True)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._send_json(200, {"object": "list", "data": [{"id": "mock-local-model", "object": "model"}]})
            return
        self._send_json(404, {"error": {"message": "mock endpoint not found"}})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "mock endpoint not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": {"message": "invalid JSON request"}})
            return
        messages = request.get("messages", [])
        user_text = " ".join(str(item.get("content", "")) for item in messages if item.get("role") == "user")
        payload = _analysis_payload() if "Classify evidence conservatively" in user_text else _topic_payload()
        content = json.dumps(payload, ensure_ascii=False)
        self._send_json(200, {
            "id": "mock-chat-completion",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.get("model", "mock-local-model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })


def start_mock_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start a loopback-only server in a daemon thread and return it."""
    server = ThreadingHTTPServer((host, port), MockOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mock-openai-server")
    thread.start()
    return server, thread


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local OpenAI-compatible mock endpoint for AI Research Lab.")
    parser.add_argument("--port", type=int, default=11435)
    args = parser.parse_args()
    server, _thread = start_mock_server(port=args.port)
    print(f"Mock OpenAI server ready: http://127.0.0.1:{server.server_port}/v1", flush=True)
    print("No model is running and no request leaves this computer. Press Ctrl+C to stop.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
