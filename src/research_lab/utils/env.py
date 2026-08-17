"""
env.py

환경 변수 로드 및 검증 모듈.
모든 환경 변수 접근은 이 모듈을 통해서만 한다. (ADR-004)

Fail-fast 원칙: 필수 변수 누락 시 앱 시작 시점에 즉시 오류 발생.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


def _env_file() -> Path:
    """Return the per-user environment file for installed builds."""
    configured_data_home = os.environ.get("AI_RESEARCH_LAB_DATA_HOME")
    if configured_data_home:
        return Path(configured_data_home) / ".env"

    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        data_root = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        return data_root / "AI Research Lab" / ".env"

    return Path(__file__).parent.parent.parent.parent / ".env"


def _load_env() -> None:
    """Load the applicable environment file."""
    if not _DOTENV_AVAILABLE:
        return
    env_file = _env_file()
    if env_file.exists():
        load_dotenv(env_file)


def load_env_value(key: str) -> str:
    """Return a single value from the project .env file.

    This helper is intentionally small so CLI entry points can read installer-
    provided values without constructing the full AppConfig singleton.
    Environment variables take precedence over the .env file.
    """
    key = str(key).strip()
    if not key:
        return ""

    # Prefer an explicitly exported process environment variable.
    value = os.environ.get(key)
    if value is not None and value.strip():
        return value.strip()

    env_file = _env_file()
    if not env_file.exists():
        return ""

    try:
        text = env_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, raw_value = stripped.split("=", 1)
        if name.strip() == key:
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
                value = value[1:-1]
            return value
    return ""


@dataclass(frozen=True)
class AppConfig:
    """앱 전체 설정. 환경 변수로부터 빌드된다."""

    # Model settings
    ai_model: str
    ai_model_fallback: str
    ai_max_tokens: int

    # API
    openai_api_key: str
    openai_api_base: str | None

    # Paths
    vault_path: Path
    memory_path: Path

    # Operations
    debug: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        """환경 변수에서 설정을 로드한다. 필수 변수 누락 시 ValueError 발생."""
        _load_env()

        # Validate required variables.
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.\n"
                "→ .env 파일에 OPENAI_API_KEY=your_key_here 를 추가하세요."
            )

        return cls(
            ai_model=os.environ.get("AI_MODEL", "gpt-5-nano"),
            ai_model_fallback=os.environ.get("AI_MODEL_FALLBACK", "gpt-5-codex"),
            ai_max_tokens=int(os.environ.get("AI_MAX_TOKENS", "10000")),
            openai_api_key=api_key,
        # Configure only when a custom endpoint is needed (proxy, Azure-compatible,
        # or local LLM server).  Otherwise use the official OpenAI endpoint.
            openai_api_base=os.environ.get("OPENAI_API_BASE", "").strip() or None,
            vault_path=Path(os.environ.get("VAULT_PATH", "./vault")),
            memory_path=Path(os.environ.get("MEMORY_PATH", "./memory")),
            debug=os.environ.get("DEBUG", "false").lower() == "true",
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )


# Singleton pattern — load only when needed.
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """AppConfig 싱글턴을 반환한다."""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def reset_config() -> None:
    """테스트 시 싱글턴을 초기화한다."""
    global _config
    _config = None
