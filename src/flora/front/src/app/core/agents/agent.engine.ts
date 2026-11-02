import { t } from '../i18n/i18n';
import { FloraRepository } from '../data/flora.repository';
import { ExplorationQuery } from '../models/domain';
import { AGENTS, AUTO_ROUTES } from './agent.catalog';
import { AgentAction, AgentId, AgentReply, AgentStep } from './agent.models';

const DEFAULT_QUERY: ExplorationQuery = {
  groups: ['Rhizosphere', 'Bulk soil', 'Endosphere'],
  metric: 'shannon',
  normalize: 'clr',
  rank: 'genus',
  distance: 'braycurtis',
  topN: 8
};

let seq = 0;
export const nextId = (prefix: string): string => `${prefix}-${Date.now().toString(36)}-${++seq}`;

export function routeAgent(prompt: string, preferred: AgentId | 'auto'): AgentId {
  if (preferred !== 'auto') return preferred;
  return AUTO_ROUTES.find((r) => r.pattern.test(prompt))?.agent ?? 'analyst';
}

function step(tool: string, label: string, detail: string): AgentStep {
  return { tool, label, detail, status: 'done', ms: 120 + ((tool.length * 37) % 380) };
}

function action(label: string, icon: string, path: string, queryParams?: Record<string, string | number>): AgentAction {
  return { id: nextId('act'), label, icon, path, queryParams, applied: false };
}

const fmt = (n: number, d = 2): string => n.toFixed(d);

/**
 * Mock agent brain. Every answer is computed from the repository (mock or HTTP),
 * so swapping the data source keeps the agents honest. A real LLM backend replaces
 * only this function; the UI contract (steps + proposed actions) stays the same.
 */
export async function runAgent(repo: FloraRepository, agentId: AgentId, prompt: string): Promise<AgentReply> {
  switch (agentId) {
    case 'qc': return qc(repo);
    case 'reporter': return reporter(repo);
    case 'taxonomist': return /modelo|model|ml|random|xgboost|shap|roc/i.test(prompt) ? models(repo) : differential(repo);
    default: return diversity(repo);
  }
}

async function diversity(repo: FloraRepository): Promise<AgentReply> {
  const bundle = await repo.exploration(DEFAULT_QUERY);
  const rows = [...bundle.comparisons].sort((a, b) => b.shannonMean - a.shannonMean);
  const steps = [
    step('exploration.alpha', t('Calcular diversidade alfa'), t('{n} amostras, Shannon, {norm}', { n: bundle.sampleCount, norm: DEFAULT_QUERY.normalize.toUpperCase() })),
    step('exploration.compare', t('Comparar grupos'), t('{n} grupos', { n: rows.length }))
  ];
  if (!rows.length) {
    return { agentId: 'analyst', steps, actions: [], text: bundle.note ?? t('A fonte atual não devolveu resumo por grupo.') };
  }
  const [top, ...rest] = rows;
  const low = rest[rest.length - 1] ?? top;
  const text = t(
    '{top} tem a maior diversidade de Shannon ({topMean} ± {topSd}, n={n}); {low} tem a menor ({lowMean}). Diferença de {diff} entre extremos. Isto é descritivo: confirme com teste estatístico e correção para múltiplas comparações antes de concluir.',
    { top: top.group, topMean: fmt(top.shannonMean), topSd: fmt(top.shannonSd), n: top.n, low: low.group, lowMean: fmt(low.shannonMean), diff: fmt(top.shannonMean - low.shannonMean) }
  );
  return {
    agentId: 'analyst', steps, text,
    actions: [
      action(t('Abrir diversidade alfa (Shannon)'), 'pi pi-chart-bar', '/explorer', { view: 'alpha', metric: 'shannon' }),
      action(t('Ver PCoA Bray–Curtis'), 'pi pi-chart-scatter', '/explorer', { view: 'pcoa', distance: 'braycurtis' })
    ]
  };
}

