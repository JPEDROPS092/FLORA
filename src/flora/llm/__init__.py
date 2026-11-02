"""LLM access for FLORA agents.

FLORA talks to language models through the OpenAI-compatible HTTP API, which
covers Ollama, llama.cpp, LM Studio, vLLM, OpenAI, OpenRouter and most gateways.
Models only *interpret* results computed by deterministic tools; they never
compute scientific results themselves.
"""

from flora.llm.client import LlmError, OpenAICompatClient
from flora.llm.settings import PRESETS, LlmSettings, SettingsStore

__all__ = ["LlmError", "LlmSettings", "OpenAICompatClient", "PRESETS", "SettingsStore"]
