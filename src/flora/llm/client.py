"""Minimal OpenAI-compatible client built on the standard library."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from flora.llm.settings import LlmSettings

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LlmError(RuntimeError):
    """Raised when the model endpoint is unreachable or answers with an error."""


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks emitted by reasoning models such as Qwen3."""
    return _THINK.sub("", text).strip()


class OpenAICompatClient:
    """Talk to any server exposing ``/models`` and ``/chat/completions``."""

    def __init__(self, settings: LlmSettings) -> None:
        if not settings.base_url:
            raise LlmError("No base URL configured.")
        self.settings = settings

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        api_key = self.settings.effective_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.settings.timeout_s) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise LlmError(f"HTTP {exc.code} from {path}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            raise LlmError(f"Cannot reach {self.settings.base_url}: {reason}") from exc
        except ValueError as exc:
            raise LlmError(f"Invalid JSON from {path}") from exc

    # -- API ---------------------------------------------------------------

    def list_models(self) -> list[str]:
        body = self._request("GET", "/models")
        items = body.get("data") or body.get("models") or []
        names = [str(m.get("id") or m.get("name")).removeprefix("models/") for m in items if isinstance(m, dict)]
        return sorted(n for n in names if n and n != "None")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        chosen = model or self.settings.model
        if not chosen:
            raise LlmError("No model selected.")
        started = time.perf_counter()
        body = self._request(
            "POST",
            "/chat/completions",
            {
                "model": chosen,
                "messages": messages,
                "temperature": self.settings.temperature if temperature is None else temperature,
                "max_tokens": max_tokens or self.settings.max_tokens,
                "stream": False,
            },
        )
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("Unexpected response shape from /chat/completions") from exc
        return {
            "model": chosen,
            "text": strip_reasoning(text),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "usage": body.get("usage") or {},
        }

    def ping(self) -> dict[str, Any]:
        """Check reachability and whether the selected model is available."""
        started = time.perf_counter()
        models = self.list_models()
        selected = self.settings.model
        return {
            "reachable": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "models": models,
            "model_available": bool(selected) and _has_model(models, selected),
        }


def _has_model(models: list[str], wanted: str) -> bool:
    # Ollama lists "qwen3:4b"; users often type "qwen3:4b" or just "qwen3".
    return wanted in models or any(m.split(":")[0] == wanted for m in models)
