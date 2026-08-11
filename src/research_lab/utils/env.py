"""
env.py

환경 변수 로드 및 검증 모듈.
모든 환경 변수 접근은 이 모듈을 통해서만 한다. (ADR-004)

Fail-fast 원칙: 필수 변수 누락 시 앱 시작 시점에 즉시 오류 발생.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


def _load_env() -> None:
    """프로젝트 루트의 .env 파일을 로드한다."""
    if not _DOTENV_AVAILABLE:
        return
    env_file = Path(__file__).parent.parent.parent.parent / ".env"
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

    env_file = Path(__file__).parent.parent.parent.parent / ".env"
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

    # 모델 설정
    ai_model: str
    ai_model_fallback: str
    ai_max_tokens: int

    # API
    openai_api_key: str
    openai_api_base: str | None

    # 경로
    vault_path: Path
    memory_path: Path

    # 운영
    debug: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        """환경 변수에서 설정을 로드한다. 필수 변수 누락 시 ValueError 발생."""
        _load_env()

        # 필수 변수 검증
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
            # 커스텀 엔드포인트가 필요할 때만 설정 (사내 프록시, Azure OpenAI 호환,
            # 로컬 LLM 서버 등). 비어있으면 OpenAI 공식 엔드포인트를 사용한다.
            openai_api_base=os.environ.get("OPENAI_API_BASE", "").strip() or None,
            vault_path=Path(os.environ.get("VAULT_PATH", "./vault")),
            memory_path=Path(os.environ.get("MEMORY_PATH", "./memory")),
            debug=os.environ.get("DEBUG", "false").lower() == "true",
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )


# 싱글턴 패턴 — 필요할 때만 로드
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
