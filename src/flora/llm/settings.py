"""LLM provider settings and their on-disk store."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

ProviderId = Literal["ollama", "lmstudio", "llamacpp", "native", "gemini", "openai", "openrouter", "qwen", "custom"]

#: Default endpoints per provider. All speak the OpenAI-compatible API.
PRESETS: dict[str, dict[str, Any]] = {
    "ollama": {"label": "Ollama (local)", "base_url": "http://127.0.0.1:11434/v1", "needs_key": False},
    "lmstudio": {"label": "LM Studio (local)", "base_url": "http://127.0.0.1:1234/v1", "needs_key": False},
    "llamacpp": {"label": "llama.cpp server (local)", "base_url": "http://127.0.0.1:8080/v1", "needs_key": False},
    "native": {"label": "llama.cpp embutido (sem servidor)", "base_url": "", "needs_key": False},
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "needs_key": True,
        "env_key": "GEMINI_API_KEY",
    },
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "needs_key": True, "env_key": "OPENAI_API_KEY"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "needs_key": True, "env_key": "OPENROUTER_API_KEY"},
    # Alibaba Model Studio (international, pay-as-you-go). Keys are tied to their plan: Coding Plan and Token Plan keys
    # use other hosts and are rejected here, and this key type is rejected by the Beijing and US endpoints.
    "qwen": {
        "label": "Qwen (Alibaba Model Studio · Singapura)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "needs_key": True,
        "env_key": "DASHSCOPE_API_KEY",
    },
    "custom": {"label": "OpenAI-compatible (custom)", "base_url": "", "needs_key": False},
}


class LlmSettings(BaseModel):
    """User-selected LLM connection. ``api_key`` never leaves the server."""

    enabled: bool = False
    provider: ProviderId = "ollama"
    base_url: str = PRESETS["ollama"]["base_url"]
    api_key: str = Field("", repr=False)
    model: str = ""
    router_model: str = ""
    temperature: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(700, ge=16, le=8192)
    timeout_s: float = Field(120, ge=1, le=900)
    #: Qwen3 models "think" by default (hundreds of reasoning tokens for a one-word answer); off unless asked for.
    thinking: bool = False
    # Only used by the in-process ``native`` provider (GGUF files under <workdir>/models).
    n_ctx: int = Field(4096, ge=512, le=131072)
    n_gpu_layers: int = Field(-1, ge=-1, le=999, description="-1 offloads every layer to the GPU")

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL")
        return value

    def effective_api_key(self) -> str:
        """Stored key, else the provider's environment variable (keeps secrets out of files)."""
        if self.api_key:
            return self.api_key
        env_name = PRESETS.get(self.provider, {}).get("env_key")
        return os.environ.get(env_name, "") if env_name else ""

    def public(self) -> dict[str, Any]:
        """Representation safe to send to the browser (no secret)."""
        data = self.model_dump(exclude={"api_key"})
        data["has_api_key"] = bool(self.effective_api_key())
        data["key_from_env"] = not self.api_key and bool(self.effective_api_key())
        return data


class SettingsStore:
    """Persist settings as JSON under the workdir with owner-only permissions."""

    def __init__(self, workdir: Path) -> None:
        self.path = Path(workdir) / "llm_settings.json"
        self._lock = threading.Lock()

    def load(self) -> LlmSettings:
        with self._lock:
            if not self.path.exists():
                return LlmSettings()
            try:
                return LlmSettings.model_validate(json.loads(self.path.read_text("utf-8")))
            except (ValueError, OSError):
                return LlmSettings()

    def save(self, settings: LlmSettings) -> LlmSettings:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings.model_dump(), fh, indent=2)
            os.replace(tmp, self.path)
            return settings

    def update(self, patch: dict[str, Any]) -> LlmSettings:
        """Merge ``patch`` into the stored settings.

        An absent or ``None`` ``api_key`` keeps the stored key; an empty string clears it.
        """
        current = self.load()
        data = current.model_dump()
        for key, value in patch.items():
            if key in data and key != "api_key" and value is not None:
                data[key] = value
        if patch.get("api_key") is not None:
            data["api_key"] = patch["api_key"]
        if "provider" in patch and "base_url" not in patch:
            preset = PRESETS.get(str(patch["provider"]))
            if preset and preset["base_url"]:
                data["base_url"] = preset["base_url"]
        return self.save(LlmSettings.model_validate(data))
