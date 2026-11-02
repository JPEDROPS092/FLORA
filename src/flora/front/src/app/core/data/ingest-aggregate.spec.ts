import { aggregateIngest } from './ingest-aggregate';

describe('aggregateIngest', () => {
  it('succeeds only when every step succeeds', () => {
    expect(
      aggregateIngest([
        { step: 'metadata', success: true },
        { step: 'asv', success: true },
        { step: 'taxonomy', success: true }
      ]).success
    ).toBe(true);
  });

  it('fails the batch when one request fails', () => {
    const outcome = aggregateIngest([
      { step: 'metadata', success: true, detail: '80 amostras' },
      { step: 'asv', success: false, error: 'arquivo ausente' },
      { step: 'taxonomy', success: true }
    ]);

    expect(outcome.success).toBe(false);
    expect(outcome.error).toContain('asv: arquivo ausente');
    expect(outcome.steps.length).toBe(3);
  });

  it('does not report success for an empty batch', () => {
    expect(aggregateIngest([]).success).toBe(false);
  });
});
