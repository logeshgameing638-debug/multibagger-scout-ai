"""Environment-driven configuration. No secrets in code; everything read from env.

Uses a small .env parser so no extra dependency is required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    project_root: Path = field(default=PROJECT_ROOT)
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'multibagger.db'}"
        )
    )
    http_timeout_seconds: int = field(default_factory=lambda: _int("HTTP_TIMEOUT_SECONDS", 20))
    price_cache_ttl_minutes: int = field(default_factory=lambda: _int("PRICE_CACHE_TTL_MINUTES", 15))
    news_cache_ttl_minutes: int = field(default_factory=lambda: _int("NEWS_CACHE_TTL_MINUTES", 30))
    ollama_enabled: bool = field(default_factory=lambda: _bool("OLLAMA_ENABLED", False))
    ollama_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.1"))
    free_ai_provider: str = field(default_factory=lambda: os.environ.get("FREE_AI_PROVIDER", "none"))
    free_ai_api_key: str = field(default_factory=lambda: os.environ.get("FREE_AI_API_KEY", ""))
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", False))
    backend_host: str = field(default_factory=lambda: os.environ.get("BACKEND_HOST", "127.0.0.1"))
    backend_port: int = field(default_factory=lambda: _int("BACKEND_PORT", 8000))

    @property
    def exports_dir(self) -> Path:
        path = self.project_root / "exports"
        path.mkdir(exist_ok=True)
        return path

    @property
    def logs_dir(self) -> Path:
        path = self.project_root / "logs"
        path.mkdir(exist_ok=True)
        return path


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS
