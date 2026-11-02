import { settleChart } from './settle-chart';

describe('settleChart', () => {
  it('keeps a failure on that chart instead of rejecting the batch', async () => {
    const result = await settleChart(async () => {
      throw new Error('pcoa indisponível');
    });

    expect(result.status).toBe('error');
    expect(result.error).toBe('pcoa indisponível');
  });

  it('returns the figure when the call succeeds', async () => {
    const result = await settleChart(async () => ({ data: [{ y: [1] }], layout: {} }));
    expect(result.status).toBe('ok');
    expect(result.figure?.data.length).toBe(1);
  });
});
