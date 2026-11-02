import { describe, expect, it } from 'vitest';

import { LOCAL_MODELS, PROVIDERS, isInstalled, placement } from './llm.catalog';
import { stripReasoning } from './llm.service';

describe('llm catalog', () => {
  it('classifies models against a 6 GB GPU', () => {
    expect(placement(2.5, 6)).toBe('gpu');
    expect(placement(5.2, 6)).toBe('tight');
    expect(placement(6.5, 6)).toBe('offload');
    expect(placement(5.2, 12)).toBe('gpu');
  });

  it('detects installed Ollama tags incl. quantised variants', () => {
    expect(isInstalled('qwen3:4b', ['qwen3:4b'])).toBe(true);
    expect(isInstalled('qwen3:4b', ['qwen3:4b-instruct-q4_K_M'])).toBe(true);
    expect(isInstalled('phi4-mini', ['phi4-mini:latest'])).toBe(true);
    expect(isInstalled('qwen3:8b', ['qwen3:4b'])).toBe(false);
  });

  it('offers local providers, Gemini and a custom OpenAI-compatible endpoint', () => {
    const ids = PROVIDERS.map((p) => p.id);
    expect(ids).toEqual(expect.arrayContaining(['ollama', 'gemini', 'openai', 'custom']));
    expect(PROVIDERS.find((p) => p.id === 'gemini')?.baseUrl).toContain('generativelanguage.googleapis.com');
    expect(LOCAL_MODELS.length).toBeGreaterThanOrEqual(9);
  });

  it('removes reasoning blocks', () => {
    expect(stripReasoning('<think>plan\nmore</think>\nAnswer')).toBe('Answer');
  });
});
