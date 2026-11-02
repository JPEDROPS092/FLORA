import { t } from '../i18n/i18n';
import { LocalModel, ProviderPreset } from './llm.models';

export const PROVIDERS: readonly ProviderPreset[] = [
  { id: 'ollama', label: 'Ollama', baseUrl: 'http://127.0.0.1:11434/v1', needsKey: false, local: true },
  { id: 'lmstudio', label: 'LM Studio', baseUrl: 'http://127.0.0.1:1234/v1', needsKey: false, local: true },
  { id: 'llamacpp', label: 'llama.cpp server', baseUrl: 'http://127.0.0.1:8080/v1', needsKey: false, local: true },
  { id: 'native', label: t('llama.cpp embutido (sem servidor)'), baseUrl: '', needsKey: false, local: true },
  { id: 'gemini', label: 'Google Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', needsKey: true, local: false },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', needsKey: true, local: false },
  { id: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', needsKey: true, local: false },
  { id: 'custom', label: t('Compatível com OpenAI (personalizado)'), baseUrl: '', needsKey: false, local: false }
];

/** Candidates for a first benchmark on a 6 GB GPU. Sizes are ~4-bit quantised estimates, without KV cache. */
export const LOCAL_MODELS: readonly LocalModel[] = [
  { id: 'qwen3.5-4b', name: 'Qwen3.5 4B', family: 'Qwen', tag: 'qwen3.5:4b', sizeGb: 3.5, role: t('Agente principal: MCP, planejamento e RAG'), fit: 'excellent' },
  { id: 'granite-3b', name: 'Granite 4.2 3B', family: 'IBM Granite', tag: 'granite4:3b', sizeGb: 2.5, role: t('Validar argumentos de ferramentas e JSON estruturado'), fit: 'excellent' },
  { id: 'phi4-mini', name: 'Phi-4-mini 3.8B', family: 'Microsoft Phi', tag: 'phi4-mini', sizeGb: 2.8, role: t('Extração, classificação e saídas estruturadas'), fit: 'excellent' },
  { id: 'qwen3-4b', name: 'Qwen3 4B', family: 'Qwen', tag: 'qwen3:4b', sizeGb: 2.5, role: t('Tool calling e interpretação'), fit: 'excellent', hf: { repo: 'Qwen/Qwen3-4B-GGUF', file: 'Qwen3-4B-Q4_K_M.gguf' } },
  { id: 'qwen3.5-2b', name: 'Qwen3.5 2B', family: 'Qwen', tag: 'qwen3.5:2b', sizeGb: 1.8, role: t('Agentes leves e roteamento'), fit: 'excellent' },
  { id: 'qwen3-1.7b', name: 'Qwen3 1.7B', family: 'Qwen', tag: 'qwen3:1.7b', sizeGb: 1.4, role: t('Extração e classificação'), fit: 'excellent', hf: { repo: 'Qwen/Qwen3-1.7B-GGUF', file: 'Qwen3-1.7B-Q8_0.gguf' } },
  { id: 'gemma3-4b', name: 'Gemma 3 4B', family: 'Google Gemma', tag: 'gemma3:4b', sizeGb: 3.3, role: t('Textos e interpretação'), fit: 'good', hf: { repo: 'ggml-org/gemma-3-4b-it-GGUF', file: 'gemma-3-4b-it-Q4_K_M.gguf' } },
  { id: 'qwen3-8b', name: 'Qwen3 8B', family: 'Qwen', tag: 'qwen3:8b', sizeGb: 5.2, role: t('Raciocínio mais complexo'), fit: 'limited', hf: { repo: 'Qwen/Qwen3-8B-GGUF', file: 'Qwen3-8B-Q4_K_M.gguf' } },
  { id: 'qwen3.5-9b', name: 'Qwen3.5 9B', family: 'Qwen', tag: 'qwen3.5:9b', sizeGb: 6.5, role: t('Planejamento e MCP (melhor com offload)'), fit: 'limited' }
];

/** KV cache + runtime headroom added to the quantised weights. */
export const RUNTIME_OVERHEAD_GB = 1.0;

export type Placement = 'gpu' | 'tight' | 'offload';

export function placement(sizeGb: number, vramGb: number): Placement {
  const need = sizeGb + RUNTIME_OVERHEAD_GB;
  if (need <= vramGb - 0.5) return 'gpu';
  if (need <= vramGb + 0.5) return 'tight';
  return 'offload';
}

/** "qwen3:4b" matches an installed "qwen3:4b" or "qwen3:4b-instruct-q4_K_M". */
export function isInstalled(tag: string, installed: readonly string[]): boolean {
  return installed.some((m) => m === tag || m.startsWith(`${tag}-`) || (!tag.includes(':') && m.split(':')[0] === tag));
}
