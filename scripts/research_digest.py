#!/usr/bin/env python3
"""
research_digest.py

AI 연구 다이제스트 파이프라인.

흐름:
  1. AI Times 최신 기사 크롤링
  2. HuggingFace 트렌딩 모델 크롤링
  3. GPT-4.1-nano로 분석
  4. vault/digest/YYYY-MM-DD.md 로 저장 (Obsidian 형식)
  5. (선택) --apply-nodes: 제안된 노드를 Knowledge Graph에 추가

사용법:
    uv run python scripts/research_digest.py
    uv run python scripts/research_digest.py --articles 10 --models 10
    uv run python scripts/research_digest.py --dry-run      # 크롤링만, API 호출 없음
    uv run python scripts/research_digest.py --apply-nodes  # 노드 자동 추가
"""

import argparse
import json
import os
import sys
import urllib.parse
import webbrowser
from datetime import date
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

# Windows 콘솔 기본 코드페이지(cp949 등)에서는 이모지 출력 시 UnicodeEncodeError가
# 발생할 수 있어, 표준출력/에러를 UTF-8로 강제 전환한다.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

from research_lab.crawler.aitimes import AITimesCrawler
from research_lab.crawler.huggingface import HuggingFaceCrawler
from research_lab.analyzer.gpt import GPTAnalyzer, AnalysisResult
from research_lab.analyzer.credibility import CredibilityScorer, filter_by_threshold
from research_lab.export.multi_format import save_digest, EXPORT_FORMATS, DEFAULT_FORMAT
from research_lab.i18n import resolve_ui_lang, DEFAULT_OUTPUT_LANGUAGE
from research_lab.knowledge.graph import KnowledgeGraph, Node, Edge, RelationType


def load_api_key() -> str:
    """환경변수 또는 .env 파일에서 API 키를 로드한다."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(APP_DATA_ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일에 OPENAI_API_KEY=sk-... 를 추가하세요.")
        sys.exit(1)
    return key


def load_api_base() -> str | None:
    """환경변수 또는 .env 파일에서 커스텀 API Base URL을 로드한다 (선택 사항)."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(APP_DATA_ROOT / ".env")
    except ImportError:
        pass
    base = os.environ.get("OPENAI_API_BASE", "").strip()
    return base or None


def apply_nodes_to_graph(result: AnalysisResult, graph_path: Path) -> None:
    """분석 결과의 suggested_nodes를 Knowledge Graph에 추가한다."""
    if not result.suggested_nodes:
        print("  ℹ️  추가할 노드가 없습니다.")
        return

    with KnowledgeGraph.open(graph_path) as kg:
        added = 0
        for node_data in result.suggested_nodes:
            node_id = node_data.get("id", "").strip()
            title   = node_data.get("title", "").strip()
            content = node_data.get("content", "").strip()
            tags    = node_data.get("tags", [])

            if not node_id or not title:
                continue

            # 이미 존재하면 스킵
            if kg.get_node(node_id):
                print(f"  ✓ skip (이미 존재): {node_id}")
                continue

            kg.add_node(Node(
                id=node_id,
                title=title,
                content=content,
                tags=tags,
                source=f"AI Research Digest {result.date}",
            ))
            print(f"  ✅ 추가됨: {node_id} ({title})")
            added += 1

    print(f"\n  Knowledge Graph에 {added}개 노드 추가 완료.")


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def open_in_obsidian(vault_name: str, vault_dir: Path, out_path: Path) -> None:
    """생성된 다이제스트 파일을 Obsidian 앱에서 바로 연다."""
    try:
        rel_path = out_path.relative_to(vault_dir).with_suffix("")
        rel_str = rel_path.as_posix()  # 옵시디언 URI는 항상 '/' 구분자 사용
        uri = (
            "obsidian://open?"
            f"vault={urllib.parse.quote(vault_name)}"
            f"&file={urllib.parse.quote(rel_str)}"
        )
        opened = webbrowser.open(uri)
        if opened:
            print(f"  🔗 Obsidian에서 열었습니다: {rel_str}")
        else:
            print(f"  ⚠️  Obsidian 자동 실행 실패. 직접 열어주세요: {out_path}")
    except Exception as e:
        print(f"  ⚠️  Obsidian 자동 실행 중 오류: {e}")
        print(f"     직접 열어주세요: {out_path}")


