#!/usr/bin/env python3
"""
app.py

AI Research Digest 데스크톱 GUI 앱.

Topic Research, Backfill, and Trend Analysis workflows in one desktop frontend.
The collection and analysis pipelines remain separate subprocesses.

실행:
    uv run python scripts/app.py
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import uuid
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, font as tkfont

def _project_root() -> Path:
    """Return the repository root in development or the installed app root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _app_data_root() -> Path:
    """Return the writable per-user location for installed-app state."""
    if not getattr(sys, "frozen", False):
        return PROJECT_ROOT
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "AI Research Lab"


APP_DATA_ROOT = _app_data_root()


def _migrate_legacy_user_data() -> None:
    """Move state from an older installed build into the per-user data folder."""
    if not getattr(sys, "frozen", False):
        return
    try:
        APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for name in (".env", "gui_settings.json", "topics_favorites.json", "vault"):
        source = PROJECT_ROOT / name
        destination = APP_DATA_ROOT / name
        if not source.exists() or destination.exists():
            continue
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            # Retain the old copy if migration cannot be completed safely.
            continue


_migrate_legacy_user_data()

from research_lab.utils.favorites import TopicFavorites  # noqa: E402
from research_lab.digest.topic_formatter import _slugify  # noqa: E402
from research_lab.i18n import resolve_ui_lang, OUTPUT_LANGUAGE_PRESETS, DEFAULT_OUTPUT_LANGUAGE  # noqa: E402
from research_lab.crawler.hacker_news import HackerNewsCrawler  # noqa: E402
from research_lab.crawler.gdelt import GdeltCrawler  # noqa: E402
from research_lab.crawler.reddit import RedditCrawler  # noqa: E402
from research_lab.crawler.tavily import TavilySocialCrawler  # noqa: E402
from research_lab.crawler.x import XCrawler  # noqa: E402
from research_lab.crawler.youtube import YouTubeCrawler  # noqa: E402
from research_lab.pending_backfills import pending_days  # noqa: E402
from research_lab.backfill_policy import resolve_dump_scan_mode  # noqa: E402

SETTINGS_PATH = APP_DATA_ROOT / "gui_settings.json"
ENV_PATH = APP_DATA_ROOT / ".env"
FAVORITES_PATH = APP_DATA_ROOT / "topics_favorites.json"
DATA_VAULT_DIR = APP_DATA_ROOT / "vault"
APP_VERSION = "0.2.0-pre.2"
RELEASES_API_URL = "https://api.github.com/repos/EricLKIM/AI-Research-Lab/releases?per_page=20"

MODEL_PRESETS = ["gpt-5.4-nano", "gpt-5.4-mini", "gpt-4.1-nano"]
EXPORT_FORMAT_CHOICES = ["obsidian", "markdown", "text", "json", "html", "docx"]

DEFAULT_SETTINGS = {
    "vault_name": "vault",
    "vault_path": str(APP_DATA_ROOT / "vault"),
    "model": "gpt-5.4-nano",
    "api_base": "",
    "export_format": "obsidian",
    "credibility_check": False,
    "credibility_threshold": 40,
    "output_language": DEFAULT_OUTPUT_LANGUAGE,
    "gossip_ratio": 20,
    "community_sources": {"tavily": True, "reddit": True, "x": False, "youtube": False, "hackernews": True, "gdelt": True},
    "gdelt_source_language": "global",
    "gdelt_region_profile": "auto",
    "latest_news_priority": "google_rss",
    "google_rss_region_profile": "balanced",
    "new_topic_backfill_days": 7,
    "new_topic_backfill_interval_days": 1,
    "backfill_daily_article_count": 5,
    "backfill_method": "doc_api",
    "dump_cache_policy": "persistent",
    "dump_compact_after_days": 3,
    "dump_scan_mode": "auto",
    "dump_full_scan_max_days": 3,
    "auto_collection_times": ["09:00"],
    "include_time_unknown": False,
    "analysis_reliability_weight": 50,
    "analysis_freshness_weight": 30,
    "analysis_early_signal_weight": 20,
    "analysis_period_days": 30,
    "analysis_alert_emerging": True,
    "analysis_alert_rising": True,
    "analysis_alert_contradictions": True,
    "analysis_alert_data_quality": True,
}


# ── Localized strings ──────────────────────────────────────────────────────
# Language changes apply after the next restart; saving settings shows a notice.

