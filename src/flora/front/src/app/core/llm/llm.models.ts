export type ProviderId = 'ollama' | 'lmstudio' | 'llamacpp' | 'native' | 'gemini' | 'openai' | 'openrouter' | 'qwen' | 'custom';

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

/** `interpretation` uses the main model; `routing` the light model (intent classification). */
export type ModelRole = 'interpretation' | 'routing';

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

/** OpenAI-style history the operator keeps between turns (the server is stateless). */
export interface OperatorMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: unknown[];
  tool_call_id?: string;
}

export interface OperatorStep { tool: string; ok: boolean; ms: number; detail: string; call_id?: string }

/** What a tool produced for the researcher (never sent back to the model). */
export type OperatorArtifact =
  | { type: 'plot'; title: string; figure: { data: Record<string, unknown>[]; layout: Record<string, unknown> } }
  | { type: 'table'; title: string; columns: string[]; rows: unknown[][]; total: number }
  | { type: 'map'; title: string; map: Record<string, unknown> }
  | { type: 'navigate'; label: string; path: string; query: Record<string, string> };

/** An action the model asked for that changes data; it only runs after the researcher approves. */
export interface PendingApproval { id: string; tool: string; description: string; arguments: Record<string, unknown> }

export interface OperatorTurn {
  messages: OperatorMessage[];
  artifacts: OperatorArtifact[];
  steps: OperatorStep[];
  pending: PendingApproval[];
  text: string;
  model: string;
  usage: { total_tokens?: number };
}

/** A saved operator analysis. The list carries counts only; the detail has the charts and tables. */
export interface SavedRun {
  id: string;
  createdAt: string;
  question: string;
  text: string;
  steps: number;
  artifacts: number;
  model: string;
  tools: string[];
  pending: number;
}
