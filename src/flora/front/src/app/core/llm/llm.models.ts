export type ProviderId = 'ollama' | 'lmstudio' | 'llamacpp' | 'native' | 'gemini' | 'openai' | 'openrouter' | 'custom';

export interface LlmSettings {
  enabled: boolean;
  provider: ProviderId;
  baseUrl: string;
  /** Only held in the browser in direct (mock) mode; the backend never returns it. */
  apiKey: string;
  hasApiKey: boolean;
  model: string;
  routerModel: string;
  temperature: number;
  maxTokens: number;
  /** In-process llama.cpp only. */
  nCtx: number;
  nGpuLayers: number;
  /** Used only to estimate which local models fit; never sent anywhere. */
  vramGb: number;
}

export interface ProviderPreset {
  id: ProviderId;
  label: string;
  baseUrl: string;
  needsKey: boolean;
  local: boolean;
}

export type LlmStatus = 'idle' | 'testing' | 'ok' | 'error';

export interface ChatMessage { role: 'system' | 'user' | 'assistant'; content: string }
export interface ChatResult { model: string; text: string; elapsedMs: number }

export interface LocalModel {
  id: string;
  name: string;
  family: string;
  /** Ollama tag. Suggested: confirm against `ollama list` / the Ollama library. */
  tag: string;
  sizeGb: number;
  role: string;
  fit: 'excellent' | 'good' | 'limited';
  /** Suggested Hugging Face GGUF; the download itself validates it. */
  hf?: { repo: string; file: string };
}

export interface PullJob {
  id: string; repo: string; file: string;
  status: 'queued' | 'downloading' | 'done' | 'error' | 'cancelled';
  bytesDone: number; bytesTotal: number; percent: number; error: string;
}
