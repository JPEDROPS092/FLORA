import { ChartResult, PlotFigure } from '../models/domain';

/**
 * Each figure is settled on its own. One failed endpoint must not blank the others.
 */
export async function settleChart(load: () => Promise<PlotFigure | null>): Promise<ChartResult> {
  try {
    const figure = await load();
    if (!figure || figure.data.length === 0) {
      return { status: 'empty', error: 'Sem dados para estes filtros.' };
    }
    return { status: 'ok', figure };
  } catch (error) {
    return {
      status: 'error',
      error: error instanceof Error ? error.message : 'Falha ao gerar o gráfico.'
    };
  }
}
