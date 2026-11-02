"""LLM provider layer: settings store, OpenAI-compatible client and handlers."""

from __future__ import annotations

import json
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from flora.llm import LlmError, LlmSettings, OpenAICompatClient, SettingsStore
from flora.llm.client import strip_reasoning
from flora.ui.handlers import llm as handlers
from flora.ui.http import UiHttpError


class _FakeOpenAI(BaseHTTPRequestHandler):
    seen_auth: list[str | None] = []

    def log_message(self, *a):  # silence
        pass

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        type(self).seen_auth.append(self.headers.get("Authorization"))
        if self.path == "/v1/models":
            self._send(200, {"data": [{"id": "qwen3:4b"}, {"id": "phi4-mini:latest"}]})
        else:
            self._send(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n))
        if req["model"] == "boom":
            self._send(500, {"error": "model crashed"})
            return
        text = "<think>hidden</think>Answer for " + req["messages"][-1]["content"]
        self._send(200, {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 7}})


@pytest.fixture()
def server():
    _FakeOpenAI.seen_auth = []
    httpd = HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1"
    httpd.shutdown()


def test_strip_reasoning():
    assert strip_reasoning("<think>x\ny</think>\nHello") == "Hello"


def test_settings_validate_url_and_hide_key():
    s = LlmSettings(base_url="http://localhost:11434/v1/", api_key="secret")
    assert s.base_url == "http://localhost:11434/v1"
    assert "api_key" not in s.public() and s.public()["has_api_key"] is True
    with pytest.raises(ValueError):
        LlmSettings(base_url="file:///etc/passwd")


def test_store_is_private_and_keeps_key_on_partial_update(tmp_path):
    store = SettingsStore(tmp_path)
    store.update({"provider": "openai", "api_key": "sk-1", "model": "gpt"})
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.load().base_url == "https://api.openai.com/v1"
    store.update({"model": "other"})  # no api_key in patch → kept
    assert store.load().api_key == "sk-1"
    store.update({"api_key": ""})  # explicit empty → cleared
    assert store.load().api_key == ""


def test_client_lists_models_chats_and_pings(server):
    client = OpenAICompatClient(LlmSettings(base_url=server, api_key="k", model="qwen3:4b"))
    assert client.list_models() == ["phi4-mini:latest", "qwen3:4b"]
    out = client.chat([{"role": "user", "content": "hi"}])
    assert out["text"] == "Answer for hi" and out["usage"]["total_tokens"] == 7
    ping = client.ping()
    assert ping["reachable"] and ping["model_available"]
    assert "Bearer k" in _FakeOpenAI.seen_auth


def test_client_errors_are_explicit(server):
    with pytest.raises(LlmError, match="HTTP 500"):
        OpenAICompatClient(LlmSettings(base_url=server, model="boom")).chat([{"role": "user", "content": "x"}])
    with pytest.raises(LlmError, match="Cannot reach"):
        OpenAICompatClient(LlmSettings(base_url="http://127.0.0.1:9/v1", timeout_s=1)).list_models()
    with pytest.raises(LlmError, match="No model"):
        OpenAICompatClient(LlmSettings(base_url=server)).chat([{"role": "user", "content": "x"}])


def test_handlers_flow_never_expose_key(tmp_path, server):
    state = SimpleNamespace(workdir=tmp_path)
    saved = handlers.save_config(state, {"enabled": True, "provider": "custom", "base_url": server, "api_key": "s3cret", "model": "qwen3:4b"})
    assert "s3cret" not in json.dumps(saved) and "\"api_key\"" not in json.dumps(saved) and saved["settings"]["has_api_key"]
    assert handlers.get_config(state)["settings"]["model"] == "qwen3:4b"
    assert handlers.list_models(state)["models"]
    assert handlers.test_connection(state, {})["model_available"] is True
    reply = handlers.chat(state, {"messages": [{"role": "user", "content": "ping"}]})
    assert reply["text"] == "Answer for ping"


