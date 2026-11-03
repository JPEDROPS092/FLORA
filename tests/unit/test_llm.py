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
    seen_requests: list[dict] = []

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
        type(self).seen_requests.append(req)
        if req["model"] == "boom":
            self._send(500, {"error": "model crashed"})
            return
        text = "<think>hidden</think>Answer for " + req["messages"][-1]["content"]
        self._send(200, {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 7}})


@pytest.fixture()
def server():
    _FakeOpenAI.seen_auth = []
    _FakeOpenAI.seen_requests = []
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


class _FakeHub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/good.gguf"):
            body = b"GGUF" + b"\0" * 600_000
        elif self.path.endswith("/fake.gguf"):
            body = b"NOPE" + b"\0" * 100
        elif self.path.endswith("/slow.gguf"):
            body = b"GGUF" + b"\0" * 8_000_000
        else:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            for i in range(0, len(body), 65536):
                self.wfile.write(body[i : i + 65536])
                if self.path.endswith("/slow.gguf"):
                    import time

                    time.sleep(0.01)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    from flora.llm import download

    httpd = HTTPServer(("127.0.0.1", 0), _FakeHub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("FLORA_HF_ENDPOINT", f"http://127.0.0.1:{httpd.server_port}")
    monkeypatch.delenv("FLORA_MODELS_DIR", raising=False)
    download._jobs.clear()
    yield SimpleNamespace(workdir=tmp_path)
    httpd.shutdown()


def _wait(state, job_id, done=("done", "error", "cancelled")):
    import time

    for _ in range(200):
        job = handlers.pull_status(state, {"id": [job_id]})["job"]
        if job["status"] in done:
            return job
        time.sleep(0.05)
    raise AssertionError("download did not finish")


def test_pull_downloads_validates_and_lists(hub):
    job = handlers.pull_start(hub, {"repo": "Qwen/Qwen3-4B-GGUF", "file": "good.gguf"})["job"]
    final = _wait(hub, job["id"])
    assert final["status"] == "done" and final["bytes_done"] == final["bytes_total"] > 0
    assert (hub.workdir / "models" / "good.gguf").is_file()
    assert not list((hub.workdir / "models").glob("*.part"))
    handlers.save_config(hub, {"provider": "native", "model": "good.gguf"})
    assert handlers.list_models(hub)["models"] == ["good.gguf"]


def test_pull_rejects_bad_names_and_bad_files(hub):
    for body in ({"repo": "x", "file": "a.gguf"}, {"repo": "a/b", "file": "../a.gguf"}, {"repo": "a/b", "file": "a/b.gguf"}, {"repo": "a/b", "file": "m.bin"}):
        with pytest.raises(UiHttpError):
            handlers.pull_start(hub, body)
    assert _wait(hub, handlers.pull_start(hub, {"repo": "a/b", "file": "fake.gguf"})["job"]["id"])["status"] == "error"
    assert not list((hub.workdir / "models").glob("fake.gguf*"))
    denied = _wait(hub, handlers.pull_start(hub, {"repo": "a/b", "file": "gated.gguf"})["job"]["id"])
    assert denied["status"] == "error" and "HF_TOKEN" in denied["error"]


def test_pull_cancel_and_single_job(hub):
    job = handlers.pull_start(hub, {"repo": "a/b", "file": "slow.gguf"})["job"]
    with pytest.raises(UiHttpError, match="already running"):
        handlers.pull_start(hub, {"repo": "a/b", "file": "good.gguf"})
    handlers.pull_cancel(hub, {"id": job["id"]})
    assert _wait(hub, job["id"])["status"] == "cancelled"
    assert not list((hub.workdir / "models").glob("slow.gguf*"))


def test_routing_role_uses_the_light_model_deterministically(tmp_path, server):
    state = SimpleNamespace(workdir=tmp_path)
    handlers.save_config(state, {"enabled": True, "provider": "custom", "base_url": server, "model": "big", "router_model": "tiny", "max_tokens": 700})
    handlers.chat(state, {"messages": [{"role": "user", "content": "a"}]})
    handlers.chat(state, {"role": "routing", "messages": [{"role": "user", "content": "b"}]})
    main, routed = _FakeOpenAI.seen_requests
    assert main["model"] == "big" and main["max_tokens"] == 700
    assert routed["model"] == "tiny" and routed["temperature"] == 0 and routed["max_tokens"] <= 32
    with pytest.raises(UiHttpError) as e:
        handlers.chat(state, {"role": "admin", "messages": [{"role": "user", "content": "c"}]})
    assert e.value.code == "invalid_role"
    # Without a light model, routing falls back to the main one.
    handlers.save_config(state, {"router_model": ""})
    handlers.chat(state, {"role": "routing", "messages": [{"role": "user", "content": "d"}]})
    assert _FakeOpenAI.seen_requests[-1]["model"] == "big"
