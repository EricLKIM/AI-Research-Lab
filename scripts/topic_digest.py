#!/usr/bin/env python3
"""
topic_digest.py

사용자가 입력한 주제(예: "경제", "반도체", "부동산")로 최신 뉴스를 크롤링하고,
GPT로 분석/정리해서 Obsidian 노트로 저장한다.

흐름:
  1. Google 뉴스 검색 (주제어 기반, 특정 사이트 구조에 의존하지 않음)
  2. GPT로 분석/정리
  3. vault/topics/{주제}/YYYY-MM-DD.md 로 저장 (Obsidian 형식)
  4. Obsidian 자동 실행

사용법:
    uv run python scripts/topic_digest.py --topic "경제"
    uv run python scripts/topic_digest.py --topic "반도체" --limit 15
    uv run python scripts/topic_digest.py --topic "부동산" --dry-run   # 크롤링만, API 호출 없음
"""

import argparse
import json
import os
import sys
import urllib.parse
import webbrowser
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Windows 콘솔 기본 코드페이지(cp949 등)에서는 이모지 출력 시 UnicodeEncodeError가
# 발생할 수 있어, 표준출력/에러를 UTF-8로 강제 전환한다.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

from research_lab.crawler.topic_news import TopicNewsCrawler
from research_lab.analyzer.topic_gpt import TopicAnalyzer
from research_lab.analyzer.credibility import CredibilityScorer, filter_by_threshold
from research_lab.export.multi_format import save_topic_digest, EXPORT_FORMATS, DEFAULT_FORMAT
from research_lab.digest.topic_formatter import _slugify
from research_lab.i18n import resolve_ui_lang, DEFAULT_OUTPUT_LANGUAGE, google_search_profile
from research_lab.utils.favorites import TopicFavorites


