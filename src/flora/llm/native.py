"""In-process llama.cpp provider (no server, no Ollama).

Loads GGUF files from ``<workdir>/models`` (or ``$FLORA_MODELS_DIR``) through the optional
``llama-cpp-python`` package. The model is loaded lazily, cached, and reloaded only when
the file or its runtime options change. ``flora[local]`` installs the dependency.
"""

from __future__ import annotations

import importlib
import os
import threading
import time
from pathlib import Path
from typing import Any

from flora.llm.client import LlmError, strip_reasoning
from flora.llm.settings import LlmSettings

INSTALL_HINT = (
    'llama-cpp-python is not installed. Install it with `pip install "flora[local]"` '
    '(NVIDIA GPU: CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-cache-dir "flora[local]").'
)

_lock = threading.Lock()
_engine: dict[str, Any] = {"key": None, "llm": None}


def models_dir(workdir: Path) -> Path:
    override = os.environ.get("FLORA_MODELS_DIR")
    return Path(override).expanduser() if override else Path(workdir) / "models"


def _load_backend():
    try:
        return importlib.import_module("llama_cpp")
    except ImportError as exc:
        raise LlmError(INSTALL_HINT) from exc


def unload() -> None:
    """Drop the cached model (frees VRAM)."""
    with _lock:
        _engine.update(key=None, llm=None)


class NativeClient:
    """Same surface as :class:`OpenAICompatClient`, backed by an in-process model."""

    def __init__(self, settings: LlmSettings, workdir: Path) -> None:
        self.settings = settings
        self.dir = models_dir(workdir)

    def _resolve(self, name: str) -> Path:
        # A plain *.gguf file name inside the models directory: no paths, no traversal.
        if not name or Path(name).name != name or not name.lower().endswith(".gguf"):
            raise LlmError("Model must be a .gguf file name inside the models directory.")
        path = (self.dir / name).resolve()
        if path.parent != self.dir.resolve() or not path.is_file():
            raise LlmError(f"Model file not found: {self.dir / name}")
        return path

    def list_models(self) -> list[str]:
        return sorted(p.name for p in self.dir.glob("*.gguf")) if self.dir.is_dir() else []

    def _llm(self, name: str):
        path = self._resolve(name)
        key = (str(path), path.stat().st_mtime_ns, self.settings.n_ctx, self.settings.n_gpu_layers)
        with _lock:
            if _engine["key"] != key:
                backend = _load_backend()
                _engine.update(key=None, llm=None)  # release the old model before loading
                try:
                    _engine["llm"] = backend.Llama(
                        model_path=str(path),
                        n_ctx=self.settings.n_ctx,
                        n_gpu_layers=self.settings.n_gpu_layers,
                        verbose=False,
                    )
                except Exception as exc:  # llama.cpp raises ValueError/RuntimeError
                    raise LlmError(f"Could not load {name}: {exc}") from exc
                _engine["key"] = key
            return _engine["llm"]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        name = model or self.settings.model
        started = time.perf_counter()
        llm = self._llm(name)
        with _lock:  # llama.cpp contexts are not thread-safe
            try:
                out = llm.create_chat_completion(
                    messages=messages,
                    temperature=self.settings.temperature if temperature is None else temperature,
                    max_tokens=max_tokens or self.settings.max_tokens,
                )
            except Exception as exc:
                raise LlmError(f"Generation failed: {exc}") from exc
        try:
            text = out["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("Unexpected response from the local model.") from exc
        return {
            "model": name,
            "text": strip_reasoning(text),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "usage": out.get("usage") or {},
        }

    def ping(self) -> dict[str, Any]:
        _load_backend()  # fail early with the install hint
        started = time.perf_counter()
        models = self.list_models()
        return {
            "reachable": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "models": models,
            "model_available": self.settings.model in models,
            "models_dir": str(self.dir),
        }
