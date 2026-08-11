#!/usr/bin/env python3
"""Run weighted trend Analysis on the latest Topic Research source snapshot."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_lab.analyzer.analysis_engine import AnalysisGPTAnalyzer, apply_weights, prepare_sources
from research_lab.digest.analysis_formatter import save_analysis
from research_lab.digest.topic_formatter import _slugify
from research_lab.i18n import DEFAULT_OUTPUT_LANGUAGE, resolve_ui_lang


def load_api_key():
    from research_lab.utils.env import load_env_value
    return load_env_value("OPENAI_API_KEY")

def load_api_base():
    from research_lab.utils.env import load_env_value
    return load_env_value("OPENAI_API_BASE") or None


def _history_key(title: str, tags: list[str]) -> str:
    normalized = " ".join(title.lower().split()) + "|" + "|".join(sorted(t.lower().strip() for t in tags))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]

def main():
    p = argparse.ArgumentParser(description="Weighted Topic Trend Analysis")
    p.add_argument("--topic", required=True)
    p.add_argument("--input", default=None, help="Topic Research source snapshot JSON")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--vault-name", default="vault")
    p.add_argument("--model", default="gpt-5.4-nano")
    p.add_argument("--format", default="obsidian")
    p.add_argument("--output-language", default=DEFAULT_OUTPUT_LANGUAGE)
    p.add_argument("--reliability-weight", type=float, default=0.5)
    p.add_argument("--freshness-weight", type=float, default=0.3)
    p.add_argument("--early-signal-weight", type=float, default=0.2)
    args = p.parse_args()
    vault_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "vault"
    input_path = Path(args.input) if args.input else vault_dir / "topics" / _slugify(args.topic) / "_analysis_input.json"
    if not input_path.exists():
        print(f"ERROR: Topic Research source snapshot not found: {input_path}")
        print("Run Topic Research once before Analysis.")
        return 2
    data = json.loads(input_path.read_text(encoding="utf-8"))
    sources = prepare_sources(data.get("articles", []))
    if not sources:
        print("ERROR: No source articles available.")
        return 2
    key = load_api_key()
    if not key:
        print("ERROR: OPENAI_API_KEY is missing.")
        return 2
    analyzer = AnalysisGPTAnalyzer(key, model=args.model, base_url=load_api_base())
    gpt = analyzer.analyze(args.topic, sources, args.output_language)
    if not gpt.is_success:
        print(f"ERROR: Analysis failed: {gpt.error}")
        return 1
    result = apply_weights(gpt, sources, args.reliability_weight, args.freshness_weight, args.early_signal_weight)
    path = save_analysis(result, args.topic, date.today().isoformat(), vault_dir, args.format, resolve_ui_lang(args.output_language))
    # Keep a machine-readable latest result for the GUI and future re-analysis.
    topic_dir = vault_dir / "topics" / _slugify(args.topic)
    latest = topic_dir / "_analysis_latest.json"
    latest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keep a compact historical series so the GUI can visualize category transitions
    # (Rumor -> Emerging Signal -> Confirmed Trend) across repeated analyses.
    history_path = topic_dir / "_analysis_history.json"
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

    def compact_items(items):
        rows = []
        for item in items:
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            tags = [str(t.get("tag", t)) for t in item.get("tags", [])]
            rows.append({
                "title": title,
                "key": _history_key(title, tags),
                "confidence": float(item.get("confidence", 0)),
                "weight": float(item.get("weight", 0)),
                "tags": tags,
            })
        return rows

    snapshot = {
        "date": date.today().isoformat(),
        "generated_at": result.get("generated_at"),
        "confirmed_trends": compact_items(result.get("confirmed_trends", [])),
        "emerging_signals": compact_items(result.get("emerging_signals", [])),
        "rumors": compact_items(result.get("rumors", [])),
    }
    history.append(snapshot)
    # Keep enough history for a useful trend chart without growing indefinitely.
    history = history[-30:]
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ANALYSIS_OUTPUT={path}")
    print(f"Confirmed Trend: {len(result['confirmed_trends'])}")
    print(f"Emerging Signal: {len(result['emerging_signals'])}")
    print(f"Rumor: {len(result['rumors'])}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