def load_api_key() -> str:
    """환경변수 또는 .env 파일에서 API 키를 로드한다."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
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
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    base = os.environ.get("OPENAI_API_BASE", "").strip()
    return base or None


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def console_strings(output_language: str | None) -> dict[str, str]:
    """Return fixed console UI strings. Korean uses Korean; every other language falls back to English."""
    if resolve_ui_lang(output_language) == "ko":
        return {
            "saved_topics_empty": "저장된 주제가 없습니다.",
            "manage_prompt": "삭제할 주제 번호를 입력하세요 (취소하려면 그냥 엔터)",
            "number": "번호",
            "invalid_number": "올바른 번호가 아닙니다.",
            "deleted": "'{topic}' 삭제했습니다.",
            "topic_menu_title": "🔎 주제 리서치 — 저장된 주제 목록",
            "new_topic": "+ 새 주제 입력",
            "manage_topics": "저장된 주제 관리 (삭제)",
            "choose_number": "번호를 선택하세요:",
            "enter_number": "숫자를 입력해주세요.",
            "enter_new_topic": "새 주제를 입력하세요:",
            "topic_missing": "주제가 입력되지 않았습니다.",
            "save_favorite": "'{topic}'을(를) 즐겨찾기에 저장할까요? (Y/n):",
            "saved_favorite": "즐겨찾기에 저장했습니다.",
            "choose_valid": "올바른 번호를 선택해주세요.",
            "obsidian_opened": "Obsidian에서 열었습니다: {path}",
            "obsidian_failed": "Obsidian 자동 실행 실패. 직접 열어주세요: {path}",
            "obsidian_error": "Obsidian 자동 실행 중 오류: {error}",
            "open_browser": "브라우저에서 열었습니다: {path}",
            "opened_default": "기본 프로그램으로 열었습니다: {path}",
            "saved": "저장됨: {path}",
            "credibility_failed": "{label} 신뢰성 평가 실패 (그대로 진행): {error}",
            "credibility_dropped": "{label} 중 신뢰도 낮음으로 제외된 항목 {count}개 (임계값 {threshold}):",
            "credibility_passed": "{label} 신뢰성 평가 통과: {kept}/{total}개",
            "credibility_score": "[{score}점] {title}",
            "search": "'{topic}' 관련 뉴스 검색 ({limit}개)",
            "google_profile": "Google 검색 언어/지역: {lang} / {country} (가십 비율 {ratio}%)",
            "collected": "{count}개 기사 수집",
            "no_articles": "관련 기사를 찾지 못했습니다. 주제어를 다르게 시도해보세요.",
            "dry_run": "dry-run 완료 (GPT 호출 생략)",
            "crawl_data": "크롤링 데이터:",
            "credibility": "신뢰성 평가 (임계값 {threshold})",
            "no_articles_after_credibility": "신뢰성 평가 후 남은 기사가 없습니다. 임계값을 낮춰보세요.",
            "gpt": "GPT 분석 ({model}, 출력 언어: {language})",
            "gpt_failed": "GPT 분석 실패: {error}",
            "analysis_done": "분석 완료",
            "trends": "핵심 동향: {count}개",
            "highlights": "주요 기사: {count}개",
            "saving": "파일 저장 ({format})",
            "saved_check": "저장됨: {path}",
            "done": "완료! {path} 를 확인해보세요.",
        }
    return {
        "saved_topics_empty": "No saved topics.",
        "manage_prompt": "Enter the number of the topic to delete (press Enter to cancel)",
        "number": "Number",
        "invalid_number": "Invalid number.",
        "deleted": "Deleted '{topic}'.",
        "topic_menu_title": "🔎 Topic Research — Saved Topics",
        "new_topic": "+ Enter a new topic",
        "manage_topics": "Manage saved topics (delete)",
        "choose_number": "Choose a number:",
        "enter_number": "Please enter a number.",
        "enter_new_topic": "Enter a new topic:",
        "topic_missing": "No topic was entered.",
        "save_favorite": "Save '{topic}' to Favorites? (Y/n):",
        "saved_favorite": "Saved to Favorites.",
        "choose_valid": "Please choose a valid number.",
        "obsidian_opened": "Opened in Obsidian: {path}",
        "obsidian_failed": "Could not open Obsidian automatically. Please open it manually: {path}",
        "obsidian_error": "Error while opening Obsidian: {error}",
        "open_browser": "Opened in browser: {path}",
        "opened_default": "Opened with the default application: {path}",
        "saved": "Saved: {path}",
        "credibility_failed": "{label} credibility check failed (continuing): {error}",
        "credibility_dropped": "{count} low-credibility {label} item(s) excluded (threshold {threshold}):",
        "credibility_passed": "{label} credibility check passed: {kept}/{total}",
        "credibility_score": "[{score} points] {title}",
        "search": "Search news related to '{topic}' ({limit} results)",
        "google_profile": "Google search language/region: {lang} / {country} (gossip ratio {ratio}%)",
        "collected": "Collected {count} articles",
        "no_articles": "No relevant articles were found. Try a different topic.",
        "dry_run": "dry-run complete (GPT call skipped)",
        "crawl_data": "Crawled data:",
        "credibility": "Credibility check (threshold {threshold})",
        "no_articles_after_credibility": "No articles remain after the credibility check. Try lowering the threshold.",
        "gpt": "GPT analysis ({model}, output language: {language})",
        "gpt_failed": "GPT analysis failed: {error}",
        "analysis_done": "Analysis complete",
        "trends": "Key trends: {count}",
        "highlights": "Top articles: {count}",
        "saving": "Save file ({format})",
        "saved_check": "Saved: {path}",
        "done": "Done! Check: {path}",
    }


def _manage_favorites(favorites: TopicFavorites) -> None:
    """즐겨찾기 목록에서 항목을 삭제한다."""
    ui = console_strings(favorites.lang)
    topics = favorites.load()
    if not topics:
        print(f"  {ui['saved_topics_empty']}")
        return
    print(f"\n  {ui['manage_prompt']}")
    for i, t in enumerate(topics, 1):
        print(f"    {i}) {t}")
    choice = input(f"  {ui['number']}: ").strip()
    if not choice:
        return
    if choice.isdigit() and 1 <= int(choice) <= len(topics):
        removed = topics[int(choice) - 1]
        favorites.remove(int(choice) - 1)
        print(f"  🗑️  {ui['deleted'].format(topic=removed)}")
    else:
        print(f"  ⚠️  {ui['invalid_number']}")


def select_topic_interactively(fav_path: Path, output_language: str = DEFAULT_OUTPUT_LANGUAGE) -> str:
    """저장된 주제 목록에서 번호로 선택하거나, 새 주제를 입력받는다.

    새로 입력한 주제는 원하면 즐겨찾기에 저장되어 다음부터는 매번
    타이핑하지 않고 번호만 선택하면 된다.
    """
    favorites = TopicFavorites(fav_path, output_language)
    ui = console_strings(output_language)

    while True:
        topics = favorites.load()

        print("\n" + "=" * 50)
        print(f"  {ui['topic_menu_title']}")
        print("=" * 50)
        for i, t in enumerate(topics, 1):
            print(f"  {i}) {t}")
        new_idx = len(topics) + 1
        manage_idx = len(topics) + 2
        print(f"  {new_idx}) {ui['new_topic']}")
        if topics:
            print(f"  {manage_idx}) {ui['manage_topics']}")
        print("-" * 50)

        choice = input(ui['choose_number'] + " ").strip()

        if not choice.isdigit():
            print(f"  ⚠️  {ui['enter_number']}")
            continue

        choice_num = int(choice)

        if 1 <= choice_num <= len(topics):
            return topics[choice_num - 1]

        if choice_num == new_idx:
            new_topic = input(ui['enter_new_topic'] + " ").strip()
            if not new_topic:
                print(f"  ⚠️  {ui['topic_missing']}")
                continue
            save = input(ui['save_favorite'].format(topic=new_topic) + " ").strip().lower()
            if save != "n":
                favorites.add(new_topic)
                print(f"  ✅ {ui['saved_favorite']}")
            return new_topic

        if topics and choice_num == manage_idx:
            _manage_favorites(favorites)
            continue

        print(f"  ⚠️  {ui['choose_valid']}")


def open_in_obsidian(vault_name: str, vault_dir: Path, out_path: Path, output_language: str) -> None:
    """Open the generated digest in Obsidian."""
    ui = console_strings(output_language)
    try:
        rel_path = out_path.relative_to(vault_dir).with_suffix("")
        rel_str = rel_path.as_posix()
        uri = (
            "obsidian://open?"
            f"vault={urllib.parse.quote(vault_name)}"
            f"&file={urllib.parse.quote(rel_str)}"
        )
        opened = webbrowser.open(uri)
        if opened:
            print(f"  🔗 {ui['obsidian_opened'].format(path=rel_str)}")
        else:
            print(f"  ⚠️  {ui['obsidian_failed'].format(path=out_path)}")
    except Exception as e:
        print(f"  ⚠️  {ui['obsidian_error'].format(error=e)}")
        print(f"     {ui['obsidian_failed'].format(path=out_path)}")


def open_output(fmt: str, vault_name: str, vault_dir: Path, out_path: Path, output_language: str) -> None:
    """Open the result file using the selected format."""
    ui = console_strings(output_language)
    if fmt == "obsidian":
        open_in_obsidian(vault_name, vault_dir, out_path, output_language)
        return

    if fmt == "html":
        try:
            if webbrowser.open(out_path.resolve().as_uri()):
                print(f"  🔗 {ui['open_browser'].format(path=out_path)}")
                return
        except Exception:
            pass

    try:
        if sys.platform == "win32":
            os.startfile(str(out_path))  # type: ignore[attr-defined]
            print(f"  🔗 {ui['opened_default'].format(path=out_path)}")
        else:
            print(f"  ℹ️  {ui['saved'].format(path=out_path)}")
    except Exception:
        print(f"  ℹ️  {ui['saved'].format(path=out_path)}")


def run_credibility_check(
    items: list[dict], label: str, api_key: str, model: str, base_url: str | None, threshold: int, output_language: str
) -> list[dict]:
    """items의 신뢰도를 평가하고 임계값 미만 항목을 걸러낸다 (평가 실패 시 fail-open)."""
    ui = console_strings(output_language)
    scorer = CredibilityScorer(api_key=api_key, model=model, base_url=base_url)
    result = scorer.score(items)

    if not result.is_success:
        print(f"  ⚠️  {ui['credibility_failed'].format(label=label, error=result.error)}")
        return items

    kept, dropped = filter_by_threshold(items, result, threshold)
    if dropped:
        print(f"  ⚠️  {ui['credibility_dropped'].format(label=label, count=len(dropped), threshold=threshold)}")
        for d in dropped:
            print(f"     · {ui['credibility_score'].format(score=d.get('credibility_score'), title=d['title'][:50])}")
    print(f"  → {ui['credibility_passed'].format(label=label, kept=len(kept), total=len(items))}")
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description="주제 기반 뉴스 리서치 다이제스트")
    parser.add_argument("--topic", default=None, help="검색할 주제 (생략하면 저장된 즐겨찾기 목록에서 선택)")
    parser.add_argument("--limit", type=int, default=10, help="가져올 기사 수 (기본: 10)")
    parser.add_argument("--model", default="gpt-5.4-nano", help="GPT 모델명 (기본: gpt-5.4-nano)")
    parser.add_argument("--api-base", default=None, help="커스텀 OpenAI API Base URL (기본: .env의 OPENAI_API_BASE 또는 공식 엔드포인트)")
    parser.add_argument("--dry-run", action="store_true", help="크롤링만 실행 (GPT 호출 없음)")
    parser.add_argument("--output-dir", default=None, help="저장 경로 (기본: vault/)")
    parser.add_argument("--vault-name", default="vault", help="Obsidian Vault 이름 (기본: vault)")
    parser.add_argument("--no-open", action="store_true", help="완료 후 자동 실행 생략")
    parser.add_argument(
        "--format", default=DEFAULT_FORMAT, choices=EXPORT_FORMATS,
        help=f"저장 형식 (기본: {DEFAULT_FORMAT}, 선택: {', '.join(EXPORT_FORMATS)})",
    )
    parser.add_argument(
        "--credibility-check", action="store_true",
        help="크롤링된 기사의 신뢰성을 GPT로 평가해서 필터링 (추가 API 호출 발생)",
    )
    parser.add_argument(
        "--credibility-threshold", type=int, default=40,
        help="신뢰성 평가 통과 최소 점수 0~100 (기본: 40, 낮을수록 더 많이 허용)",
    )
    parser.add_argument(
        "--gossip-ratio", type=int, default=20,
        help="검색 결과 중 개인 의견/가십성 자료의 목표 비율 0~100 (기본: 20)",
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
    ui = console_strings(args.output_language)

    today = date.today().isoformat()
    vault_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "vault"
    run_credibility = args.credibility_check and not args.dry_run
    total_steps = 2 if args.dry_run else (4 if run_credibility else 3)

    topic = args.topic or select_topic_interactively(
        PROJECT_ROOT / "topics_favorites.json", args.output_language
    )

    print(f"\n{'='*50}")
    print(f"  🔎 Topic Research Digest — 「{topic}」 — {today}")
    print(f"{'='*50}")

    # ── Step 1: 뉴스 크롤링 ───────────────────────────────────────────────
    step(1, total_steps, ui['search'].format(topic=topic, limit=args.limit))
    search_profile = google_search_profile(args.output_language)
    gossip_ratio = max(0, min(100, args.gossip_ratio))
    print(
        f"  → {ui['google_profile'].format(lang=search_profile['lang'], country=search_profile['country'], ratio=gossip_ratio)}"
    )
    crawler = TopicNewsCrawler(
        lang=search_profile["lang"],
        country=search_profile["country"],
        lr=search_profile["lr"],
        gossip_ratio=gossip_ratio,
    )
    articles = crawler.fetch(topic, limit=args.limit)
    print(f"  → {ui['collected'].format(count=len(articles))}")
    for a in articles:
        print(f"     · {a['title'][:60]}")

    if not articles:
        print(f"\n  ❌ {ui['no_articles']}")
        sys.exit(1)

    # Analysis 탭/스크립트가 동일한 Topic Research 결과를 재사용할 수 있도록
    # 원자료 스냅샷을 저장한다. 사용자가 선택한 언어/검색 성향도 함께 기록한다.
    snapshot_dir = vault_dir / "topics" / _slugify(topic)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "_analysis_input.json"
    snapshot_path.write_text(
        json.dumps({
            "topic": topic,
            "date": today,
            "output_language": args.output_language,
            "gossip_ratio": gossip_ratio,
            "articles": articles,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # dry-run 종료 (신뢰성 평가도 GPT 호출이라 dry-run에서는 건너뛴다)
    if args.dry_run:
        step(2, total_steps, ui['dry_run'])
        print(f"\n  {ui['crawl_data']}")
        print(json.dumps({"topic": topic, "articles": articles},
                         ensure_ascii=False, indent=2))
        return

    api_key = load_api_key()
    api_base = args.api_base or load_api_base()
    ui_lang = resolve_ui_lang(args.output_language)
    step_n = 1

    # ── (선택) Step: 신뢰성 평가 ───────────────────────────────────────────
    if run_credibility:
        step_n += 1
        step(step_n, total_steps, ui['credibility'].format(threshold=args.credibility_threshold))
        articles = run_credibility_check(
            articles, (f"'{topic}' 기사" if ui_lang == "ko" else f"'{topic}' articles"), api_key, args.model, api_base, args.credibility_threshold, args.output_language
        )
        if not articles:
            print(f"\n  ❌ {ui['no_articles_after_credibility']}")
            sys.exit(1)

    # ── Step: GPT 분석 ────────────────────────────────────────────────────
    step_n += 1
    step(step_n, total_steps, ui['gpt'].format(model=args.model, language=args.output_language))
    analyzer = TopicAnalyzer(api_key=api_key, model=args.model, base_url=api_base)
    result = analyzer.analyze(
        topic=topic, articles=articles, today=today, output_language=args.output_language
    )

    if not result.is_success:
        print(f"  ❌ {ui['gpt_failed'].format(error=result.error)}")
        sys.exit(1)

    print(f"  → {ui['analysis_done']}")
    print(f"     {ui['trends'].format(count=len(result.trend_summary))}")
    print(f"     {ui['highlights'].format(count=len(result.highlights))}")

    # ── Step: 파일 저장 ────────────────────────────────────────────────────
    step_n += 1
    step(step_n, total_steps, ui['saving'].format(format=args.format))
    out_path = save_topic_digest(result, vault_dir, args.format, lang=ui_lang)
    print(f"  ✅ {ui['saved_check'].format(path=out_path)}")

    # ── 결과 파일 자동 실행 ───────────────────────────────────────────────
    if not args.no_open:
        open_output(args.format, args.vault_name, vault_dir, out_path, args.output_language)

    print(f"\n{'='*50}")
    print(f"  {ui['done'].format(path=out_path)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