def open_output(fmt: str, vault_name: str, vault_dir: Path, out_path: Path) -> None:
    """저장 형식에 맞는 방법으로 결과 파일을 열어준다.

    - obsidian: 기존과 동일하게 obsidian:// URI로 앱을 직접 연다.
    - html: 기본 브라우저로 연다.
    - 그 외(markdown/text/json): OS 기본 프로그램으로 열어보고, 실패하면 경로만 안내한다.
    """
    if fmt == "obsidian":
        open_in_obsidian(vault_name, vault_dir, out_path)
        return

    if fmt == "html":
        try:
            if webbrowser.open(out_path.resolve().as_uri()):
                print(f"  🔗 브라우저에서 열었습니다: {out_path}")
                return
        except Exception:
            pass

    try:
        if sys.platform == "win32":
            os.startfile(str(out_path))  # type: ignore[attr-defined]
            print(f"  🔗 기본 프로그램으로 열었습니다: {out_path}")
        else:
            print(f"  ℹ️  저장됨: {out_path}")
    except Exception:
        print(f"  ℹ️  저장됨: {out_path}")


def run_credibility_check(
    items: list[dict], label: str, api_key: str, model: str, base_url: str | None, threshold: int
) -> list[dict]:
    """items(기사 또는 모델 목록)의 신뢰도를 평가하고 임계값 미만 항목을 걸러낸다.

    평가 자체가 실패하면(네트워크/파싱 오류 등) 안전하게 원본을 그대로 반환한다.
    """
    scorer = CredibilityScorer(api_key=api_key, model=model, base_url=base_url)
    result = scorer.score(items)

    if not result.is_success:
        print(f"  ⚠️  {label} 신뢰성 평가 실패 (그대로 진행): {result.error}")
        return items

    kept, dropped = filter_by_threshold(items, result, threshold)
    if dropped:
        print(f"  ⚠️  {label} 중 신뢰도 낮음으로 제외된 항목 {len(dropped)}개 (임계값 {threshold}):")
        for d in dropped:
            print(f"     · [{d.get('credibility_score')}점] {d['title'][:50]}")
    print(f"  → {label} 신뢰성 평가 통과: {len(kept)}/{len(items)}개")
    return kept


def main():
    parser = argparse.ArgumentParser(description="AI 연구 다이제스트 파이프라인")
    parser.add_argument("--articles", type=int, default=5, help="AI Times 기사 수 (기본: 5)")
    parser.add_argument("--models",   type=int, default=5, help="HuggingFace 모델 수 (기본: 5)")
    parser.add_argument("--model",    default="gpt-5.4-nano", help="GPT 모델명 (기본: gpt-5.4-nano)")
    parser.add_argument("--api-base", default=None, help="커스텀 OpenAI API Base URL (기본: .env의 OPENAI_API_BASE 또는 공식 엔드포인트)")
    parser.add_argument("--dry-run",  action="store_true", help="크롤링만 실행 (GPT 호출 없음)")
    parser.add_argument("--apply-nodes", action="store_true", help="제안 노드를 Knowledge Graph에 추가")
    parser.add_argument("--output-dir", default=None, help="저장 경로 (기본: vault/)")
    parser.add_argument("--vault-name", default="vault", help="Obsidian Vault 이름 (기본: vault)")
    parser.add_argument("--no-open", action="store_true", help="완료 후 자동 실행 생략")
    parser.add_argument(
        "--format", default=DEFAULT_FORMAT, choices=EXPORT_FORMATS,
        help=f"저장 형식 (기본: {DEFAULT_FORMAT}, 선택: {', '.join(EXPORT_FORMATS)})",
    )
    parser.add_argument(
        "--credibility-check", action="store_true",
        help="크롤링된 항목의 신뢰성을 GPT로 평가해서 필터링 (추가 API 호출 발생)",
    )
    parser.add_argument(
        "--credibility-threshold", type=int, default=40,
        help="신뢰성 평가 통과 최소 점수 0~100 (기본: 40, 낮을수록 더 많이 허용)",
    )
    parser.add_argument(
        "--output-language", default=DEFAULT_OUTPUT_LANGUAGE,
        help=(
            f"다이제스트 내용을 작성할 언어 (기본: {DEFAULT_OUTPUT_LANGUAGE}). "
            "자유롭게 지정 가능 (예: English, 日本語, 中文). "
            "단, 파일의 고정 틀 문구(섹션 제목 등)는 한국어/English만 지원하며, "
            "이 값이 한국어가 아니면 전부 English로 표시됩니다."
        ),
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    vault_dir  = Path(args.output_dir) if args.output_dir else APP_DATA_ROOT / "vault"
    graph_path = vault_dir / "knowledge_graph.json"
    run_credibility = args.credibility_check and not args.dry_run
    total_steps = 3 if args.dry_run else (5 if run_credibility else 4)

    print(f"\n{'='*50}")
    print(f"  🤖 AI Research Digest — {today}")
    print(f"{'='*50}")

    # ── Step 1: AI Times 크롤링 ───────────────────────────────────────────
    step(1, total_steps, f"AI Times 크롤링 ({args.articles}개)")
    aitimes_crawler = AITimesCrawler()
    articles = aitimes_crawler.fetch(limit=args.articles)
    print(f"  → {len(articles)}개 기사 수집")
    for a in articles:
        print(f"     · {a['title'][:60]}")

    # ── Step 2: HuggingFace 크롤링 ────────────────────────────────────────
    step(2, total_steps, f"HuggingFace 트렌딩 크롤링 ({args.models}개)")
    hf_crawler = HuggingFaceCrawler()
    hf_models  = hf_crawler.fetch(limit=args.models)
    print(f"  → {len(hf_models)}개 모델 수집")
    for m in hf_models:
        print(f"     · {m['title'][:60]}")

    # dry-run 종료 (신뢰성 평가도 GPT 호출이라 dry-run에서는 건너뛴다)
    if args.dry_run:
        step(3, total_steps, "dry-run 완료 (GPT 호출 생략)")
        print("\n  크롤링 데이터:")
        print(json.dumps({"articles": articles, "models": hf_models},
                         ensure_ascii=False, indent=2))
        return

    api_key  = load_api_key()
    api_base = args.api_base or load_api_base()
    step_n = 2

    # ── (선택) Step: 신뢰성 평가 ───────────────────────────────────────────
    if run_credibility:
        step_n += 1
        step(step_n, total_steps, f"신뢰성 평가 (임계값 {args.credibility_threshold})")
        articles = run_credibility_check(
            articles, "AI Times 기사", api_key, args.model, api_base, args.credibility_threshold
        )
        hf_models = run_credibility_check(
            hf_models, "HuggingFace 모델", api_key, args.model, api_base, args.credibility_threshold
        )

    # ── Step: GPT 분석 ────────────────────────────────────────────────────
    step_n += 1
    step(step_n, total_steps, f"GPT 분석 ({args.model}, 출력 언어: {args.output_language})")
    analyzer = GPTAnalyzer(api_key=api_key, model=args.model, base_url=api_base)
    result   = analyzer.analyze(
        articles=articles, models=hf_models, today=today, output_language=args.output_language
    )

    if not result.is_success:
        print(f"  ❌ GPT 분석 실패: {result.error}")
        sys.exit(1)

    print(f"  → 분석 완료")
    print(f"     트렌드: {len(result.trend_summary)}개")
    print(f"     하이라이트: {len(result.highlights)}개")
    print(f"     노드 제안: {len(result.suggested_nodes)}개")

    # ── Step: 파일 저장 ────────────────────────────────────────────────────
    step_n += 1
    step(step_n, total_steps, f"파일 저장 ({args.format})")
    ui_lang = resolve_ui_lang(args.output_language)
    out_path = save_digest(result, vault_dir, args.format, lang=ui_lang)
    print(f"  ✅ 저장됨: {out_path}")

    # ── (선택) 노드 추가 ──────────────────────────────────────────────────
    if args.apply_nodes and result.suggested_nodes:
        print(f"\n[+] Knowledge Graph 노드 추가")
        apply_nodes_to_graph(result, graph_path)

    # ── 결과 파일 자동 실행 ───────────────────────────────────────────────
    if not args.no_open:
        open_output(args.format, args.vault_name, vault_dir, out_path)

    print(f"\n{'='*50}")
    print(f"  완료! {out_path} 를 확인해보세요.")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
