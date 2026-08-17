#!/usr/bin/env python3
"""Run weighted trend Analysis on the latest Topic Research source snapshot."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import date, datetime
from pathlib import Path

def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        configured = os.environ.get("AI_RESEARCH_LAB_HOME")
        if configured:
            return Path(configured).resolve()
        executable_dir = Path(sys.executable).resolve().parent
        for candidate in (executable_dir, *executable_dir.parents):
            if (candidate / "AI Research Lab.exe").exists():
                return candidate
        return executable_dir
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()


def _app_data_root() -> Path:
    if getattr(sys, "frozen", False):
        configured = os.environ.get("AI_RESEARCH_LAB_DATA_HOME")
        if configured:
            return Path(configured).resolve()
        local_app_data = os.environ.get("LOCALAPPDATA")
        return (Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local") / "AI Research Lab"
    return PROJECT_ROOT


APP_DATA_ROOT = _app_data_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# The GUI reads child-process logs as UTF-8.  Force that encoding before any
# Korean alert or analysis text is printed on Windows.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

from research_lab.analyzer.analysis_engine import AnalysisGPTAnalyzer, apply_weights, prepare_sources
from research_lab.analyzer.analysis_context import build_cross_topic_context, load_state, save_state, update_tag_index
from research_lab.analyzer.time_series_analysis import build_time_series_summary
from research_lab.analyzer.analysis_alerts import build_alerts, save_new_alerts
from research_lab.digest.analysis_formatter import save_analysis
from research_lab.digest.topic_formatter import _slugify
from research_lab.i18n import DEFAULT_OUTPUT_LANGUAGE, resolve_ui_lang
from research_lab.tagging import tag_articles


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
    p.add_argument("--data-dir", default=None, help="Machine-readable JSON data directory")
    p.add_argument("--vault-name", default="vault")
    p.add_argument("--model", default="gpt-5.4-nano")
    p.add_argument("--format", default="obsidian")
    p.add_argument("--output-language", default=DEFAULT_OUTPUT_LANGUAGE)
    p.add_argument("--reliability-weight", type=float, default=0.5)
    p.add_argument("--freshness-weight", type=float, default=0.3)
    p.add_argument("--early-signal-weight", type=float, default=0.2)
    p.add_argument("--period-days", type=int, default=30, choices=(7, 30, 90, 180, 365), help="Stored snapshot period used for local trend evidence")
    p.add_argument("--alert-emerging", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--alert-rising", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--alert-contradictions", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--alert-data-quality", action=argparse.BooleanOptionalAction, default=True)
    args = p.parse_args()
    vault_dir = Path(args.output_dir) if args.output_dir else APP_DATA_ROOT / "vault"
    data_dir = Path(args.data_dir) if args.data_dir else vault_dir
    input_path = Path(args.input) if args.input else data_dir / "topics" / _slugify(args.topic) / "_analysis_input.json"
    if not input_path.exists():
        print(f"ERROR: Topic Research source snapshot not found: {input_path}")
        print("Run Topic Research once before Analysis.")
        return 2
    data = json.loads(input_path.read_text(encoding="utf-8"))
    topic_dir = data_dir / "topics" / _slugify(args.topic)
    topic_dir.mkdir(parents=True, exist_ok=True)
    tagged_articles = tag_articles(data.get("articles", []), args.topic)
    sources = prepare_sources(tagged_articles)
    if not sources:
        print("ERROR: No source articles available.")
        return 2
    source_ids = {str(row.get("article_id") or row.get("url") or _history_key(str(row.get("title", "")), [])) for row in sources}
    current_tags = {tag for row in tagged_articles for tag in row.get("normalized_tags", [])}
    cross_context, context_signature = build_cross_topic_context(data_dir, args.topic, current_tags)
    time_series, time_series_signature = build_time_series_summary(topic_dir, args.topic, args.period_days)
    state = load_state(topic_dir)
    if state.get("processed_article_ids") == sorted(source_ids) and state.get("context_signature") == context_signature and state.get("time_series_signature") == time_series_signature:
        cached_path = state.get("output_path") or ""
        print(f"ANALYSIS_CACHED={cached_path}")
        print("Analysis unchanged: no new sources or relevant cross-topic evidence; GPT call skipped.")
        return 0
    previously_processed = set(state.get("processed_article_ids", []))
    new_sources = [source for source in sources if str(source.get("article_id") or source.get("url") or _history_key(str(source.get("title", "")), [])) not in previously_processed]
    # When only the external context changed, retain the latest sources so the
    # model still has traceable evidence for a revised conclusion.
    sources_for_analysis = new_sources or sources
    key = load_api_key()
    if not key:
        print("ERROR: OPENAI_API_KEY is missing.")
        return 2
    analyzer = AnalysisGPTAnalyzer(key, model=args.model, base_url=load_api_base())
    previous = (data_dir / "topics" / _slugify(args.topic) / "_analysis_latest.json")
    previous_summary = ""
    if previous.exists():
        try:
            previous_summary = str(json.loads(previous.read_text(encoding="utf-8")).get("overall_summary", ""))
        except (OSError, json.JSONDecodeError):
            pass
    print(f"Analysis input: {len(sources_for_analysis)} new/current sources; {len(cross_context)} cross-topic evidence rows; {time_series['data_quality']['snapshot_count']} snapshots / {args.period_days} days")
    gpt = analyzer.analyze(args.topic, sources_for_analysis, args.output_language, cross_context, previous_summary, time_series)
    if not gpt.is_success:
        print(f"ERROR: Analysis failed: {gpt.error}")
        return 1
    result = apply_weights(gpt, sources_for_analysis, args.reliability_weight, args.freshness_weight, args.early_signal_weight)
    result["generated_at"] = datetime.now().astimezone().isoformat()
    result["cross_topic_evidence"] = cross_context
    result["time_series"] = time_series
    result["data_quality"] = time_series["data_quality"]
    result["alerts"] = build_alerts(
        result,
        emerging=args.alert_emerging,
        rising=args.alert_rising,
        contradictions=args.alert_contradictions,
        quality=args.alert_data_quality,
    )
    result["analysis_tags"] = sorted({
        str(tag.get("tag", tag)).strip()
        for category in ("confirmed_trends", "emerging_signals", "rumors")
        for item in result.get(category, [])
        for tag in item.get("tags", [])
        if str(tag.get("tag", tag)).strip()
    })
    path = save_analysis(result, args.topic, date.today().isoformat(), vault_dir, args.format, resolve_ui_lang(args.output_language))
    # Keep a machine-readable latest result for the GUI and future re-analysis.
    latest = topic_dir / "_analysis_latest.json"
    latest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    new_alerts = save_new_alerts(topic_dir, result["alerts"])
    update_tag_index(data_dir, args.topic, result, path)
    save_state(topic_dir, source_ids=source_ids, context_signature=context_signature, time_series_signature=time_series_signature, output_path=path)

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
    for alert in new_alerts:
        print(f"[ALERT] {alert['message']}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
