from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("LOCAL2API_HOST", "127.0.0.1")
    port: int = _env_int("LOCAL2API_PORT", 8000)
    local_url: str = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")
    cloud_url: str = os.getenv("CLOUD_API_URL", "http://127.0.0.1:3000/v1/chat/completions")
    local_model: str = os.getenv("LOCAL_LLM_MODEL", "local-model")
    cloud_model: str = os.getenv("CLOUD_API_MODEL", "cloud-model")
    local_timeout: float = _env_float("LOCAL_TIMEOUT_SECONDS", 60.0)
    cloud_timeout: float = _env_float("CLOUD_TIMEOUT_SECONDS", 120.0)
    complexity_words: int = _env_int("ROUTER_COMPLEXITY_WORDS", 450)