async function differential(repo: FloraRepository): Promise<AgentReply> {
  const bundle = await repo.exploration(DEFAULT_QUERY);
  const sig = bundle.differential.filter((d) => d.qValue < 0.05).sort((a, b) => Math.abs(b.log2FoldChange) - Math.abs(a.log2FoldChange));
  const steps = [
    step('exploration.differential', t('Listar táxons diferenciais'), t('{n} contrastes', { n: bundle.differential.length })),
    step('stats.filter_fdr', t('Filtrar q < 0,05'), t('{n} significativos', { n: sig.length }))
  ];
  const text = sig.length
    ? t('{n} táxons com q < 0,05. Os mais fortes: {list}. Resultados de abundância relativa são composicionais; interprete o sinal, não a magnitude absoluta.', {
        n: sig.length,
        list: sig.slice(0, 3).map((d) => t('{taxon} (log2FC {fc}, maior em {grp})', { taxon: d.taxon, fc: fmt(d.log2FoldChange), grp: d.higherIn })).join('; ')
      })
    : t('Nenhum táxon passou q < 0,05 nesta configuração.');
  return {
    agentId: 'taxonomist', steps, text,
    actions: [action(t('Abrir taxonomia por gênero'), 'pi pi-sitemap', '/explorer', { view: 'taxonomy', rank: 'genus', topN: 8 })]
  };
}

async function models(repo: FloraRepository): Promise<AgentReply> {
  const rows = await repo.comparison();
  const steps = [step('ml.comparison', t('Comparar modelos treinados'), t('{n} experimentos', { n: rows.length }))];
  if (!rows.length) return { agentId: 'taxonomist', steps, actions: [], text: t('Ainda não há experimentos para comparar. Treine um modelo no ML Lab.') };
  const best = [...rows].sort((a, b) => b.cvAccuracyMean - a.cvAccuracyMean)[0];
  const text = t(
    '{model} lidera na validação cruzada (acc {acc}, F1 macro {f1}{auc}; seed {seed}, {feat} features). Ressalvas: cohort pequeno, risco de overfitting e vazamento entre réplicas da mesma unidade; valide em coorte externa.',
    { model: best.model, acc: fmt(best.cvAccuracyMean), f1: fmt(best.f1Macro), auc: best.rocAuc != null ? `, AUC ${fmt(best.rocAuc)}` : '', seed: best.seed, feat: best.features }
  );
  return { agentId: 'taxonomist', steps, text, actions: [action(t('Abrir ML Lab'), 'pi pi-microchip', '/ml')] };
}

async function qc(repo: FloraRepository): Promise<AgentReply> {
  const snap = await repo.pipeline();
  const { rows, summary } = snap.qc;
  const fails = rows.filter((r) => r.status === 'fail');
  const warns = rows.filter((r) => r.status === 'warn');
  const steps = [
    step('pipeline.qc_table', t('Ler QC por amostra'), t('{n} amostras', { n: rows.length })),
    step('pipeline.reconcile', t('Reconciliar metadata × ASV'), t('{m} casadas, {o} órfãs', { m: summary.matched, o: summary.metadataOnly + summary.asvOnly }))
  ];
  const detail = fails.slice(0, 3).map((r) => `${r.sampleId} (${r.issues[0] ?? t('falha')})`).join(', ');
  const text =
    t('{f} falhas e {w} alertas; {d} amostras com baixa profundidade.', { f: fails.length, w: warns.length, d: summary.lowDepth }) + ' ' +
    (fails.length ? t('Pior caso: {list}.', { list: detail }) + ' ' : '') +
    (snap.ingested ? t('A ingestão já foi confirmada.') : t('A ingestão só fecha com metadata, ASV e taxonomia bem-sucedidos; resolva as falhas antes de confirmar.'));
  return { agentId: 'qc', steps, text, actions: [action(t('Abrir QC no Pipeline Studio'), 'pi pi-sitemap', '/pipeline')] };
}

async function reporter(repo: FloraRepository): Promise<AgentReply> {
  const draft = await repo.reportDraft();
  const included = draft.sections.filter((s) => s.included);
  const empty = included.filter((s) => !s.narrative.trim());
  const noFigure = included.filter((s) => s.figure === null);
  const steps = [
    step('report.draft', t('Ler rascunho'), t('{n} seções', { n: draft.sections.length })),
    step('report.parameters', t('Coletar parâmetros'), t('{n} parâmetros para Métodos', { n: draft.parameters.length }))
  ];
  const text =
    t('{a}/{b} seções incluídas.', { a: included.length, b: draft.sections.length }) + ' ' +
    (empty.length ? t('Sem texto: {list}.', { list: empty.map((x) => x.title).join(', ') }) : t('Todas as incluídas têm texto.')) + ' ' +
    (noFigure.length ? t('{n} sem figura.', { n: noFigure.length }) + ' ' : '') +
    t('Registre seed e versões no bloco de Métodos para reprodutibilidade.');
  return { agentId: 'reporter', steps, text, actions: [action(t('Abrir Report Builder'), 'pi pi-file', '/reports')] };
}

export const AGENT_IDS = AGENTS.map((a) => a.id);
