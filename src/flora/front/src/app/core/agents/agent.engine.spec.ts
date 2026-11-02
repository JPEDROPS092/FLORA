import { describe, expect, it } from 'vitest';

import { MockFloraRepository } from '../data/mock/mock-flora.repository';
import { routeAgent, runAgent } from './agent.engine';

describe('agent engine (mock study)', () => {
  const repo = new MockFloraRepository();

  it('routes prompts to the right agent and honours explicit choice', () => {
    expect(routeAgent('quais amostras falharam no QC?', 'auto')).toBe('qc');
    expect(routeAgent('compare a diversidade de Shannon', 'auto')).toBe('analyst');
    expect(routeAgent('qual modelo é melhor?', 'auto')).toBe('taxonomist');
    expect(routeAgent('exportar relatório', 'auto')).toBe('reporter');
    expect(routeAgent('qualquer coisa', 'reporter')).toBe('reporter');
  });

  it('every agent answers with data-grounded steps and unapplied actions', async () => {
    for (const id of ['analyst', 'qc', 'taxonomist', 'reporter'] as const) {
      const reply = await runAgent(repo, id, id === 'taxonomist' ? 'modelo' : 'resumo');
      expect(reply.text.length).toBeGreaterThan(20);
      expect(reply.steps.length).toBeGreaterThan(0);
      expect(reply.actions.every((a) => a.applied === false && a.path.startsWith('/'))).toBe(true);
    }
  });
});
