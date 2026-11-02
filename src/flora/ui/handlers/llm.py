"""LLM settings and proxy handlers. The API key stays on the server."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from flora.llm import PRESETS, LlmError, LlmSettings, OpenAICompatClient, SettingsStore
from flora.llm import download
from flora.llm.native import NativeClient, models_dir
from flora.ui.http import UiHttpError, json_success

_ALLOWED_ROLES = {"system", "user", "assistant"}
_MAX_MESSAGES = 24
_MAX_CHARS = 24_000


def _store(state) -> SettingsStore:
    return SettingsStore(state.workdir)


def _client(state, settings: LlmSettings):
    try:
        if settings.provider == "native":
            return NativeClient(settings, state.workdir)
        return OpenAICompatClient(settings)
    except LlmError as exc:
        raise UiHttpError(str(exc), status=400, code="llm_not_configured") from exc


def get_config(state, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    return json_success(data={"settings": _store(state).load().public(), "presets": PRESETS})


def save_config(state, body: dict[str, Any]) -> dict[str, Any]:
    try:
        settings = _store(state).update(body or {})
    except ValidationError as exc:
        raise UiHttpError("Invalid LLM settings.", code="invalid_settings", details={"errors": exc.errors(include_url=False, include_context=False)}) from exc
    return json_success(data={"settings": settings.public()})


def list_models(state, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    try:
        return json_success(data={"models": _client(state, _store(state).load()).list_models()})
    except LlmError as exc:
        raise UiHttpError(str(exc), status=502, code="llm_unreachable") from exc


def test_connection(state, body: dict[str, Any]) -> dict[str, Any]:
    """Test the saved settings, optionally overridden by unsaved form values."""
    base = _store(state).load()
    overrides = {k: v for k, v in (body or {}).items() if k in LlmSettings.model_fields and v not in (None, "")}
    try:
        settings = LlmSettings.model_validate({**base.model_dump(), **overrides})
    except ValidationError as exc:
        raise UiHttpError("Invalid LLM settings.", code="invalid_settings") from exc
    try:
        return json_success(data=_client(state, settings).ping())
    except LlmError as exc:
        return {"success": False, "error": str(exc), "code": "llm_unreachable", "reachable": False}


def chat(state, body: dict[str, Any]) -> dict[str, Any]:
    settings = _store(state).load()
    if not settings.enabled:
        raise UiHttpError("LLM is disabled in settings.", status=409, code="llm_disabled")
    messages = (body or {}).get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > _MAX_MESSAGES:
        raise UiHttpError("`messages` must be a non-empty list.", code="invalid_messages")
    clean: list[dict[str, str]] = []
    total = 0
    for item in messages:
        role, content = (item or {}).get("role"), (item or {}).get("content")
        if role not in _ALLOWED_ROLES or not isinstance(content, str):
            raise UiHttpError("Each message needs a valid role and string content.", code="invalid_messages")
        total += len(content)
        clean.append({"role": role, "content": content})
    if total > _MAX_CHARS:
        raise UiHttpError("Conversation too long.", status=413, code="payload_too_large")
    model = body.get("model") if isinstance(body.get("model"), str) and body.get("model") else None
    try:
        result = _client(state, settings).chat(clean, model=model, temperature=body.get("temperature"), max_tokens=body.get("max_tokens"))
    except LlmError as exc:
        raise UiHttpError(str(exc), status=502, code="llm_error") from exc
    return json_success(data=result)


def pull_start(state, body: dict[str, Any]) -> dict[str, Any]:
    """Start downloading a GGUF file from Hugging Face into the models directory."""
    body = body or {}
    try:
        job = download.start(models_dir(state.workdir), body.get("repo", ""), body.get("file", ""), body.get("revision") or "main")
    except LlmError as exc:
        raise UiHttpError(str(exc), code="invalid_download") from exc
    return json_success(data={"job": job.public()})


def pull_status(state, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    job_id = ((params or {}).get("id") or [""])[0]
    try:
        return json_success(data={"job": download.get(job_id).public()})
    except LlmError as exc:
        raise UiHttpError(str(exc), status=404, code="not_found") from exc


def pull_cancel(state, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return json_success(data={"job": download.cancel((body or {}).get("id", "")).public()})
    except LlmError as exc:
        raise UiHttpError(str(exc), status=404, code="not_found") from exc