def test_chat_guards(tmp_path, server):
    state = SimpleNamespace(workdir=tmp_path)
    with pytest.raises(UiHttpError) as e:
        handlers.chat(state, {"messages": [{"role": "user", "content": "x"}]})
    assert e.value.code == "llm_disabled"
    handlers.save_config(state, {"enabled": True, "provider": "custom", "base_url": server, "model": "m"})
    for bad in ([], [{"role": "tool", "content": "x"}], [{"role": "user", "content": 3}]):
        with pytest.raises(UiHttpError):
            handlers.chat(state, {"messages": bad})
    with pytest.raises(UiHttpError) as e:
        handlers.chat(state, {"messages": [{"role": "user", "content": "x" * 30000}]})
    assert e.value.status == 413
    assert handlers.test_connection(state, {"base_url": "http://127.0.0.1:9/v1", "timeout_s": 1})["success"] is False


def test_gemini_preset_uses_env_key_and_strips_model_prefix(monkeypatch, server):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    s = LlmSettings(provider="gemini", base_url=server)
    assert s.effective_api_key() == "env-key"
    pub = s.public()
    assert pub["has_api_key"] and pub["key_from_env"] and "env-key" not in json.dumps(pub)
    from flora.llm.settings import PRESETS

    assert PRESETS["gemini"]["base_url"].startswith("https://generativelanguage.googleapis.com")
    OpenAICompatClient(s).list_models()
    assert "Bearer env-key" in _FakeOpenAI.seen_auth
    assert LlmSettings(provider="gemini", api_key="own").effective_api_key() == "own"


class _FakeLlama:
    loads: list[dict] = []

    def __init__(self, **kw):
        type(self).loads.append(kw)

    def create_chat_completion(self, messages, temperature, max_tokens):
        return {"choices": [{"message": {"content": "<think>x</think>local:" + messages[-1]["content"]}}], "usage": {"total_tokens": 3}}


@pytest.fixture()
def native(tmp_path, monkeypatch):
    import sys
    import types

    from flora.llm import native as mod

    _FakeLlama.loads = []
    mod.unload()
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=_FakeLlama))
    monkeypatch.delenv("FLORA_MODELS_DIR", raising=False)
    models = tmp_path / "models"
    models.mkdir()
    (models / "qwen3-4b-q4.gguf").write_bytes(b"GGUF")
    (models / "notes.txt").write_text("x")
    yield SimpleNamespace(workdir=tmp_path)
    mod.unload()


def test_native_provider_lists_gguf_and_chats_in_process(native):
    handlers.save_config(native, {"enabled": True, "provider": "native", "model": "qwen3-4b-q4.gguf", "n_ctx": 2048, "n_gpu_layers": 20})
    assert handlers.list_models(native)["models"] == ["qwen3-4b-q4.gguf"]
    ping = handlers.test_connection(native, {})
    assert ping["model_available"] and ping["models_dir"].endswith("models")
    assert handlers.chat(native, {"messages": [{"role": "user", "content": "hi"}]})["text"] == "local:hi"
    handlers.chat(native, {"messages": [{"role": "user", "content": "again"}]})
    assert len(_FakeLlama.loads) == 1  # model cached between calls
    assert _FakeLlama.loads[0]["n_ctx"] == 2048 and _FakeLlama.loads[0]["n_gpu_layers"] == 20


def test_native_rejects_paths_and_missing_backend(native, monkeypatch):
    handlers.save_config(native, {"enabled": True, "provider": "native", "model": "../etc/passwd"})
    with pytest.raises(UiHttpError, match="gguf"):
        handlers.chat(native, {"messages": [{"role": "user", "content": "x"}]})
    handlers.save_config(native, {"model": "missing.gguf"})
    with pytest.raises(UiHttpError, match="not found"):
        handlers.chat(native, {"messages": [{"role": "user", "content": "x"}]})
    import sys

    monkeypatch.setitem(sys.modules, "llama_cpp", None)  # simulate "not installed"
    out = handlers.test_connection(native, {})
    assert out["success"] is False and "flora[local]" in out["error"]
