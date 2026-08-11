#!/usr/bin/env python3
"""
app.py

AI Research Digest 데스크톱 GUI 앱.

기존 run_digest.bat / run_topic_digest.bat 이 하던 일(스크립트 실행 + Obsidian 자동 실행)을
창(윈도우) 하나로 통합한 프런트엔드. 실제 크롤링/GPT 분석/저장 로직은 건드리지 않고,
기존 scripts/research_digest.py, scripts/topic_digest.py 를 그대로 서브프로세스로 호출한다.

실행:
    uv run python scripts/app.py
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, font as tkfont

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_lab.utils.favorites import TopicFavorites  # noqa: E402
from research_lab.digest.topic_formatter import _slugify  # noqa: E402
from research_lab.i18n import resolve_ui_lang, OUTPUT_LANGUAGE_PRESETS, DEFAULT_OUTPUT_LANGUAGE  # noqa: E402

SETTINGS_PATH = PROJECT_ROOT / "gui_settings.json"
ENV_PATH = PROJECT_ROOT / ".env"
FAVORITES_PATH = PROJECT_ROOT / "topics_favorites.json"

MODEL_PRESETS = ["gpt-5.4-nano", "gpt-5.4-mini", "gpt-4.1-nano"]
EXPORT_FORMAT_CHOICES = ["obsidian", "markdown", "text", "json", "html", "docx"]

DEFAULT_SETTINGS = {
    "vault_name": "vault",
    "vault_path": str(PROJECT_ROOT / "vault"),
    "model": "gpt-5.4-nano",
    "api_base": "",
    "export_format": "obsidian",
    "credibility_check": False,
    "credibility_threshold": 40,
    "output_language": DEFAULT_OUTPUT_LANGUAGE,
    "gossip_ratio": 20,
    "analysis_reliability_weight": 50,
    "analysis_freshness_weight": 30,
    "analysis_early_signal_weight": 20,
}


# ── 다국어 문자열 ─────────────────────────────────────────────────────────
# 언어 변경은 다음 재시작부터 적용된다 (설정 탭에서 바꾸고 저장하면 안내 메시지가 뜬다).

STRINGS = {
    "ko": {
        "window_title": "AI Research Lab",
        "tab_digest": "AI 다이제스트",
        "tab_topic": "주제 리서치",
        "tab_settings": "설정",
        "tab_analysis": "분석",
        "analysis_intro": "Topic Research에서 수집한 최신 자료를 재사용하여 신뢰도·최신성·독립성을 반영한 동향 분석을 수행합니다.",
        "analysis_topic_label": "분석할 주제",
        "analysis_run_btn": "동향 분석 실행",
        "analysis_need_research": "먼저 Topic Research를 한 번 실행해 주세요.",
        "analysis_weights": "분석 가중치",
        "analysis_reliability": "신뢰도",
        "analysis_freshness": "최신성",
        "analysis_signal": "초기 신호",
        "analysis_history": "동향 변화 추적",
        "analysis_history_hint": "반복 분석 결과를 시간순으로 비교합니다. Rumor → Emerging Signal → Confirmed Trend 승격을 추적할 수 있습니다.",
        "analysis_no_history": "아직 분석 이력이 없습니다. Analysis를 실행하면 여기에 변화가 표시됩니다.",
        "status_idle": "대기 중",
        "status_running": "실행 중...",
        "status_done": "완료",
        "status_error": "오류로 종료됨",
        "digest_intro": "AI Times + HuggingFace 최신 동향을 수집해서 GPT로 분석하고,\nObsidian 노트로 저장합니다.",
        "digest_articles_label": "AI Times 기사 수",
        "digest_models_label": "HuggingFace 모델 수",
        "digest_dryrun_label": "미리보기만 (크롤링만 하고 GPT 호출은 생략)",
        "digest_run_btn": "지금 생성하기",
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
        "tab_digest": "AI Digest",
        "tab_topic": "Topic Research",
        "tab_settings": "Settings",
        "tab_analysis": "Analysis",
        "analysis_intro": "Reuses the latest Topic Research sources and analyzes trends using reliability, freshness, evidence, and source independence.",
        "analysis_topic_label": "Topic to analyze",
        "analysis_run_btn": "Run Trend Analysis",
        "analysis_need_research": "Run Topic Research once before Analysis.",
        "analysis_weights": "Analysis weights",
        "analysis_reliability": "Reliability",
        "analysis_freshness": "Freshness",
        "analysis_signal": "Early signal",
        "analysis_history": "Trend evolution",
        "analysis_history_hint": "Compare repeated analyses over time and track Rumor → Emerging Signal → Confirmed Trend transitions.",
        "analysis_no_history": "No analysis history yet. Run Analysis to populate this timeline.",
        "status_idle": "Idle",
        "status_running": "Running...",
        "status_done": "Done",
        "status_error": "Finished with an error",
        "status_cancelled": "Cancelled",
        "cancel_btn": "Cancel",
        "digest_intro": "Collects the latest AI Times + HuggingFace updates, analyzes them with GPT,\nand saves the result as an Obsidian note.",
        "digest_articles_label": "AI Times article count",
        "digest_models_label": "HuggingFace model count",
        "digest_dryrun_label": "Preview only (crawl only, skip the GPT call)",
        "digest_run_btn": "Generate now",
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


# ── 설정 파일 / .env 읽고 쓰기 ─────────────────────────────────────────────

def _parse_bat_arg(bat_path: Path, flag: str) -> str | None:
    """bat 파일 안의 `--flag "값"` 형태에서 값을 추출한다."""
    if not bat_path.exists():
        return None
    text = bat_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(re.escape(flag) + r'\s+"([^"]*)"', text)
    return m.group(1) if m and m.group(1) else None


def recover_settings_from_bat() -> dict | None:
    """gui_settings.json이 없을 때(구버전 설치, 또는 app.py만 교체 적용한 경우),
    설치 시 이미 만들어져 있는 run_digest.bat / run_topic_digest.bat 안의 실제 값으로
    복구를 시도한다. 이게 없으면 앱이 항상 설치 폴더 밑 기본 vault 경로로 저장해버려서,
    사용자가 설치 때 지정한 실제 Vault 경로가 무시되는 문제가 있었다."""
    for bat_name in ("run_digest.bat", "run_topic_digest.bat"):
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
        save_settings(merged)  # 복구했으면 다음부터는 바로 여기서 읽도록 저장해둔다

    # gui_settings.json/bat 어디에도 api_base가 없으면 .env에 저장된 값을 대신 쓴다
    # (설치 시 입력한 값을 앱에서 다시 물어보지 않기 위함)
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
                if values[matched_key]:  # 빈 값이면 아예 줄 자체를 지움
                    lines.append(f"{matched_key}={values[matched_key]}")
                seen.add(matched_key)
            else:
                lines.append(line)

    for key, value in values.items():
        if key not in seen and value:
            lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 백그라운드 파이프라인 실행 ────────────────────────────────────────────

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
        python_exe = sys.executable
        if not python_exe or not Path(python_exe).exists():
            self.log_queue.put(("line", "Python interpreter not found.\n"))
            self.log_queue.put(("done", -1))
            return
        cmd = [python_exe, *args]
        self.log_queue.put(("line", f"$ {' '.join(cmd)}\n"))
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
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
        # Windows 작업 표시줄에서 pythonw.exe가 아니라 AI Research Lab 앱으로
        # 그룹화되도록 AppUserModelID를 명시합니다.
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

        # Windows 작업 표시줄/창 아이콘을 설치된 AI Research Lab 아이콘으로 지정합니다.
        # Tkinter 기본 아이콘(파이썬 로고)이 표시되지 않도록 설치 폴더의 digest.ico를 사용합니다.
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

    def t(self, key: str, **kwargs) -> str:
        return tr(self.lang, key, **kwargs)

    # ── 위젯 구성 ─────────────────────────────────────────────────────
    def _build_widgets(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=False, padx=10, pady=(10, 0))

        self.tab_digest = ttk.Frame(notebook)
        self.tab_topic = ttk.Frame(notebook)
        self.tab_analysis = ttk.Frame(notebook)
        self.tab_settings = ttk.Frame(notebook)
        notebook.add(self.tab_digest, text=self.t("tab_digest"))
        notebook.add(self.tab_topic, text=self.t("tab_topic"))
        notebook.add(self.tab_analysis, text=self.t("tab_analysis"))
        notebook.add(self.tab_settings, text=self.t("tab_settings"))

        self._build_digest_tab()
        self._build_topic_tab()
        self._build_analysis_tab()
        self._build_settings_tab()

        # ── 공용: 상태 표시줄 + 로그 창 ──
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=10, pady=(10, 0))
        self.status_var = tk.StringVar(value=self.t("status_idle"))
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")

        self.cancel_btn = ttk.Button(
            status_frame, text=self.t("cancel_btn"), command=self._cancel_run, state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text = tk.Text(log_frame, height=14, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_digest_tab(self) -> None:
        f = self.tab_digest
        for i in range(2):
            f.columnconfigure(i, weight=1)

        ttk.Label(f, text=self.t("digest_intro"), justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        ttk.Label(f, text=self.t("digest_articles_label")).grid(row=1, column=0, sticky="w", padx=12)
        self.articles_var = tk.IntVar(value=5)
        ttk.Spinbox(f, from_=1, to=30, textvariable=self.articles_var, width=8).grid(
            row=1, column=1, sticky="w", padx=12
        )

        ttk.Label(f, text=self.t("digest_models_label")).grid(row=2, column=0, sticky="w", padx=12, pady=(4, 0))
        self.models_var = tk.IntVar(value=5)
        ttk.Spinbox(f, from_=1, to=30, textvariable=self.models_var, width=8).grid(
            row=2, column=1, sticky="w", padx=12, pady=(4, 0)
        )

        self.digest_dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text=self.t("digest_dryrun_label"), variable=self.digest_dry_run_var
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))

        self.digest_run_btn = ttk.Button(f, text=self.t("digest_run_btn"), command=self._on_run_digest)
        self.digest_run_btn.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=16)

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
        f.rowconfigure(7, weight=1)
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
        self.analysis_run_btn = ttk.Button(f, text=self.t("analysis_run_btn"), command=self._on_run_analysis)
        self.analysis_run_btn.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=16)
        ttk.Label(
            f,
            text="Confirmed Trend / Emerging Signal / Rumor로 분리하며, 결과는 Settings의 Export format으로 저장됩니다."
            if self.lang == "ko"
            else "Results are separated into Confirmed Trend / Emerging Signal / Rumor and saved using the Settings export format.",
            wraplength=680,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        # ── 시간축 시각화 ─────────────────────────────────────────────
        ttk.Label(f, text=self.t("analysis_history"), font=("TkDefaultFont", 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 2)
        )
        ttk.Label(f, text=self.t("analysis_history_hint"), wraplength=680).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6)
        )
        chart_frame = ttk.Frame(f)
        chart_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))
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
    def _build_settings_tab(self) -> None:
        f = self.tab_settings
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
            row=18, column=1, sticky="w", padx=12, pady=(10, 0)
        )
        ttk.Button(f, text=self.t("settings_save_btn"), command=self._on_save_settings).grid(
            row=19, column=1, sticky="w", padx=12, pady=(4, 12)
        )

    # ── 값 로드 ───────────────────────────────────────────────────────
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
        self.language_var.set(self.settings.get("output_language", DEFAULT_OUTPUT_LANGUAGE))
        self._on_toggle_credibility()
        self._on_threshold_change()
        self._on_gossip_ratio_change()
        self.analysis_reliability_var.set(int(self.settings.get("analysis_reliability_weight", 50)))
        self.analysis_freshness_var.set(int(self.settings.get("analysis_freshness_weight", 30)))
        self.analysis_signal_var.set(int(self.settings.get("analysis_early_signal_weight", 20)))
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

    def _analysis_history_path(self, topic: str) -> Path:
        return Path(self.settings["vault_path"]) / "topics" / _slugify(topic) / "_analysis_history.json"

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

    # ── 설정 탭 이벤트 ────────────────────────────────────────────────
    def _on_browse_vault(self) -> None:
        chosen = filedialog.askdirectory(
            title=self.t("settings_vault_path"), initialdir=self.vault_path_var.get() or str(PROJECT_ROOT)
        )
        if chosen:
            self.vault_path_var.set(chosen)

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

        self.settings = {
            "vault_name": self.vault_name_var.get().strip(),
            "vault_path": self.vault_path_var.get().strip(),
            "model": (self.model_var.get().strip() or MODEL_PRESETS[0]),
            "api_base": self.api_base_var.get().strip(),
            "export_format": self.export_format_var.get().strip() or "obsidian",
            "credibility_check": bool(self.credibility_check_var.get()),
            "credibility_threshold": int(self.credibility_threshold_var.get()),
            "gossip_ratio": int(self.gossip_ratio_var.get()),
            "output_language": self.language_var.get().strip() or DEFAULT_OUTPUT_LANGUAGE,
            "analysis_reliability_weight": int(self.analysis_reliability_var.get()),
            "analysis_freshness_weight": int(self.analysis_freshness_var.get()),
            "analysis_early_signal_weight": int(self.analysis_signal_var.get()),
        }
        save_settings(self.settings)

        # Apply the selected output language immediately to subsequent runs.
        self.output_language = self.settings["output_language"]
        self.lang = resolve_ui_lang(self.output_language)

        save_env_values({
            "OPENAI_API_KEY": api_key,
            "OPENAI_API_BASE": self.api_base_var.get().strip(),
        })
        self.settings_status_var.set(self.t("settings_saved_msg"))
        self.after(3500, lambda: self.settings_status_var.set(""))

    # ── 즐겨찾기 탭 이벤트 ────────────────────────────────────────────
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

    # ── 실행 공통 로직 ────────────────────────────────────────────────
    def _guard_before_run(self) -> bool:
        if self.runner.is_running:
            messagebox.showinfo(self.t("msg_running_title"), self.t("msg_running_body"))
            return False
        if not load_env_value("OPENAI_API_KEY"):
            messagebox.showerror(self.t("msg_api_key_missing_title"), self.t("msg_api_key_missing_body"))
            return False
        return True

    def _start_run(self, args: list[str], buttons: list[ttk.Button]) -> None:
        self._clear_log()
        for b in buttons:
            b.state(["disabled"])
        self.cancel_btn.state(["!disabled"])
        self.status_var.set(self.t("status_running"))
        self.progress.start(12)
        self._active_buttons = buttons
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
                    else:
                        self.status_var.set(self.t("status_error"))
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    # ── AI 다이제스트 탭 실행 ─────────────────────────────────────────
    def _on_run_digest(self) -> None:
        if not self._guard_before_run():
            return
        # Use the live Settings value so a language change takes effect immediately,
        # even before the user restarts the GUI.
        current_output_language = self.language_var.get().strip() or DEFAULT_OUTPUT_LANGUAGE
        self.settings["output_language"] = current_output_language
        args = [
            "scripts/research_digest.py",
            "--articles", str(self.articles_var.get()),
            "--models", str(self.models_var.get()),
            "--vault-name", self.settings["vault_name"],
            "--output-dir", self.settings["vault_path"],
            "--model", self.settings["model"],
            "--format", self.settings.get("export_format", "obsidian"),
            "--output-language", current_output_language,
            "--gossip-ratio", str(self.gossip_ratio_var.get()),
        ]
        if self.settings.get("credibility_check"):
            args += [
                "--credibility-check",
                "--credibility-threshold", str(self.settings.get("credibility_threshold", 40)),
            ]
        if self.digest_dry_run_var.get():
            args.append("--dry-run")
        self._start_run(args, [self.digest_run_btn])

    # ── 주제 리서치 탭 실행 ───────────────────────────────────────────
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
            "--model", self.settings["model"],
            "--format", self.settings.get("export_format", "obsidian"),
            "--output-language", current_output_language,
            "--gossip-ratio", str(self.gossip_ratio_var.get()),
        ]
        if self.settings.get("credibility_check"):
            args += [
                "--credibility-check",
                "--credibility-threshold", str(self.settings.get("credibility_threshold", 40)),
            ]
        self._start_run(args, [self.topic_run_btn])


    # ── Analysis 탭 실행 ───────────────────────────────────────────────
    def _on_run_analysis(self) -> None:
        if not self._guard_before_run():
            return
        topic = self.analysis_topic_var.get().strip()
        if not topic:
            messagebox.showinfo(self.t("msg_topic_required_title"), self.t("analysis_need_research"))
            return
        snapshot = Path(self.settings["vault_path"]) / "topics" / _slugify(topic) / "_analysis_input.json"
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
            "--model", self.settings["model"],
            "--format", self.settings.get("export_format", "obsidian"),
            "--output-language", current_output_language,
            "--reliability-weight", str(self.analysis_reliability_var.get() / 100),
            "--freshness-weight", str(self.analysis_freshness_var.get() / 100),
            "--early-signal-weight", str(self.analysis_signal_var.get() / 100),
        ]
        self._start_run(args, [self.analysis_run_btn])

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