STRINGS = {
    "ko": {
        "window_title": "AI Research Lab",
        "tab_topic": "주제 리서치",
        "tab_settings": "설정",
        "tab_advanced": "고급 설정",
        "tab_analysis": "분석",
        "analysis_intro": "Topic Research에서 수집한 최신 자료를 재사용하여 신뢰도·최신성·독립성을 반영한 동향 분석을 수행합니다.",
        "analysis_topic_label": "분석할 주제",
        "analysis_run_btn": "동향 분석 실행",
        "analysis_need_research": "먼저 Topic Research를 한 번 실행해 주세요.",
        "analysis_weights": "분석 가중치",
        "analysis_reliability": "신뢰도",
        "analysis_freshness": "최신성",
        "analysis_signal": "초기 신호",
        "analysis_period": "시계열 분석 기간",
        "analysis_history": "동향 변화 추적",
        "analysis_history_hint": "반복 분석 결과를 시간순으로 비교합니다. Rumor → Emerging Signal → Confirmed Trend 승격을 추적할 수 있습니다.",
        "analysis_no_history": "아직 분석 이력이 없습니다. Analysis를 실행하면 여기에 변화가 표시됩니다.",
        "status_idle": "대기 중",
        "status_running": "실행 중...",
        "status_done": "완료",
        "status_error": "오류로 종료됨",
        "topic_intro": "주제를 입력하거나 즐겨찾기에서 골라서 최신 뉴스를 리서치합니다.",
        "topic_favorites_label": "즐겨찾기",
        "topic_delete_btn": "삭제",
        "topic_entry_label": "주제어 (직접 입력 시 위 목록보다 우선 사용됩니다)",
        "topic_save_fav_label": "새로 입력한 주제를 즐겨찾기에 저장",
        "topic_limit_label": "가져올 기사 수",
        "topic_run_btn": "생성하기",
        "settings_api_key": "OpenAI API Key",
        "settings_api_base": "API Base URL (선택)",
        "settings_vault_name": "Obsidian Vault 이름",
        "settings_vault_path": "Vault 폴더 경로",
        "settings_browse": "찾아보기...",
        "settings_model": "GPT 모델",
        "settings_export_format": "내보내기 형식",
        "settings_export_format_hint": "obsidian(기본) 외에 markdown / text / json / html / docx로도 저장할 수 있습니다.",
        "settings_credibility_check": "크롤링 항목 신뢰성 평가 사용 (가십/미확인 정보 필터링)",
        "settings_credibility_warning": "⚠️ 켜면 항목마다 GPT 호출이 추가되어 API 비용이 더 듭니다.",
        "settings_source_balance": "검색 성향 (정확한 뉴스 ↔ 개인 의견·가십)",
        "source_balance_left": "정확한 뉴스",
        "source_balance_right": "개인 의견·가십",
        "source_balance_fmt": "가십 비율 {v}% — {hint}",
        "source_balance_low": "주요 언론/뉴스 중심으로 검색합니다.",
        "source_balance_mid": "뉴스와 개인·커뮤니티 자료를 섞습니다.",
        "source_balance_high": "Google 일반 검색에서 블로그·커뮤니티·토론 자료를 적극적으로 찾습니다. 소문은 사실로 간주하지 않습니다.",
        "settings_community_sources": "고급 설정 — 커뮤니티 수집원",
        "settings_tavily": "Tavily Social (추천: Reddit·X 통합, 무료 월간 할당량)",
        "settings_reddit": "Reddit (OAuth 승인 필요)",
        "settings_x": "X (Bearer Token 필요)",
        "settings_youtube": "YouTube (API Key 필요)",
        "settings_hackernews": "Hacker News (AI·반도체 주제만, API Key 불필요)",
        "settings_gdelt": "GDELT DOC (뉴스·백필, API Key 불필요)",
        "settings_gdelt_language": "GDELT 원문 언어 (global / korean / english)",
        "settings_gdelt_region": "GDELT 지역 분산 (auto / global_even / country_focus)",
        "settings_latest_news_priority": "최신 뉴스 우선 수집원 (google_rss / gdelt)",
        "settings_google_rss_region": "Google RSS 국가 분산 (balanced / local_only)",
        "settings_reddit_id": "Reddit Client ID",
        "settings_tavily_key": "Tavily API Key (추천)",
        "settings_reddit_secret": "Reddit Client Secret",
        "settings_reddit_agent": "Reddit User-Agent",
        "settings_x_token": "X Bearer Token",
        "settings_youtube_key": "YouTube API Key",
        "settings_include_time_unknown": "시간을 확인할 수 없는 커뮤니티 자료도 사용",
        "settings_test_connections": "활성 수집원 연결 테스트",
        "settings_test_running": "연결 확인 중...",
        "settings_backfill_days": "새 주제 백필 전체 기간 (일)",
        "settings_backfill_interval_days": "새 주제 백필 간격 (일)",
        "settings_backfill_daily_count": "백필 일일 목표 기사 수",
        "settings_backfill_method": "백필 방식 (doc_api / gdelt_dump)",
        "settings_dump_cache_policy": "덤프 캐시 (persistent / compact persistent / temporary)",
        "settings_dump_compact_after_days": "Compact persistent 전체 보관 기간 (일, 기본 추천: 3)",
        "settings_dump_cache_hint": "persistent는 전체 보관, compact persistent는 오래된 날짜를 UTC 5개 균등 블록으로 축소, temporary는 처리 후 삭제합니다.",
        "settings_dump_scan_mode": "덤프 스캔 (auto / sample / full)",
        "settings_dump_full_scan_days": "Auto Full 최대 기간 (일, 기본 추천: 3)",
        "settings_auto_times": "자동 수집 시각 (최대 3개, HH:MM)",
        "settings_auto_register": "자동 수집 등록/변경",
        "settings_auto_unregister": "자동 수집 해제",
        "msg_backfill_title": "새 주제 백필",
        "msg_backfill_body": "이 주제에는 아직 수집 이력이 없습니다. 최근 {days}일의 GDELT 데이터를 먼저 백필할까요? 완료 후 최신 주제 리서치가 자동으로 이어집니다.",
        "msg_backfill_disabled": "GDELT DOC가 꺼져 있어 새 주제 백필은 실행하지 않습니다. 고급 설정에서 GDELT DOC를 켠 뒤 다시 실행하세요.",
        "settings_language": "출력 언어 (다이제스트 내용)",
        "settings_language_hint": "자유롭게 입력 가능 (예: English, 日本語, 中文). 앱 화면/파일 틀 문구는 이 값이 한국어일 때만 한국어이고, 그 외에는 항상 English로 표시됩니다. 변경 후 앱을 다시 시작해야 적용됩니다.",
        "settings_save_btn": "저장",
        "settings_saved_msg": "✅ 저장되었습니다. (언어를 바꿨다면 앱을 재시작하세요)",
        "threshold_left_label": "정확도 중심",
        "threshold_right_label": "신규성·가십 허용",
        "threshold_off": "신뢰성 평가가 꺼져 있습니다.",
        "threshold_high": "검증된 정보만 남기고 확인되지 않은 내용은 적극적으로 걸러냅니다.",
        "threshold_low": "아직 검증되지 않았어도 새로운/화제성 있는 정보를 대부분 통과시킵니다.",
        "threshold_mid": "정확도와 새로운 정보 사이에서 균형을 잡습니다.",
        "threshold_fmt": "임계값 {v}/100 — {hint}",
        "msg_save_title": "설정 저장",
        "msg_save_api_key_required": "OpenAI API Key를 입력해주세요.",
        "msg_save_vault_required": "Vault 이름과 폴더 경로를 입력해주세요.",
        "msg_running_title": "실행 중",
        "msg_running_body": "이미 다른 작업이 실행 중입니다. 완료 후 다시 시도하세요.",
        "msg_api_key_missing_title": "API Key 없음",
        "msg_api_key_missing_body": "설정 탭에서 OpenAI API Key를 먼저 저장해주세요.",
        "msg_topic_required_title": "주제 필요",
        "msg_topic_required_body": "주제를 입력하거나 즐겨찾기에서 선택하세요.",
        "msg_fav_delete_title": "즐겨찾기 삭제",
        "msg_fav_delete_body": "삭제할 항목을 목록에서 선택하세요.",
        "error_uv_not_found": "❌ 'uv'를 찾을 수 없습니다. uv가 설치/PATH에 등록되어 있는지 확인하세요.\n",
        "error_running": "❌ 실행 중 오류: {e}\n",
    },
    "en": {
        "window_title": "AI Research Lab",
        "tab_topic": "Topic Research",
        "tab_settings": "Settings",
        "tab_advanced": "Advanced",
        "tab_analysis": "Analysis",
        "analysis_intro": "Reuses the latest Topic Research sources and analyzes trends using reliability, freshness, evidence, and source independence.",
        "analysis_topic_label": "Topic to analyze",
        "analysis_run_btn": "Run Trend Analysis",
        "analysis_need_research": "Run Topic Research once before Analysis.",
        "analysis_weights": "Analysis weights",
        "analysis_reliability": "Reliability",
        "analysis_freshness": "Freshness",
        "analysis_signal": "Early signal",
        "analysis_period": "Time-series period",
        "analysis_history": "Trend evolution",
        "analysis_history_hint": "Compare repeated analyses over time and track Rumor → Emerging Signal → Confirmed Trend transitions.",
        "analysis_no_history": "No analysis history yet. Run Analysis to populate this timeline.",
        "status_idle": "Idle",
        "status_running": "Running...",
        "status_done": "Done",
        "status_error": "Finished with an error",
        "status_cancelled": "Cancelled",
        "cancel_btn": "Cancel",
        "topic_intro": "Type a topic or pick one from your favorites to research the latest news.",
        "topic_favorites_label": "Favorites",
        "topic_delete_btn": "Delete",
        "topic_entry_label": "Topic (typing here takes priority over the list above)",
        "topic_save_fav_label": "Save newly typed topics to favorites",
        "topic_limit_label": "Number of articles to fetch",
        "topic_run_btn": "Generate",
        "settings_api_key": "OpenAI API Key",
        "settings_api_base": "API Base URL (optional)",
        "settings_vault_name": "Obsidian Vault name",
        "settings_vault_path": "Vault folder path",
        "settings_browse": "Browse...",
        "settings_model": "GPT model",
        "settings_export_format": "Export format",
        "settings_export_format_hint": "Besides obsidian (default), you can also save as markdown / text / json / html / docx.",
        "settings_credibility_check": "Enable credibility scoring for crawled items (filters gossip/unverified content)",
        "settings_credibility_warning": "⚠️ Turning this on adds a GPT call per item, which increases API cost.",
        "settings_source_balance": "Search style (reliable news ↔ personal opinions/gossip)",
        "source_balance_left": "Reliable news",
        "source_balance_right": "Personal opinions/gossip",
        "source_balance_fmt": "Gossip ratio {v}% — {hint}",
        "source_balance_low": "Primarily searches established news sources.",
        "source_balance_mid": "Mixes news with personal and community sources.",
        "source_balance_high": "Actively searches Google Web for blogs, communities, and discussions. Rumors are not treated as facts.",
        "settings_community_sources": "Advanced — community sources",
        "settings_tavily": "Tavily Social (recommended: combined Reddit/X, monthly free credits)",
        "settings_reddit": "Reddit (OAuth approval required)",
        "settings_x": "X (Bearer Token required)",
        "settings_youtube": "YouTube (API Key required)",
        "settings_hackernews": "Hacker News (AI/semiconductor topics only; no API key)",
        "settings_gdelt": "GDELT DOC (news/backfill; no API key)",
        "settings_gdelt_language": "GDELT source language (global / korean / english)",
        "settings_gdelt_region": "GDELT regional balance (auto / global_even / country_focus)",
        "settings_latest_news_priority": "Latest-news priority (google_rss / gdelt)",
        "settings_google_rss_region": "Google RSS regional mix (balanced / local_only)",
        "settings_reddit_id": "Reddit Client ID",
        "settings_tavily_key": "Tavily API Key (recommended)",
        "settings_reddit_secret": "Reddit Client Secret",
        "settings_reddit_agent": "Reddit User-Agent",
        "settings_x_token": "X Bearer Token",
        "settings_youtube_key": "YouTube API Key",
        "settings_include_time_unknown": "Include community items with an unknown time",
        "settings_test_connections": "Test enabled source connections",
        "settings_test_running": "Checking connections...",
        "settings_backfill_days": "New-topic backfill total period (days)",
        "settings_backfill_interval_days": "New-topic backfill interval (days)",
        "settings_backfill_daily_count": "Backfill daily target articles",
        "settings_backfill_method": "Backfill method (doc_api / gdelt_dump)",
        "settings_dump_cache_policy": "Dump cache (persistent / compact persistent / temporary)",
        "settings_dump_compact_after_days": "Compact persistent full-cache period (days, recommended default: 3)",
        "settings_dump_cache_hint": "persistent keeps all blocks; compact persistent reduces older days to five balanced UTC blocks; temporary deletes blocks after processing.",
        "settings_dump_scan_mode": "Dump scan (auto / sample / full)",
        "settings_dump_full_scan_days": "Auto Full maximum period (days, recommended default: 3)",
        "settings_auto_times": "Auto-collection times (up to 3, HH:MM)",
        "settings_auto_register": "Register/update auto collection",
        "settings_auto_unregister": "Remove auto collection",
        "msg_backfill_title": "New topic backfill",
        "msg_backfill_body": "This topic has no collection history. Backfill the last {days} days from GDELT first? The latest Topic Research will run automatically afterwards.",
        "msg_backfill_disabled": "New-topic backfill is disabled because GDELT DOC is disabled. Enable it in Advanced settings and run again.",
        "settings_language": "Output language (digest content)",
        "settings_language_hint": "Type any language (e.g. English, 日本語, 中文). The app UI and file template text stay Korean only when this is Korean; otherwise they're always in English. Restart the app after changing this.",
        "settings_save_btn": "Save",
        "settings_saved_msg": "✅ Saved. (Restart the app if you changed the language)",
        "threshold_left_label": "Favor accuracy",
        "threshold_right_label": "Allow novelty/gossip",
        "threshold_off": "Credibility scoring is turned off.",
        "threshold_high": "Keeps only well-verified information and aggressively filters out unconfirmed content.",
        "threshold_low": "Lets most new or buzzworthy items through even if not yet verified.",
        "threshold_mid": "Balances accuracy against novelty.",
        "threshold_fmt": "Threshold {v}/100 — {hint}",
        "msg_save_title": "Save settings",
        "msg_save_api_key_required": "Please enter your OpenAI API Key.",
        "msg_save_vault_required": "Please enter both the Vault name and folder path.",
        "msg_running_title": "Already running",
        "msg_running_body": "Another job is already running. Please wait for it to finish and try again.",
        "msg_api_key_missing_title": "No API Key",
        "msg_api_key_missing_body": "Please save your OpenAI API Key in the Settings tab first.",
        "msg_topic_required_title": "Topic required",
        "msg_topic_required_body": "Type a topic or select one from your favorites.",
        "msg_fav_delete_title": "Delete favorite",
        "msg_fav_delete_body": "Select an item from the list to delete.",
        "error_uv_not_found": "❌ Could not find 'uv'. Make sure uv is installed and on your PATH.\n",
        "error_running": "❌ Error while running: {e}\n",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["ko"])
    text = table.get(key, STRINGS["ko"].get(key, key))
    return text.format(**kwargs) if kwargs else text


# ── Settings and .env I/O ──────────────────────────────────────────────────

def _parse_bat_arg(bat_path: Path, flag: str) -> str | None:
    """bat 파일 안의 `--flag "값"` 형태에서 값을 추출한다."""
    if not bat_path.exists():
        return None
    text = bat_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(re.escape(flag) + r'\s+"([^"]*)"', text)
    return m.group(1) if m and m.group(1) else None


def recover_settings_from_bat() -> dict | None:
    """gui_settings.json이 없을 때(구버전 설치, 또는 app.py만 교체 적용한 경우),
    설치 시 이미 만들어져 있는 run_topic_digest.bat 안의 실제 값으로
    복구를 시도한다. 이게 없으면 앱이 항상 설치 폴더 밑 기본 vault 경로로 저장해버려서,
    사용자가 설치 때 지정한 실제 Vault 경로가 무시되는 문제가 있었다."""
    for bat_name in ("run_topic_digest.bat",):
        bat_path = PROJECT_ROOT / bat_name
        if not bat_path.exists():
            continue
        vault_name = _parse_bat_arg(bat_path, "--vault-name")
        vault_path = _parse_bat_arg(bat_path, "--output-dir")
        model = _parse_bat_arg(bat_path, "--model")
        if not any([vault_name, vault_path, model]):
            continue
        recovered = dict(DEFAULT_SETTINGS)
        if vault_name:
            recovered["vault_name"] = vault_name
        if vault_path:
            recovered["vault_path"] = vault_path
        if model:
            recovered["model"] = model
        return recovered
    return None


def _read_text_with_fallback(path: Path) -> str:
    """Read text robustly from files created by older installers.

    Older Inno Setup scripts wrote generated files with the system ANSI code
    page. On a Korean Windows installation that can be CP949, which makes
    json.loads(... read_text(encoding="utf-8")) fail before the GUI can start.
    Prefer UTF-8, then BOM-aware UTF-16, then CP949, then the local ANSI code
    page as a last resort.
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp949", "mbcs"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def load_settings() -> dict:
    merged = dict(DEFAULT_SETTINGS)

    if SETTINGS_PATH.exists():
        try:
            data = json.loads(_read_text_with_fallback(SETTINGS_PATH))
            if isinstance(data, dict):
                merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
                saved_sources = data.get("community_sources")
                if isinstance(saved_sources, dict):
                    merged["community_sources"] = {
                        **DEFAULT_SETTINGS["community_sources"],
                        **saved_sources,
                    }
            # Normalize the file to UTF-8 so this compatibility path is only
            # needed once for installations produced by older versions.
            save_settings(merged)
        except (json.JSONDecodeError, OSError, UnicodeError, TypeError):
            recovered = recover_settings_from_bat()
            merged = recovered if recovered else dict(DEFAULT_SETTINGS)
            save_settings(merged)
    else:
        recovered = recover_settings_from_bat()
        merged = recovered if recovered else dict(DEFAULT_SETTINGS)
        save_settings(merged)  # Persist recovered settings for subsequent launches.

    # Fall back to .env when neither gui_settings.json nor the launcher stores api_base.
    # This avoids prompting again for the value chosen during installation.
    if not merged.get("api_base"):
        env_base = load_env_value("OPENAI_API_BASE")
        if env_base:
            merged["api_base"] = env_base

    if not str(merged.get("output_language", "")).strip():
        merged["output_language"] = DEFAULT_OUTPUT_LANGUAGE

    return merged


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_env_value(key: str) -> str:
    if not ENV_PATH.exists():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def save_env_values(values: dict) -> None:
    """기존 .env의 다른 줄은 건드리지 않고, 지정한 key들만 갱신/추가한다."""
    lines: list[str] = []
    seen: set[str] = set()

    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            matched_key = None
            for key in values:
                if stripped.startswith(f"{key}="):
                    matched_key = key
                    break
            if matched_key:
                if values[matched_key]:  # Remove the line entirely for an empty value.
                    lines.append(f"{matched_key}={values[matched_key]}")
                seen.add(matched_key)
            else:
                lines.append(line)

    for key, value in values.items():
        if key not in seen and value:
            lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Background pipeline execution ─────────────────────────────────────────

class PipelineRunner:
    """서브프로세스로 파이프라인 스크립트를 실행하고, 출력 줄을 큐로 흘려보낸다."""

    def __init__(self, log_queue: "queue.Queue[tuple[str, object]]", lang: str) -> None:
        self.log_queue = log_queue
        self.lang = lang
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._cancel_requested = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run(self, args: list[str]) -> None:
        if self.is_running:
            return
        self._cancel_requested = False
        self._thread = threading.Thread(target=self._run_blocking, args=(args,), daemon=True)
        self._thread.start()

    def cancel(self) -> bool:
        """Request cancellation and terminate the currently running child process."""
        if not self.is_running or self._proc is None:
            return False
        self._cancel_requested = True
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
            return True
        except Exception:
            return False

    def _run_blocking(self, args: list[str]) -> None:
        # app.py itself is launched inside uv's managed virtual environment.
        # Reusing the exact interpreter that launched this GUI is more reliable
        # than starting a second nested `uv run` process.
        if getattr(sys, "frozen", False):
            pipeline_names = {
                "topic_digest.py": ("topic_digest", "Topic Research.exe"),
                "backfill_gdelt_dump.py": ("backfill_gdelt_dump", "GDELT Dump Backfill.exe"),
                "analysis.py": ("analysis", "Trend Analysis.exe"),
            }
            pipeline = pipeline_names.get(Path(args[0]).name)
            if pipeline is None:
                self.log_queue.put(("line", f"Packaged pipeline is not registered: {args[0]}\n"))
                self.log_queue.put(("done", -1))
                return
            executable = PROJECT_ROOT / "pipelines" / pipeline[0] / pipeline[1]
            if not executable.exists():
                self.log_queue.put(("line", f"Packaged pipeline was not found: {executable}\n"))
                self.log_queue.put(("done", -1))
                return
            cmd = [str(executable), *args[1:]]
        else:
            python_exe = sys.executable
            if not python_exe or not Path(python_exe).exists():
                self.log_queue.put(("line", "Python interpreter not found.\n"))
                self.log_queue.put(("done", -1))
                return
            # -u makes child progress lines visible in the GUI immediately.
            cmd = [python_exe, "-u", *args]
        self.log_queue.put(("line", f"$ {' '.join(cmd)}\n"))
        try:
            child_env = os.environ.copy()
            child_env["AI_RESEARCH_LAB_HOME"] = str(PROJECT_ROOT)
            child_env["AI_RESEARCH_LAB_DATA_HOME"] = str(APP_DATA_ROOT)
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self.log_queue.put(("line", f"[Process] PID {self._proc.pid} started\n"))
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                self.log_queue.put(("line", line))
            returncode = self._proc.wait()
        except FileNotFoundError:
            self.log_queue.put(("line", tr(self.lang, "error_uv_not_found")))
            returncode = -1
        except Exception as e:  # noqa: BLE001
            self.log_queue.put(("line", tr(self.lang, "error_running", e=e)))
            returncode = -1
        finally:
            self._proc = None
            self.log_queue.put(("done", returncode))


# ── GUI ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self) -> None:
        # Group the Windows taskbar entry under AI Research Lab rather than pythonw.exe.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "AIResearchLab.AIResearchLab"
                )
            except Exception:
                pass

        super().__init__()

        self.settings = load_settings()
        self.output_language = self.settings.get("output_language", DEFAULT_OUTPUT_LANGUAGE)
        self.lang = resolve_ui_lang(self.output_language)

        self.title(tr(self.lang, "window_title"))

        # Use the installed AI Research Lab icon for the window and taskbar instead of Tkinter's Python icon.
        icon_path = PROJECT_ROOT / "digest.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

        self.geometry("780x720")
        self.minsize(660, 580)

        self.log_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.runner = PipelineRunner(self.log_queue, self.lang)
        self.favorites = TopicFavorites(FAVORITES_PATH, self.output_language)

        self._build_widgets()
        self._load_settings_into_widgets()
        self._refresh_favorites_list()
        self.after(100, self._poll_log_queue)
        self.after(1200, self._check_for_updates_in_background)

    def t(self, key: str, **kwargs) -> str:
        return tr(self.lang, key, **kwargs)

    # ── Widget construction ───────────────────────────────────────────────
    def _build_widgets(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=False, padx=10, pady=(10, 0))

        self.tab_topic = ttk.Frame(self.notebook)
        self.tab_analysis = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_advanced = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_topic, text=self.t("tab_topic"))
        self.notebook.add(self.tab_analysis, text=self.t("tab_analysis"))
        self.notebook.add(self.tab_settings, text=self.t("tab_settings"))
        self.notebook.add(self.tab_advanced, text=self.t("tab_advanced"))

        self._build_topic_tab()
        self._build_analysis_tab()
        self._build_settings_tab()
        self._build_advanced_settings_tab()

        # ── Shared status bar and log pane ─────────────────────────────────
        self.status_frame = ttk.Frame(self)
        self.status_frame.pack(fill="x", padx=10, pady=(10, 0))
        self.status_var = tk.StringVar(value=self.t("status_idle"))
        ttk.Label(self.status_frame, textvariable=self.status_var).pack(side="left")

        self._update_url = ""
        self.update_btn = ttk.Button(self.status_frame, command=self._open_update_page)

        self.cancel_btn = ttk.Button(
            self.status_frame, text=self.t("cancel_btn"), command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.progress = ttk.Progressbar(self.status_frame, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        self.log_frame = ttk.Frame(self)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text = tk.Text(self.log_frame, height=14, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

    def _on_notebook_tab_changed(self, _event=None) -> None:
        """Hide execution controls while the user is editing settings."""
        selected = self.notebook.nametowidget(self.notebook.select())
        show_execution = selected not in {self.tab_settings, self.tab_advanced}
        if show_execution:
            self.notebook.pack_configure(expand=False)
            if not self.status_frame.winfo_manager():
                self.status_frame.pack(fill="x", padx=10, pady=(10, 0))
            if not self.log_frame.winfo_manager():
                self.log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        else:
            self.status_frame.pack_forget()
            self.log_frame.pack_forget()
            self.notebook.pack_configure(expand=True)

    # ── Update check ─────────────────────────────────────────────────────
    @staticmethod
    def _version_key(version: str) -> tuple[int, int, int, int, int]:
        """Create a small, dependency-free ordering key for release tags."""
        match = re.search(r"v?(\d+)\.(\d+)\.(\d+)(?:-pre\.(\d+))?", version, re.IGNORECASE)
        if not match:
            return (0, 0, 0, 0, 0)
        major, minor, patch, pre = match.groups()
        # A stable release sorts after pre-releases for the same version.
        return (int(major), int(minor), int(patch), 1 if pre is None else 0, int(pre or 0))

    def _check_for_updates_in_background(self) -> None:
        """Check public GitHub releases without delaying the desktop UI."""
        def worker() -> None:
            try:
                request = urllib.request.Request(
                    RELEASES_API_URL,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "AI-Research-Lab"},
                )
                with urllib.request.urlopen(request, timeout=4) as response:
                    releases = json.loads(response.read().decode("utf-8"))
                candidates = [release for release in releases if not release.get("draft")]
                if not candidates:
                    return
                latest = max(candidates, key=lambda release: self._version_key(str(release.get("tag_name", ""))))
                latest_tag = str(latest.get("tag_name", ""))
                if self._version_key(latest_tag) <= self._version_key(APP_VERSION):
                    return
                self.after(0, lambda: self._show_update_available(latest_tag, str(latest.get("html_url", ""))))
            except Exception:
                # Network failures must never affect startup or collection work.
                return

        threading.Thread(target=worker, daemon=True, name="release-update-check").start()

    def _show_update_available(self, version: str, url: str) -> None:
        self._update_url = url
        label = f"Update available: {version}" if self.lang != "ko" else f"새 버전 사용 가능: {version}"
        self.update_btn.configure(text=label)
        self.update_btn.pack(side="left", padx=(12, 0))

    def _open_update_page(self) -> None:
        if self._update_url:
            webbrowser.open(self._update_url)

    def _build_topic_tab(self) -> None:
        f = self.tab_topic
        f.columnconfigure(0, weight=1)

        ttk.Label(f, text=self.t("topic_intro"), justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        ttk.Label(f, text=self.t("topic_favorites_label")).grid(row=1, column=0, sticky="w", padx=12)
        self.fav_listbox = tk.Listbox(f, height=6, exportselection=False)
        self.fav_listbox.grid(row=2, column=0, sticky="nsew", padx=(12, 4))
        self.fav_listbox.bind("<<ListboxSelect>>", self._on_favorite_selected)

        fav_btns = ttk.Frame(f)
        fav_btns.grid(row=2, column=1, sticky="n", padx=(4, 12))
        ttk.Button(fav_btns, text=self.t("topic_delete_btn"), command=self._on_remove_favorite).pack(
            fill="x", pady=(0, 4)
        )

        ttk.Label(f, text=self.t("topic_entry_label")).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 0)
        )
        self.topic_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.topic_var).grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=12
        )

        self.save_favorite_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            f, text=self.t("topic_save_fav_label"), variable=self.save_favorite_var
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(6, 0))

        ttk.Label(f, text=self.t("topic_limit_label")).grid(row=6, column=0, sticky="w", padx=12, pady=(8, 0))
        self.limit_var = tk.IntVar(value=10)
        ttk.Spinbox(f, from_=1, to=30, textvariable=self.limit_var, width=8).grid(
            row=6, column=1, sticky="w", padx=12, pady=(8, 0)
        )

        self.topic_run_btn = ttk.Button(f, text=self.t("topic_run_btn"), command=self._on_run_topic)
        self.topic_run_btn.grid(row=7, column=0, sticky="w", padx=12, pady=16)

    def _build_analysis_tab(self) -> None:
        f = self.tab_analysis
        f.columnconfigure(1, weight=1)
        f.rowconfigure(10, weight=1)
        pad = {"padx": 12, "pady": 6}
        ttk.Label(f, text=self.t("analysis_intro"), justify="left", wraplength=680).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 12)
        )
        ttk.Label(f, text=self.t("analysis_topic_label")).grid(row=1, column=0, sticky="w", **pad)
        self.analysis_topic_var = tk.StringVar()
        self.analysis_topic_combo = ttk.Combobox(f, textvariable=self.analysis_topic_var)
        self.analysis_topic_combo.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(f, text=self.t("analysis_weights")).grid(row=2, column=0, sticky="w", **pad)
        weights = ttk.Frame(f)
        weights.grid(row=2, column=1, sticky="ew", **pad)
        weights.columnconfigure(1, weight=1); weights.columnconfigure(3, weight=1); weights.columnconfigure(5, weight=1)
        ttk.Label(weights, text=self.t("analysis_reliability")).grid(row=0, column=0, sticky="w")
        self.analysis_reliability_var = tk.IntVar(value=50)
        ttk.Scale(weights, from_=0, to=100, variable=self.analysis_reliability_var, orient="horizontal").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(weights, text=self.t("analysis_freshness")).grid(row=0, column=2, sticky="w")
        self.analysis_freshness_var = tk.IntVar(value=30)
        ttk.Scale(weights, from_=0, to=100, variable=self.analysis_freshness_var, orient="horizontal").grid(row=0, column=3, sticky="ew", padx=5)
        ttk.Label(weights, text=self.t("analysis_signal")).grid(row=0, column=4, sticky="w")
        self.analysis_signal_var = tk.IntVar(value=20)
        ttk.Scale(weights, from_=0, to=100, variable=self.analysis_signal_var, orient="horizontal").grid(row=0, column=5, sticky="ew", padx=5)
        ttk.Label(f, text=self.t("analysis_period")).grid(row=3, column=0, sticky="w", **pad)
        self.analysis_period_var = tk.IntVar(value=30)
        ttk.Combobox(f, textvariable=self.analysis_period_var, values=(7, 30, 90, 180, 365), state="readonly", width=8).grid(row=3, column=1, sticky="w", **pad)
        self.analysis_run_btn = ttk.Button(f, text=self.t("analysis_run_btn"), command=self._on_run_analysis)
        self.analysis_run_btn.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=16)
        ttk.Label(
            f,
            text="Confirmed Trend / Emerging Signal / Rumor로 분리하며, 결과는 Settings의 Export format으로 저장됩니다."
            if self.lang == "ko"
            else "Results are separated into Confirmed Trend / Emerging Signal / Rumor and saved using the Settings export format.",
            wraplength=680,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        comparison_title = "직전 분석과 비교" if self.lang == "ko" else "Compare with previous analysis"
        ttk.Label(f, text=comparison_title, font=("TkDefaultFont", 10, "bold")).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 2)
        )
        self.analysis_comparison_text = tk.Text(f, height=6, wrap="word", state="disabled", background="#f8fafc", relief="solid", borderwidth=1)
        self.analysis_comparison_text.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

        # ── Timeline visualization ─────────────────────────────────────────
        ttk.Label(f, text=self.t("analysis_history"), font=("TkDefaultFont", 10, "bold")).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 2)
        )
        ttk.Label(f, text=self.t("analysis_history_hint"), wraplength=680).grid(
            row=9, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6)
        )
        chart_frame = ttk.Frame(f)
        chart_frame.grid(row=10, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)
        self.analysis_canvas = tk.Canvas(
            chart_frame, height=300, background="white", highlightthickness=1,
            highlightbackground="#d5dbe0"
        )
        self.analysis_canvas.grid(row=0, column=0, sticky="nsew")
        chart_scroll = ttk.Scrollbar(chart_frame, orient="vertical", command=self.analysis_canvas.yview)
        chart_scroll.grid(row=0, column=1, sticky="ns")
        self.analysis_canvas.configure(yscrollcommand=chart_scroll.set)
        self.analysis_canvas.bind("<Configure>", lambda _e: self._draw_analysis_history())
        self.analysis_topic_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_analysis_history())
    def _build_settings_tab(self) -> None:
        settings_canvas = tk.Canvas(self.tab_settings, highlightthickness=0)
        settings_scrollbar = ttk.Scrollbar(
            self.tab_settings, orient="vertical", command=settings_canvas.yview
        )
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tab_settings.columnconfigure(0, weight=1)
        self.tab_settings.rowconfigure(0, weight=1)

        f = ttk.Frame(settings_canvas)
        settings_window = settings_canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind(
            "<Configure>",
            lambda _event: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")),
        )
        settings_canvas.bind(
            "<Configure>",
            lambda event: settings_canvas.itemconfigure(settings_window, width=event.width),
        )
        f.columnconfigure(1, weight=1)
        pad = {"padx": 12, "pady": 6}

        ttk.Label(f, text=self.t("settings_api_key")).grid(row=0, column=0, sticky="w", **pad)
        self.api_key_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.api_key_var, show="•").grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(f, text=self.t("settings_api_base")).grid(row=1, column=0, sticky="w", **pad)
        self.api_base_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.api_base_var).grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(f, text=self.t("settings_vault_name")).grid(row=2, column=0, sticky="w", **pad)
        self.vault_name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.vault_name_var).grid(row=2, column=1, sticky="ew", **pad)

        ttk.Label(f, text=self.t("settings_vault_path")).grid(row=3, column=0, sticky="w", **pad)
        vault_path_frame = ttk.Frame(f)
        vault_path_frame.grid(row=3, column=1, sticky="ew", **pad)
        vault_path_frame.columnconfigure(0, weight=1)
        self.vault_path_var = tk.StringVar()
        ttk.Entry(vault_path_frame, textvariable=self.vault_path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(vault_path_frame, text=self.t("settings_browse"), command=self._on_browse_vault).grid(
            row=0, column=1, padx=(6, 0)
        )

        ttk.Label(f, text=self.t("settings_model")).grid(row=4, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.model_var, values=MODEL_PRESETS).grid(
            row=4, column=1, sticky="ew", **pad
        )

        ttk.Separator(f).grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 8))

        ttk.Label(f, text=self.t("settings_export_format")).grid(row=6, column=0, sticky="w", **pad)
        self.export_format_var = tk.StringVar()
        ttk.Combobox(
            f, textvariable=self.export_format_var, values=EXPORT_FORMAT_CHOICES, state="readonly"
        ).grid(row=6, column=1, sticky="ew", **pad)
        ttk.Label(f, text=self.t("settings_export_format_hint"), foreground="#5b6b7a").grid(
            row=7, column=1, sticky="w", padx=12
        )

        self.credibility_check_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text=self.t("settings_credibility_check"),
            variable=self.credibility_check_var, command=self._on_toggle_credibility,
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 0))
        ttk.Label(f, text=self.t("settings_credibility_warning"), foreground="#a15c00").grid(
            row=9, column=0, columnspan=2, sticky="w", padx=12
        )

        self.threshold_label_var = tk.StringVar()
        self.threshold_desc_label = ttk.Label(f, textvariable=self.threshold_label_var)
        self.threshold_desc_label.grid(row=10, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))

        slider_row = ttk.Frame(f)
        slider_row.grid(row=11, column=0, columnspan=2, sticky="ew", padx=12)
        slider_row.columnconfigure(1, weight=1)
        ttk.Label(slider_row, text=self.t("threshold_left_label")).grid(row=0, column=0, sticky="w")
        self.credibility_threshold_var = tk.IntVar(value=40)
        self.threshold_scale = tk.Scale(
            slider_row, from_=0, to=100, orient="horizontal", resolution=1,
            showvalue=False, variable=self.credibility_threshold_var,
            command=self._on_threshold_change,
        )
        self.threshold_scale.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(slider_row, text=self.t("threshold_right_label")).grid(row=0, column=2, sticky="e")

        ttk.Label(f, text=self.t("settings_source_balance")).grid(row=12, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        source_row = ttk.Frame(f)
        source_row.grid(row=13, column=0, columnspan=2, sticky="ew", padx=12)
        source_row.columnconfigure(1, weight=1)
        ttk.Label(source_row, text=self.t("source_balance_left")).grid(row=0, column=0, sticky="w")
        self.gossip_ratio_var = tk.IntVar(value=20)
        self.gossip_ratio_scale = tk.Scale(
            source_row, from_=0, to=100, orient="horizontal", resolution=1,
            showvalue=False, variable=self.gossip_ratio_var, command=self._on_gossip_ratio_change,
        )
        self.gossip_ratio_scale.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(source_row, text=self.t("source_balance_right")).grid(row=0, column=2, sticky="e")
        self.source_balance_label_var = tk.StringVar()
        ttk.Label(f, textvariable=self.source_balance_label_var, wraplength=520).grid(
            row=14, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 4)
        )

        ttk.Separator(f).grid(row=15, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 8))

        ttk.Label(f, text=self.t("settings_language")).grid(row=16, column=0, sticky="w", **pad)
        self.language_var = tk.StringVar()
        ttk.Combobox(
            f, textvariable=self.language_var, values=OUTPUT_LANGUAGE_PRESETS
        ).grid(row=16, column=1, sticky="ew", **pad)
        ttk.Label(f, text=self.t("settings_language_hint"), foreground="#5b6b7a", wraplength=380).grid(
            row=17, column=1, sticky="w", padx=12
        )

        self.settings_status_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.settings_status_var, foreground="#2a7a2a").grid(
            row=25, column=1, sticky="w", padx=12, pady=(10, 0)
        )
        ttk.Button(f, text=self.t("settings_save_btn"), command=self._on_save_settings).grid(
            row=26, column=1, sticky="w", padx=12, pady=(4, 12)
        )

    def _build_advanced_settings_tab(self) -> None:
        """Keep data-source credentials and collection behavior separate from basics."""
        canvas = tk.Canvas(self.tab_advanced, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_advanced, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tab_advanced.columnconfigure(0, weight=1)
        self.tab_advanced.rowconfigure(0, weight=1)

        f = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text=self.t("settings_community_sources")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 2)
        )
        self.tavily_enabled_var = tk.BooleanVar(value=True)
        self.reddit_enabled_var = tk.BooleanVar(value=True)
        self.x_enabled_var = tk.BooleanVar(value=False)
        self.youtube_enabled_var = tk.BooleanVar(value=False)
        self.hackernews_enabled_var = tk.BooleanVar(value=True)
        self.gdelt_enabled_var = tk.BooleanVar(value=True)
        sources = ttk.Frame(f)
        sources.grid(row=1, column=0, columnspan=2, sticky="w", padx=12)
        for index, (key, variable) in enumerate([
            ("settings_tavily", self.tavily_enabled_var),
            ("settings_reddit", self.reddit_enabled_var),
            ("settings_x", self.x_enabled_var),
            ("settings_youtube", self.youtube_enabled_var),
            ("settings_hackernews", self.hackernews_enabled_var),
            ("settings_gdelt", self.gdelt_enabled_var),
        ]):
            ttk.Checkbutton(sources, text=self.t(key), variable=variable).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 12)
            )
        self.include_time_unknown_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            sources,
            text=self.t("settings_include_time_unknown"),
            variable=self.include_time_unknown_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w")
        self.gdelt_source_language_var = tk.StringVar(value="global")
        ttk.Label(sources, text=self.t("settings_gdelt_language")).grid(
            row=4, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Combobox(
            sources,
            textvariable=self.gdelt_source_language_var,
            values=("global", "korean", "english"),
            state="readonly",
            width=12,
        ).grid(row=4, column=1, sticky="w", pady=(4, 0))
        self.gdelt_region_profile_var = tk.StringVar(value="auto")
        ttk.Label(sources, text=self.t("settings_gdelt_region")).grid(
            row=5, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Combobox(
            sources,
            textvariable=self.gdelt_region_profile_var,
            values=("auto", "global_even", "country_focus"),
            state="readonly",
            width=12,
        ).grid(row=5, column=1, sticky="w", pady=(4, 0))
        self.tavily_api_key_var = tk.StringVar()
        self.reddit_client_id_var = tk.StringVar()
        self.reddit_client_secret_var = tk.StringVar()
        self.reddit_user_agent_var = tk.StringVar()
        self.x_bearer_token_var = tk.StringVar()
        self.youtube_api_key_var = tk.StringVar()
        credentials = ttk.Frame(f)
        credentials.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 0))
        credentials.columnconfigure(1, weight=1)
        for row, (key, variable) in enumerate([
            ("settings_tavily_key", self.tavily_api_key_var),
            ("settings_reddit_id", self.reddit_client_id_var),
            ("settings_reddit_secret", self.reddit_client_secret_var),
            ("settings_reddit_agent", self.reddit_user_agent_var),
            ("settings_x_token", self.x_bearer_token_var),
            ("settings_youtube_key", self.youtube_api_key_var),
        ]):
            ttk.Label(credentials, text=self.t(key)).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(credentials, textvariable=variable, show="•").grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=2
            )
        ttk.Button(
            credentials,
            text=self.t("settings_test_connections"),
            command=self._on_test_community_sources,
        ).grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.source_test_status_var = tk.StringVar(value="")
        ttk.Label(credentials, textvariable=self.source_test_status_var, wraplength=520).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Separator(f).grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        ttk.Label(f, text=self.t("settings_backfill_days")).grid(
            row=4, column=0, sticky="w", padx=12, pady=6
        )
        self.new_topic_backfill_days_var = tk.IntVar(value=7)
        ttk.Spinbox(
            f, from_=1, to=90, textvariable=self.new_topic_backfill_days_var, width=8
        ).grid(row=4, column=1, sticky="w", padx=12, pady=6)
        ttk.Label(f, text=self.t("settings_backfill_interval_days")).grid(
            row=5, column=0, sticky="w", padx=12, pady=6
        )
        self.new_topic_backfill_interval_days_var = tk.IntVar(value=1)
        ttk.Spinbox(
            f, from_=1, to=30, textvariable=self.new_topic_backfill_interval_days_var, width=8
        ).grid(row=5, column=1, sticky="w", padx=12, pady=6)
        ttk.Label(f, text=self.t("settings_backfill_daily_count")).grid(row=6, column=0, sticky="w", padx=12, pady=6)
        self.backfill_daily_article_count_var = tk.IntVar(value=5)
        ttk.Spinbox(f, from_=1, to=30, textvariable=self.backfill_daily_article_count_var, width=8).grid(row=6, column=1, sticky="w", padx=12, pady=6)
        self.backfill_method_var = tk.StringVar(value="doc_api")
        ttk.Label(f, text=self.t("settings_backfill_method")).grid(row=7, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(f, textvariable=self.backfill_method_var, values=("doc_api", "gdelt_dump"), state="readonly", width=14).grid(row=7, column=1, sticky="w", padx=12, pady=6)
        self.dump_cache_policy_var = tk.StringVar(value="persistent")
        ttk.Label(f, text=self.t("settings_dump_cache_policy")).grid(row=8, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(f, textvariable=self.dump_cache_policy_var, values=("persistent", "compact_persistent", "temporary"), state="readonly", width=20).grid(row=8, column=1, sticky="w", padx=12, pady=6)
        self.dump_compact_after_days_var = tk.IntVar(value=3)
        ttk.Label(f, text=self.t("settings_dump_compact_after_days")).grid(row=9, column=0, sticky="w", padx=12, pady=6)
        ttk.Spinbox(f, from_=1, to=365, textvariable=self.dump_compact_after_days_var, width=8).grid(row=9, column=1, sticky="w", padx=12, pady=6)
        ttk.Label(f, text=self.t("settings_dump_cache_hint"), foreground="#5b6b7a", wraplength=620).grid(
            row=10, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 4)
        )
        self.dump_scan_mode_var = tk.StringVar(value="auto")
        ttk.Label(f, text=self.t("settings_dump_scan_mode")).grid(row=11, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(f, textvariable=self.dump_scan_mode_var, values=("auto", "sample", "full"), state="readonly", width=14).grid(row=11, column=1, sticky="w", padx=12, pady=6)
        self.dump_full_scan_max_days_var = tk.IntVar(value=3)
        ttk.Label(f, text=self.t("settings_dump_full_scan_days")).grid(row=12, column=0, sticky="w", padx=12, pady=6)
        ttk.Spinbox(f, from_=1, to=365, textvariable=self.dump_full_scan_max_days_var, width=8).grid(row=12, column=1, sticky="w", padx=12, pady=6)
        self.latest_news_priority_var = tk.StringVar(value="google_rss")
        ttk.Label(f, text=self.t("settings_latest_news_priority")).grid(row=13, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(f, textvariable=self.latest_news_priority_var, values=("google_rss", "gdelt"), state="readonly", width=14).grid(row=13, column=1, sticky="w", padx=12, pady=6)
        self.google_rss_region_profile_var = tk.StringVar(value="balanced")
        ttk.Label(f, text=self.t("settings_google_rss_region")).grid(row=14, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(f, textvariable=self.google_rss_region_profile_var, values=("balanced", "local_only"), state="readonly", width=14).grid(row=14, column=1, sticky="w", padx=12, pady=6)
        ttk.Label(f, text=self.t("settings_auto_times")).grid(row=15, column=0, sticky="w", padx=12, pady=6)
        self.auto_collection_times_var = tk.StringVar(value="09:00")
        ttk.Entry(f, textvariable=self.auto_collection_times_var, width=22).grid(row=15, column=1, sticky="w", padx=12, pady=6)
        buttons = ttk.Frame(f)
        buttons.grid(row=16, column=1, sticky="w", padx=12, pady=4)
        ttk.Button(buttons, text=self.t("settings_auto_register"), command=self._on_register_auto_collection).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text=self.t("settings_auto_unregister"), command=self._on_unregister_auto_collection).grid(row=0, column=1)
        alert_label = "분석 알림 조건" if self.lang == "ko" else "Analysis alert conditions"
        ttk.Label(f, text=alert_label).grid(row=17, column=0, sticky="w", padx=12, pady=(10, 2))
        self.analysis_alert_emerging_var = tk.BooleanVar(value=True)
        self.analysis_alert_rising_var = tk.BooleanVar(value=True)
        self.analysis_alert_contradictions_var = tk.BooleanVar(value=True)
        self.analysis_alert_data_quality_var = tk.BooleanVar(value=True)
        alert_frame = ttk.Frame(f)
        alert_frame.grid(row=18, column=0, columnspan=2, sticky="w", padx=12)
        alert_texts = (
            ("신뢰도 높은 초기 신호" if self.lang == "ko" else "High-confidence emerging signals", self.analysis_alert_emerging_var),
            ("시계열 상승 신호" if self.lang == "ko" else "Rising time-series signals", self.analysis_alert_rising_var),
            ("상충 근거" if self.lang == "ko" else "Contradictory evidence", self.analysis_alert_contradictions_var),
            ("데이터 품질 주의" if self.lang == "ko" else "Data-quality cautions", self.analysis_alert_data_quality_var),
        )
        for index, (text, variable) in enumerate(alert_texts):
            ttk.Checkbutton(alert_frame, text=text, variable=variable).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 14))
        dictionary_label = "사용자 태그 사전" if self.lang == "ko" else "Custom tag dictionary"
        ttk.Label(f, text=dictionary_label).grid(row=19, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 2))
        tag_frame = ttk.Frame(f)
        tag_frame.grid(row=20, column=0, columnspan=2, sticky="ew", padx=12)
        tag_frame.columnconfigure(1, weight=1)
        tag_frame.columnconfigure(3, weight=1)
        self.tag_canonical_var = tk.StringVar()
        self.tag_aliases_var = tk.StringVar()
        self.tag_parents_var = tk.StringVar()
        ttk.Label(tag_frame, text="정규 태그" if self.lang == "ko" else "Canonical tag").grid(row=0, column=0, sticky="w")
        ttk.Entry(tag_frame, textvariable=self.tag_canonical_var, width=20).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(tag_frame, text="찾을 표현 (쉼표 구분)" if self.lang == "ko" else "Aliases (comma-separated)").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(tag_frame, textvariable=self.tag_aliases_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(4, 0))
        ttk.Label(tag_frame, text="상위 태그 (쉼표 구분)" if self.lang == "ko" else "Parent tags (comma-separated)").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(tag_frame, textvariable=self.tag_parents_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(4, 0))
        ttk.Button(tag_frame, text="추가/수정" if self.lang == "ko" else "Add / update", command=self._upsert_tag_dictionary_entry).grid(row=3, column=1, sticky="w", pady=(6, 4))
        ttk.Button(tag_frame, text="선택 삭제" if self.lang == "ko" else "Delete selected", command=self._delete_tag_dictionary_entry).grid(row=3, column=2, sticky="w", padx=(6, 0), pady=(6, 4))
        self.tag_dictionary_tree = ttk.Treeview(tag_frame, columns=("aliases", "parents"), show="tree headings", height=5)
        self.tag_dictionary_tree.heading("#0", text="정규 태그" if self.lang == "ko" else "Canonical")
        self.tag_dictionary_tree.heading("aliases", text="찾을 표현" if self.lang == "ko" else "Aliases")
        self.tag_dictionary_tree.heading("parents", text="상위 태그" if self.lang == "ko" else "Parents")
        self.tag_dictionary_tree.column("#0", width=130, stretch=False, anchor="center")
        self.tag_dictionary_tree.column("aliases", width=250, anchor="center")
        self.tag_dictionary_tree.column("parents", width=180, anchor="center")
        self.tag_dictionary_tree.grid(row=4, column=0, columnspan=4, sticky="ew")
        self.tag_dictionary_tree.bind("<<TreeviewSelect>>", self._select_tag_dictionary_entry)
        ttk.Button(f, text=self.t("settings_save_btn"), command=self._on_save_settings).grid(
            row=21, column=1, sticky="w", padx=12, pady=(10, 12)
        )

    # ── Load values ────────────────────────────────────────────────────
    def _load_settings_into_widgets(self) -> None:
        self.vault_name_var.set(self.settings["vault_name"])
        self.vault_path_var.set(self.settings["vault_path"])
        self.model_var.set(self.settings["model"])
        self.api_base_var.set(self.settings["api_base"])
        self.api_key_var.set(load_env_value("OPENAI_API_KEY"))
        self.export_format_var.set(self.settings.get("export_format", "obsidian"))
        self.credibility_check_var.set(bool(self.settings.get("credibility_check", False)))
        self.credibility_threshold_var.set(int(self.settings.get("credibility_threshold", 40)))
        self.gossip_ratio_var.set(int(self.settings.get("gossip_ratio", 20)))
        community_sources = self.settings.get("community_sources", {})
        self.tavily_enabled_var.set(bool(community_sources.get("tavily", True)))
        self.reddit_enabled_var.set(bool(community_sources.get("reddit", True)))
        self.x_enabled_var.set(bool(community_sources.get("x", False)))
        self.youtube_enabled_var.set(bool(community_sources.get("youtube", False)))
        self.hackernews_enabled_var.set(bool(community_sources.get("hackernews", True)))
        self.gdelt_enabled_var.set(bool(community_sources.get("gdelt", True)))
        self.gdelt_source_language_var.set(self.settings.get("gdelt_source_language", "global"))
        self.gdelt_region_profile_var.set(self.settings.get("gdelt_region_profile", "auto"))
        self.new_topic_backfill_days_var.set(int(self.settings.get("new_topic_backfill_days", 7)))
        self.new_topic_backfill_interval_days_var.set(int(self.settings.get("new_topic_backfill_interval_days", 1)))
        self.backfill_daily_article_count_var.set(int(self.settings.get("backfill_daily_article_count", 5)))
        self.backfill_method_var.set(self.settings.get("backfill_method", "doc_api"))
        self.dump_cache_policy_var.set(self.settings.get("dump_cache_policy", "persistent"))
        self.dump_compact_after_days_var.set(int(self.settings.get("dump_compact_after_days", 3)))
        self.dump_scan_mode_var.set(self.settings.get("dump_scan_mode", "auto"))
        self.dump_full_scan_max_days_var.set(int(self.settings.get("dump_full_scan_max_days", 3)))
        self.latest_news_priority_var.set(self.settings.get("latest_news_priority", "google_rss"))
        self.google_rss_region_profile_var.set(self.settings.get("google_rss_region_profile", "balanced"))
        self.auto_collection_times_var.set(", ".join(self.settings.get("auto_collection_times", ["09:00"])))
        self.include_time_unknown_var.set(bool(self.settings.get("include_time_unknown", False)))
        self.tavily_api_key_var.set(load_env_value("TAVILY_API_KEY"))
        self.reddit_client_id_var.set(load_env_value("REDDIT_CLIENT_ID"))
        self.reddit_client_secret_var.set(load_env_value("REDDIT_CLIENT_SECRET"))
        self.reddit_user_agent_var.set(load_env_value("REDDIT_USER_AGENT"))
        self.x_bearer_token_var.set(load_env_value("X_BEARER_TOKEN"))
        self.youtube_api_key_var.set(load_env_value("YOUTUBE_API_KEY"))
        self.language_var.set(self.settings.get("output_language", DEFAULT_OUTPUT_LANGUAGE))
        self._on_toggle_credibility()
        self._on_threshold_change()
        self._on_gossip_ratio_change()
        self.analysis_reliability_var.set(int(self.settings.get("analysis_reliability_weight", 50)))
        self.analysis_freshness_var.set(int(self.settings.get("analysis_freshness_weight", 30)))
        self.analysis_signal_var.set(int(self.settings.get("analysis_early_signal_weight", 20)))
        self.analysis_period_var.set(int(self.settings.get("analysis_period_days", 30)))
        self.analysis_alert_emerging_var.set(bool(self.settings.get("analysis_alert_emerging", True)))
        self.analysis_alert_rising_var.set(bool(self.settings.get("analysis_alert_rising", True)))
        self.analysis_alert_contradictions_var.set(bool(self.settings.get("analysis_alert_contradictions", True)))
        self.analysis_alert_data_quality_var.set(bool(self.settings.get("analysis_alert_data_quality", True)))
        dictionary_path = DATA_VAULT_DIR / "tag_dictionary.json"
        try:
            dictionary_value = json.loads(dictionary_path.read_text(encoding="utf-8")) if dictionary_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            dictionary_value = {}
        self.tag_dictionary_entries = dictionary_value if isinstance(dictionary_value, dict) else {}
        self._refresh_tag_dictionary_tree()
        self._refresh_analysis_topics()

    def _refresh_favorites_list(self) -> None:
        self.fav_listbox.delete(0, "end")
        for t in self.favorites.load():
            self.fav_listbox.insert("end", t)

    def _refresh_analysis_topics(self) -> None:
        topics = self.favorites.load()
        self.analysis_topic_combo["values"] = topics
        if topics and not self.analysis_topic_var.get():
            self.analysis_topic_var.set(topics[0])
        self._draw_analysis_history()
        self._draw_analysis_comparison()

    def _analysis_history_path(self, topic: str) -> Path:
        return DATA_VAULT_DIR / "topics" / _slugify(topic) / "_analysis_history.json"

    def _draw_analysis_comparison(self) -> None:
        widget = getattr(self, "analysis_comparison_text", None)
        if widget is None:
            return
        topic = self.analysis_topic_var.get().strip()
        try:
            history = json.loads(self._analysis_history_path(topic).read_text(encoding="utf-8")) if topic else []
        except (OSError, json.JSONDecodeError):
            history = []
        if not isinstance(history, list) or len(history) < 2:
            text = "분석을 두 번 이상 실행하면 직전 결과와의 변화가 표시됩니다." if self.lang == "ko" else "Run Analysis at least twice to see changes from the previous result."
        else:
            previous, current = history[-2], history[-1]
            def items(snapshot):
                return {
                    row.get("key") or row.get("title", ""): {**row, "category": category}
                    for category in ("rumors", "emerging_signals", "confirmed_trends")
                    for row in snapshot.get(category, [])
                    if row.get("key") or row.get("title")
                }
            before, after = items(previous), items(current)
            added = [row for key, row in after.items() if key not in before]
            removed = [row for key, row in before.items() if key not in after]
            moved = [row for key, row in after.items() if key in before and row["category"] != before[key]["category"]]
            changed = [row for key, row in after.items() if key in before and abs(float(row.get("confidence", 0)) - float(before[key].get("confidence", 0))) >= 10]
            label = lambda rows: ", ".join(str(row.get("title", ""))[:55] for row in rows[:3]) or "-"
            prefix = "비교" if self.lang == "ko" else "Comparison"
            text = "\n".join([
                f"{prefix}: {previous.get('date', '?')} → {current.get('date', '?')}",
                ("새 신호: " if self.lang == "ko" else "New signals: ") + label(added),
                ("사라진 신호: " if self.lang == "ko" else "No longer present: ") + label(removed),
                ("등급 변화: " if self.lang == "ko" else "Category changes: ") + label(moved),
                ("신뢰도 ±10 이상: " if self.lang == "ko" else "Confidence changes (10+): ") + label(changed),
            ])
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _draw_analysis_history(self) -> None:
        """Draw category transitions without requiring a charting dependency."""
        canvas = getattr(self, "analysis_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        topic = self.analysis_topic_var.get().strip()
        if not topic:
            canvas.create_text(12, 18, anchor="nw", text=self.t("analysis_no_history"))
            canvas.configure(scrollregion=(0, 0, 700, 60))
            return
        path = self._analysis_history_path(topic)
        try:
            history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except (json.JSONDecodeError, OSError):
            history = []
        if not isinstance(history, list) or not history:
            canvas.create_text(12, 18, anchor="nw", text=self.t("analysis_no_history"))
            canvas.configure(scrollregion=(0, 0, 700, 60))
            return

        # Keep the latest 10 analysis runs and the most frequently recurring signals.
        history = history[-10:]
        items_by_key = {}
        for snap in history:
            for category in ("rumors", "emerging_signals", "confirmed_trends"):
                for item in snap.get(category, []):
                    key = item.get("key") or item.get("title", "")
                    if key:
                        items_by_key.setdefault(
                            key,
                            {"key": key, "title": item.get("title", ""), "events": {}},
                        )
        # Prefer recurring items; fall back to the most recent items.
        ranked = sorted(
            items_by_key.values(),
            key=lambda x: sum(len(v) for v in x["events"].values()),
            reverse=True,
        )[:8]

        width = max(canvas.winfo_width(), 720)

        # Reserve enough room for trend labels instead of truncating them with
        # "...".  The label column grows with the longest title, but is capped
        # so the actual timeline still has useful horizontal space.
        label_font = tkfont.nametofont("TkDefaultFont").copy()
        label_font.configure(size=10)
        max_title_px = max(
            (label_font.measure(str(item.get("title", ""))) for item in ranked),
            default=0,
        )
        left = min(max(250, max_title_px + 24), max(360, int(width * 0.55)))
        right, top = 20, 48
        label_wrap_px = max(180, left - 24)
        row_h = 42
        plot_w = max(320, width - left - right)
        run_count = len(history)
        x_positions = [left + (plot_w * i / max(1, run_count - 1)) for i in range(run_count)]
        colors = {
            "rumors": "#8a8f98",
            "emerging_signals": "#d08b2e",
            "confirmed_trends": "#3b7ddd",
        }
        labels = {
            "rumors": "Rumor",
            "emerging_signals": "Emerging",
            "confirmed_trends": "Confirmed",
        }

        canvas.create_text(12, 14, anchor="nw", text=topic, font=("TkDefaultFont", 10, "bold"))
        # Legend
        lx = left
        for key in ("rumors", "emerging_signals", "confirmed_trends"):
            canvas.create_oval(lx, 17, lx + 8, 25, fill=colors[key], outline="")
            canvas.create_text(lx + 13, 21, anchor="w", text=labels[key])
            lx += 92

        for i, snap in enumerate(history):
            x = x_positions[i]
            canvas.create_line(x, top - 5, x, top + row_h * max(1, len(ranked)) + 8, fill="#e5e7eb")
            canvas.create_text(x, top - 18, text=str(snap.get("date", ""))[-5:])

        def wrap_to_pixels(text: str, max_px: int) -> list[str]:
            """Wrap a trend title by rendered pixel width so no label is clipped."""
            words = str(text or "").split()
            if not words:
                return [""]
            lines = []
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if label_font.measure(candidate) <= max_px:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                    current = word
                else:
                    # Handle a single unusually long token without truncating it.
                    chunk = ""
                    for ch in word:
                        candidate = chunk + ch
                        if chunk and label_font.measure(candidate) > max_px:
                            lines.append(chunk)
                            chunk = ch
                        else:
                            chunk = candidate
                    current = chunk
            if current:
                lines.append(current)
            return lines or [""]

        row_layout = []
        y = top
        for item in ranked:
            lines = wrap_to_pixels(item["title"], label_wrap_px)
            # Keep each row compact while allowing long titles to use 2–3 lines.
            line_count = min(max(1, len(lines)), 3)
            lines = lines[:line_count]
            row_height = max(row_h, 18 * line_count + 12)
            row_layout.append((item, y + row_height / 2, lines))
            y += row_height

        for item, y, lines in row_layout:
            canvas.create_text(
                left - 8,
                y,
                anchor="e",
                text="\n".join(lines),
                justify="right",
                font=label_font,
            )
            previous = None
            item_key = item["key"]
            for i, snap in enumerate(history):
                event = None
                for category in ("rumors", "emerging_signals", "confirmed_trends"):
                    for candidate in snap.get(category, []):
                        if (candidate.get("key") or candidate.get("title", "")) == item_key:
                            event = (category, float(candidate.get("confidence", 0)))
                            break
                    if event:
                        break
                if event:
                    category, confidence = event
                    x, yy = x_positions[i], y
                    if previous:
                        canvas.create_line(
                            previous[0], previous[1], x, yy,
                            fill=colors[category], width=2
                        )
                    radius = 5 + min(3, confidence / 35)
                    canvas.create_oval(
                        x-radius, yy-radius, x+radius, yy+radius,
                        fill=colors[category], outline=""
                    )
                    previous = (x, yy)
                else:
                    previous = None

        height = max(top + 30, y + 18)
        canvas.configure(scrollregion=(0, 0, width, height))

    def _refresh_analysis_history(self) -> None:
        self._draw_analysis_history()
        self._draw_analysis_comparison()

    def _refresh_tag_dictionary_tree(self) -> None:
        tree = getattr(self, "tag_dictionary_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        dictionary = getattr(self, "tag_dictionary_entries", {})
        aliases = dictionary.get("aliases", {}) if isinstance(dictionary, dict) else {}
        parents = dictionary.get("parents", {}) if isinstance(dictionary, dict) else {}
        for canonical in sorted(set(aliases) | set(parents)):
            tree.insert("", "end", iid=canonical, text=canonical, values=(", ".join(aliases.get(canonical, [])), ", ".join(parents.get(canonical, []))))

    def _upsert_tag_dictionary_entry(self) -> None:
        canonical = "_".join(self.tag_canonical_var.get().strip().lower().split())
        aliases = [value.strip() for value in self.tag_aliases_var.get().split(",") if value.strip()]
        parents = ["_".join(value.strip().lower().split()) for value in self.tag_parents_var.get().split(",") if value.strip()]
        if not canonical or not aliases:
            messagebox.showinfo(self.t("msg_save_title"), "정규 태그와 하나 이상의 찾을 표현을 입력하세요." if self.lang == "ko" else "Enter a canonical tag and at least one alias.")
            return
        dictionary = getattr(self, "tag_dictionary_entries", {})
        dictionary.setdefault("aliases", {})[canonical] = aliases
        if parents:
            dictionary.setdefault("parents", {})[canonical] = parents
        else:
            dictionary.setdefault("parents", {}).pop(canonical, None)
        self.tag_dictionary_entries = dictionary
        self._refresh_tag_dictionary_tree()
        self.tag_canonical_var.set("")
        self.tag_aliases_var.set("")
        self.tag_parents_var.set("")

    def _delete_tag_dictionary_entry(self) -> None:
        selected = self.tag_dictionary_tree.selection()
        if not selected:
            return
        dictionary = getattr(self, "tag_dictionary_entries", {})
        for canonical in selected:
            dictionary.get("aliases", {}).pop(canonical, None)
            dictionary.get("parents", {}).pop(canonical, None)
        self.tag_dictionary_entries = dictionary
        self._refresh_tag_dictionary_tree()

    def _select_tag_dictionary_entry(self, _event=None) -> None:
        selected = self.tag_dictionary_tree.selection()
        if not selected:
            return
        canonical = selected[0]
        dictionary = getattr(self, "tag_dictionary_entries", {})
        self.tag_canonical_var.set(canonical)
        self.tag_aliases_var.set(", ".join(dictionary.get("aliases", {}).get(canonical, [])))
        self.tag_parents_var.set(", ".join(dictionary.get("parents", {}).get(canonical, [])))

    # ── Settings-tab events ───────────────────────────────────────────────
    def _on_browse_vault(self) -> None:
        chosen = filedialog.askdirectory(
            title=self.t("settings_vault_path"), initialdir=self.vault_path_var.get() or str(PROJECT_ROOT)
        )
        if chosen:
            self.vault_path_var.set(chosen)

    def _on_test_community_sources(self) -> None:
        """Run opt-in API credential checks outside the Tkinter event loop."""
        enabled_crawlers = []
        if self.tavily_enabled_var.get():
            enabled_crawlers.append(("Tavily Social", TavilySocialCrawler(self.tavily_api_key_var.get())))
        if self.reddit_enabled_var.get():
            enabled_crawlers.append(("Reddit", RedditCrawler(
                self.reddit_client_id_var.get(),
                self.reddit_client_secret_var.get(),
                self.reddit_user_agent_var.get(),
            )))
        if self.x_enabled_var.get():
            enabled_crawlers.append(("X", XCrawler(self.x_bearer_token_var.get())))
        if self.youtube_enabled_var.get():
            enabled_crawlers.append(("YouTube", YouTubeCrawler(self.youtube_api_key_var.get())))
        if self.hackernews_enabled_var.get():
            enabled_crawlers.append(("Hacker News", HackerNewsCrawler()))
        if self.gdelt_enabled_var.get():
            enabled_crawlers.append(("GDELT", GdeltCrawler()))

        if not enabled_crawlers:
            self.source_test_status_var.set("No community source is enabled.")
            return

        self.source_test_status_var.set(self.t("settings_test_running"))

        def check_connections() -> None:
            messages = []
            for name, crawler in enabled_crawlers:
                connected, message = crawler.validate_connection()
                marker = "✓" if connected else "✗"
                messages.append(f"{marker} {name}: {message}")
            self.after(0, self.source_test_status_var.set, " | ".join(messages))

        threading.Thread(target=check_connections, daemon=True).start()

    def _parse_auto_collection_times(self) -> list[str]:
        times = [item.strip() for item in self.auto_collection_times_var.get().split(",") if item.strip()]
        if not 1 <= len(times) <= 3 or any(not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", item) for item in times):
            raise ValueError("Enter one to three times in HH:MM format.")
        return times

    def _on_register_auto_collection(self) -> None:
        try:
            times = self._parse_auto_collection_times()
        except ValueError as error:
            messagebox.showerror(self.t("msg_save_title"), str(error))
            return
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "scripts" / "register_auto_collection.ps1"), "-Times", *times]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            messagebox.showinfo(self.t("settings_auto_register"), f"Registered: {', '.join(times)}")
        else:
            messagebox.showerror(self.t("settings_auto_register"), result.stderr or result.stdout)

    def _on_unregister_auto_collection(self) -> None:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", "Unregister-ScheduledTask -TaskName 'AI Research Lab Auto Collect' -Confirm:$false"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            messagebox.showinfo(self.t("settings_auto_unregister"), "Removed.")
        else:
            messagebox.showerror(self.t("settings_auto_unregister"), result.stderr or result.stdout)

    def _on_toggle_credibility(self) -> None:
        state = "normal" if self.credibility_check_var.get() else "disabled"
        self.threshold_scale.configure(state=state)
        self._on_threshold_change()

    def _on_threshold_change(self, _value=None) -> None:
        v = self.credibility_threshold_var.get()
        if not self.credibility_check_var.get():
            self.threshold_label_var.set(self.t("threshold_off"))
            return
        if v >= 70:
            hint = self.t("threshold_high")
        elif v <= 20:
            hint = self.t("threshold_low")
        else:
            hint = self.t("threshold_mid")
        self.threshold_label_var.set(self.t("threshold_fmt", v=v, hint=hint))

    def _on_gossip_ratio_change(self, _value=None) -> None:
        v = int(self.gossip_ratio_var.get())
        if v <= 20:
            hint = self.t("source_balance_low")
        elif v >= 70:
            hint = self.t("source_balance_high")
        else:
            hint = self.t("source_balance_mid")
        self.source_balance_label_var.set(self.t("source_balance_fmt", v=v, hint=hint))

    def _on_save_settings(self) -> None:
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror(self.t("msg_save_title"), self.t("msg_save_api_key_required"))
            return
        if not self.vault_name_var.get().strip() or not self.vault_path_var.get().strip():
            messagebox.showerror(self.t("msg_save_title"), self.t("msg_save_vault_required"))
            return

        Path(self.vault_path_var.get().strip()).mkdir(parents=True, exist_ok=True)
        try:
            auto_collection_times = self._parse_auto_collection_times()
        except ValueError as error:
            messagebox.showerror(self.t("msg_save_title"), str(error))
            return
        dictionary_value = getattr(self, "tag_dictionary_entries", {})
        dictionary_path = DATA_VAULT_DIR / "tag_dictionary.json"
        dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        dictionary_path.write_text(json.dumps(dictionary_value, ensure_ascii=False, indent=2), encoding="utf-8")

        self.settings = {
            "vault_name": self.vault_name_var.get().strip(),
            "vault_path": self.vault_path_var.get().strip(),
            "model": (self.model_var.get().strip() or MODEL_PRESETS[0]),
            "api_base": self.api_base_var.get().strip(),
            "export_format": self.export_format_var.get().strip() or "obsidian",
            "credibility_check": bool(self.credibility_check_var.get()),
            "credibility_threshold": int(self.credibility_threshold_var.get()),
            "gossip_ratio": int(self.gossip_ratio_var.get()),
            "community_sources": {
                "tavily": bool(self.tavily_enabled_var.get()),
                "reddit": bool(self.reddit_enabled_var.get()),
                "x": bool(self.x_enabled_var.get()),
                "youtube": bool(self.youtube_enabled_var.get()),
                "hackernews": bool(self.hackernews_enabled_var.get()),
                "gdelt": bool(self.gdelt_enabled_var.get()),
            },
            "include_time_unknown": bool(self.include_time_unknown_var.get()),
            "gdelt_source_language": self.gdelt_source_language_var.get(),
            "gdelt_region_profile": self.gdelt_region_profile_var.get(),
            "latest_news_priority": self.latest_news_priority_var.get(),
            "google_rss_region_profile": self.google_rss_region_profile_var.get(),
            "new_topic_backfill_days": int(self.new_topic_backfill_days_var.get()),
            "new_topic_backfill_interval_days": int(self.new_topic_backfill_interval_days_var.get()),
            "backfill_daily_article_count": int(self.backfill_daily_article_count_var.get()),
            "backfill_method": self.backfill_method_var.get(),
            "dump_cache_policy": self.dump_cache_policy_var.get(),
            "dump_compact_after_days": int(self.dump_compact_after_days_var.get()),
            "dump_scan_mode": self.dump_scan_mode_var.get(),
            "dump_full_scan_max_days": int(self.dump_full_scan_max_days_var.get()),
            "auto_collection_times": auto_collection_times,
            "output_language": self.language_var.get().strip() or DEFAULT_OUTPUT_LANGUAGE,
            "analysis_reliability_weight": int(self.analysis_reliability_var.get()),
            "analysis_freshness_weight": int(self.analysis_freshness_var.get()),
            "analysis_early_signal_weight": int(self.analysis_signal_var.get()),
            "analysis_period_days": int(self.analysis_period_var.get()),
            "analysis_alert_emerging": bool(self.analysis_alert_emerging_var.get()),
            "analysis_alert_rising": bool(self.analysis_alert_rising_var.get()),
            "analysis_alert_contradictions": bool(self.analysis_alert_contradictions_var.get()),
            "analysis_alert_data_quality": bool(self.analysis_alert_data_quality_var.get()),
        }
        save_settings(self.settings)

        # Apply the selected output language immediately to subsequent runs.
        self.output_language = self.settings["output_language"]
        self.lang = resolve_ui_lang(self.output_language)

        save_env_values({
            "OPENAI_API_KEY": api_key,
            "OPENAI_API_BASE": self.api_base_var.get().strip(),
            "TAVILY_API_KEY": self.tavily_api_key_var.get().strip(),
            "REDDIT_CLIENT_ID": self.reddit_client_id_var.get().strip(),
            "REDDIT_CLIENT_SECRET": self.reddit_client_secret_var.get().strip(),
            "REDDIT_USER_AGENT": self.reddit_user_agent_var.get().strip(),
            "X_BEARER_TOKEN": self.x_bearer_token_var.get().strip(),
            "YOUTUBE_API_KEY": self.youtube_api_key_var.get().strip(),
        })
        self.settings_status_var.set(self.t("settings_saved_msg"))
        self.after(3500, lambda: self.settings_status_var.set(""))

    # ── Favorites-tab events ──────────────────────────────────────────────
    def _on_favorite_selected(self, _event=None) -> None:
        sel = self.fav_listbox.curselection()
        if sel:
            self.topic_var.set(self.fav_listbox.get(sel[0]))

    def _on_remove_favorite(self) -> None:
        sel = self.fav_listbox.curselection()
        if not sel:
            messagebox.showinfo(self.t("msg_fav_delete_title"), self.t("msg_fav_delete_body"))
            return
        self.favorites.remove(sel[0])
        self._refresh_favorites_list()

    # ── Shared execution logic ────────────────────────────────────────────
    def _guard_before_run(self) -> bool:
        if self.runner.is_running:
            messagebox.showinfo(self.t("msg_running_title"), self.t("msg_running_body"))
            return False
        if not load_env_value("OPENAI_API_KEY"):
            messagebox.showerror(self.t("msg_api_key_missing_title"), self.t("msg_api_key_missing_body"))
            return False
        return True

    def _start_run(
        self,
        args: list[str],
        buttons: list[ttk.Button],
        *,
        on_success=None,
        clear_log: bool = True,
    ) -> None:
        if clear_log:
            self._clear_log()
        for b in buttons:
            b.state(["disabled"])
        self.cancel_btn.state(["!disabled"])
        self.status_var.set(self.t("status_running"))
        self.progress.start(12)
        self._active_buttons = buttons
        self._run_on_success = on_success
        self.runner.run(args)

    def _cancel_run(self) -> None:
        if self.runner.cancel():
            self.status_var.set(self.t("status_cancelled"))
            self.cancel_btn.state(["disabled"])
            self._append_log("\n[Cancelled by user]\n")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "line":
                    self._append_log(str(payload))
                    self._handle_http_consent_request(str(payload))
                elif kind == "done":
                    self.progress.stop()
                    self.cancel_btn.state(["disabled"])
                    for b in getattr(self, "_active_buttons", []):
                        b.state(["!disabled"])
                    returncode = payload
                    if self.runner._cancel_requested:
                        self.status_var.set(self.t("status_cancelled"))
                    elif returncode == 0:
                        self.status_var.set(self.t("status_done"))
                        self._refresh_analysis_history()
                        on_success = getattr(self, "_run_on_success", None)
                        self._run_on_success = None
                        if on_success is not None:
                            self.after(0, on_success)
                    else:
                        self.status_var.set(self.t("status_error"))
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _new_http_consent_file(self) -> Path:
        return DATA_VAULT_DIR / f".http-consent-{uuid.uuid4().hex}.json"

    def _missing_backfill_dates(self, topic: str, days: int) -> list[str]:
        """Return missing days, plus dates that need an elected Full re-scan."""
        topic_dir = DATA_VAULT_DIR / "topics" / _slugify(topic)
        snapshots = topic_dir / "snapshots"
        covered: set[date] = set()
        full_covered: set[date] = set()
        snapshot_paths = list(snapshots.glob("*.json")) if snapshots.exists() else []
        # A genuinely new topic has no directory at all, so its first Topic
        # Research establishes the baseline.  An existing topic directory with
        # deleted/corrupt snapshots is different: every configured day is a
        # real gap and must be eligible for recovery/backfill.
        if not snapshot_paths:
            if not topic_dir.exists():
                return []
            return [
                (date.today() - timedelta(days=offset)).isoformat()
                for offset in range(days, 0, -1)
            ]
        for path in snapshot_paths:
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                start_text = snapshot.get("window_start")
                end_text = snapshot.get("window_end")
                if start_text and end_text:
                    start_day = datetime.fromisoformat(start_text).date()
                    end_day = datetime.fromisoformat(end_text).date()
                    cursor = start_day
                    while cursor < end_day:
                        covered.add(cursor)
                        if snapshot.get("backfill_scan_mode") == "full":
                            full_covered.add(cursor)
                        cursor += timedelta(days=1)
                elif snapshot.get("collected_at"):
                    collected_day = datetime.fromisoformat(snapshot["collected_at"]).date()
                    covered.add(collected_day)
                    if snapshot.get("backfill_scan_mode") == "full":
                        full_covered.add(collected_day)
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                continue
        # Today's Topic Research will collect today itself. Backfill only the
        # completed days before it, so a seven-day setting means seven gaps.
        expected = [date.today() - timedelta(days=offset) for offset in range(days, 0, -1)]
        required_scan_mode = resolve_dump_scan_mode(
            self.dump_scan_mode_var.get(), days, self.dump_full_scan_max_days_var.get()
        )
        return [
            item.isoformat()
            for item in expected
            if item not in covered
            or (required_scan_mode == "full" and item not in full_covered)
        ]

    def _handle_http_consent_request(self, line: str) -> None:
        marker = "[HTTP_CONSENT_REQUIRED] "
        if marker not in line:
            return
        candidate = line.split(marker, 1)[1].strip()
        try:
            consent_path = Path(candidate).resolve()
            vault_path = DATA_VAULT_DIR.resolve()
            if not consent_path.is_relative_to(vault_path):
                self._append_log("[Security] ignored an HTTP consent request outside the data vault.\n")
                return
        except (OSError, ValueError):
            return
        if self.lang == "ko":
            message = (
                "GDELT HTTPS 인증서를 검증할 수 없어 현재 백필 작업이 대기 중입니다.\n\n"
                "HTTP로 계속하면 전송 중 데이터가 변경되지 않았는지 확인할 수 없습니다. "
                "이번 실행에 한해서 HTTP 연결을 허용할까요?\n\n"
                "아니오를 선택하면 이 실행의 나머지 날짜도 HTTPS만 시도하며 팝업 없이 보류로 기록됩니다. 다음 수집 때 다시 물어봅니다."
            )
        else:
            message = (
                "The GDELT HTTPS certificate could not be verified, so this backfill is waiting.\n\n"
                "HTTP cannot verify that data was not modified in transit. Allow HTTP for this run only?\n\n"
                "Choosing No records this and the remaining dates as pending without another prompt; the next collection asks again."
            )
        allowed = messagebox.askyesno("GDELT dump security warning", message, icon="warning")
        try:
            consent_path.write_text(json.dumps({"allow": allowed}), encoding="utf-8")
        except OSError as error:
            self._append_log(f"[Security] could not send HTTP consent response: {error}\n")

    # ── Run Topic Research tab ────────────────────────────────────────────
    def _on_run_topic(self) -> None:
        if not self._guard_before_run():
            return
        topic = self.topic_var.get().strip()
        if not topic:
            sel = self.fav_listbox.curselection()
            if sel:
                topic = self.fav_listbox.get(sel[0])
        if not topic:
            messagebox.showinfo(self.t("msg_topic_required_title"), self.t("msg_topic_required_body"))
            return

        if topic not in self.favorites.load() and self.save_favorite_var.get():
            self.favorites.add(topic)
            self._refresh_favorites_list()
            self._refresh_analysis_topics()

        # Always read the currently selected output language from Settings.
        # Previously this used self.settings, which could still contain the
        # language from the last saved configuration.
        current_output_language = self.language_var.get().strip() or DEFAULT_OUTPUT_LANGUAGE
        self.settings["output_language"] = current_output_language
        args = [
            "scripts/topic_digest.py",
            "--topic", topic,
            "--limit", str(self.limit_var.get()),
            "--vault-name", self.settings["vault_name"],
            "--output-dir", self.settings["vault_path"],
            "--data-dir", str(DATA_VAULT_DIR),
            "--model", self.settings["model"],
            "--format", self.settings.get("export_format", "obsidian"),
            "--output-language", current_output_language,
            "--gossip-ratio", str(self.gossip_ratio_var.get()),
            "--community-sources", ",".join(
                source for source, enabled in self.settings.get("community_sources", {}).items() if enabled
            ),
            "--gdelt-source-language", self.settings.get("gdelt_source_language", "global"),
            "--gdelt-region-profile", self.settings.get("gdelt_region_profile", "auto"),
            "--latest-news-priority", self.settings.get("latest_news_priority", "google_rss"),
            "--google-rss-region-profile", self.settings.get("google_rss_region_profile", "balanced"),
        ]
        if self.settings.get("include_time_unknown", False):
            args.append("--include-time-unknown")
        if self.settings.get("credibility_check"):
            args += [
                "--credibility-check",
                "--credibility-threshold", str(self.settings.get("credibility_threshold", 40)),
            ]
        # A queued dump retry remains actionable even if the preferred method
        # was later changed to DOC API.
        queued_dump_days = pending_days(DATA_VAULT_DIR, topic)
        if queued_dump_days and self.gdelt_enabled_var.get():
            backfill_args = [
                "scripts/backfill_gdelt_dump.py", "--topic", topic, "--backfill-days", "1",
                "--collection-interval-days", "1", "--limit", str(self.limit_var.get()), "--daily-limit", str(self.backfill_daily_article_count_var.get()),
                "--cache-policy", self.dump_cache_policy_var.get(), "--data-dir", str(DATA_VAULT_DIR), "--output-dir", self.settings["vault_path"],
                "--compact-after-days", str(self.dump_compact_after_days_var.get()),
                "--scan-mode", self.dump_scan_mode_var.get(), "--full-scan-max-days", str(self.dump_full_scan_max_days_var.get()), "--output-language", current_output_language, "--retry-pending", "--http-consent-file",
                str(self._new_http_consent_file()),
            ]
            self._start_run(backfill_args, [self.topic_run_btn], on_success=lambda: self._start_run(args, [self.topic_run_btn], clear_log=False))
            return
        days = max(1, int(self.new_topic_backfill_days_var.get()))
        topic_data_dir = DATA_VAULT_DIR / "topics" / _slugify(topic)
        # A first-ever topic has no recovery gap yet, but the user can opt in
        # to a short baseline backfill.  This is deliberately a prompt, never
        # an automatic long-running job.
        if not topic_data_dir.exists() and self.backfill_method_var.get() == "gdelt_dump":
            if not self.gdelt_enabled_var.get():
                messagebox.showwarning(self.t("msg_backfill_title"), self.t("msg_backfill_disabled"))
            else:
                if self.lang == "ko":
                    prompt = f"새 토픽입니다. 최근 {days}일의 초기 기준선 데이터를 백필한 뒤 최신 Topic Research를 실행할까요?"
                else:
                    prompt = f"This is a new topic. Backfill {days} days for an initial baseline before running the latest Topic Research?"
                if messagebox.askyesno(self.t("msg_backfill_title"), prompt):
                    backfill_args = [
                        "scripts/backfill_gdelt_dump.py", "--topic", topic,
                        "--backfill-days", str(days),
                        "--collection-interval-days", str(max(1, int(self.new_topic_backfill_interval_days_var.get()))),
                        "--daily-limit", str(self.backfill_daily_article_count_var.get()),
                        "--cache-policy", self.dump_cache_policy_var.get(), "--data-dir", str(DATA_VAULT_DIR),
                        "--compact-after-days", str(self.dump_compact_after_days_var.get()),
                        "--output-dir", self.settings["vault_path"], "--scan-mode", self.dump_scan_mode_var.get(), "--full-scan-max-days", str(self.dump_full_scan_max_days_var.get()),
                        "--output-language", current_output_language, "--http-consent-file", str(self._new_http_consent_file()),
                    ]
                    self._start_run(backfill_args, [self.topic_run_btn], on_success=lambda: self._start_run(args, [self.topic_run_btn], clear_log=False))
                    return
        missing_dates = self._missing_backfill_dates(topic, days)
        if missing_dates and self.backfill_method_var.get() == "gdelt_dump":
            if not self.gdelt_enabled_var.get():
                messagebox.showwarning(self.t("msg_backfill_title"), self.t("msg_backfill_disabled"))
                self._start_run(args, [self.topic_run_btn])
                return
            required_scan_mode = resolve_dump_scan_mode(
                self.dump_scan_mode_var.get(), days, self.dump_full_scan_max_days_var.get()
            )
            if self.lang == "ko" and required_scan_mode == "full":
                prompt = (
                    f"최근 {days}일 중 {len(missing_dates)}일은 Full Dump 스캔 기록이 없습니다.\n\n"
                    "해당 날짜의 Sample 스냅샷을 Full 결과로 갱신한 뒤 최신 Topic Research를 실행할까요?"
                )
            elif self.lang == "ko":
                prompt = f"vault에서 최근 {days}일 중 {len(missing_dates)}일의 수집 기록이 비어 있습니다.\n\n누락된 날짜만 백필한 뒤 최신 Topic Research를 실행할까요?"
            elif required_scan_mode == "full":
                prompt = (
                    f"{len(missing_dates)} of the previous {days} days do not have Full dump coverage.\n\n"
                    "Refresh those Sample snapshots with Full-scan results before the latest Topic Research?"
                )
            else:
                prompt = f"The vault is missing {len(missing_dates)} of the previous {days} completed days.\n\nBackfill only those dates before running the latest Topic Research?"
            if messagebox.askyesno(self.t("msg_backfill_title"), prompt):
                backfill_args = [
                    "scripts/backfill_gdelt_dump.py", "--topic", topic,
                    "--backfill-days", str(days), "--dates", ",".join(missing_dates),
                    "--collection-interval-days", str(max(1, int(self.new_topic_backfill_interval_days_var.get()))),
                    "--daily-limit", str(self.backfill_daily_article_count_var.get()),
                    "--cache-policy", self.dump_cache_policy_var.get(), "--data-dir", str(DATA_VAULT_DIR), "--output-dir", self.settings["vault_path"],
                    "--compact-after-days", str(self.dump_compact_after_days_var.get()),
                    "--scan-mode", self.dump_scan_mode_var.get(), "--full-scan-max-days", str(self.dump_full_scan_max_days_var.get()), "--output-language", current_output_language,
                    "--http-consent-file", str(self._new_http_consent_file()),
                ]
                self._start_run(backfill_args, [self.topic_run_btn], on_success=lambda: self._start_run(args, [self.topic_run_btn], clear_log=False))
                return
        self._start_run(args, [self.topic_run_btn])


    # ── Run Analysis tab ──────────────────────────────────────────────────
    def _on_run_analysis(self) -> None:
        if not self._guard_before_run():
            return
        topic = self.analysis_topic_var.get().strip()
        if not topic:
            messagebox.showinfo(self.t("msg_topic_required_title"), self.t("analysis_need_research"))
            return
        snapshot = DATA_VAULT_DIR / "topics" / _slugify(topic) / "_analysis_input.json"
        if not snapshot.exists():
            messagebox.showinfo(self.t("msg_topic_required_title"), self.t("analysis_need_research"))
            return
        current_output_language = self.language_var.get().strip() or DEFAULT_OUTPUT_LANGUAGE
        self.settings["output_language"] = current_output_language
        args = [
            "scripts/analysis.py",
            "--topic", topic,
            "--input", str(snapshot),
            "--vault-name", self.settings["vault_name"],
            "--output-dir", self.settings["vault_path"],
            "--data-dir", str(DATA_VAULT_DIR),
            "--model", self.settings["model"],
            "--format", self.settings.get("export_format", "obsidian"),
            "--output-language", current_output_language,
            "--reliability-weight", str(self.analysis_reliability_var.get() / 100),
            "--freshness-weight", str(self.analysis_freshness_var.get() / 100),
            "--early-signal-weight", str(self.analysis_signal_var.get() / 100),
            "--period-days", str(self.analysis_period_var.get()),
            "--alert-emerging" if self.settings.get("analysis_alert_emerging", True) else "--no-alert-emerging",
            "--alert-rising" if self.settings.get("analysis_alert_rising", True) else "--no-alert-rising",
            "--alert-contradictions" if self.settings.get("analysis_alert_contradictions", True) else "--no-alert-contradictions",
            "--alert-data-quality" if self.settings.get("analysis_alert_data_quality", True) else "--no-alert-data-quality",
        ]
        self._start_run(args, [self.analysis_run_btn])

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
