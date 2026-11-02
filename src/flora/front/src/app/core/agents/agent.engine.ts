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
    step('exploration.alpha', 'Calcular diversidade alfa', `${bundle.sampleCount} amostras, Shannon, ${DEFAULT_QUERY.normalize.toUpperCase()}`),
    step('exploration.compare', 'Comparar grupos', `${rows.length} grupos`)
  ];
  if (!rows.length) {
    return { agentId: 'analyst', steps, actions: [], text: bundle.note ?? 'A fonte atual não devolveu resumo por grupo.' };
  }
  const [top, ...rest] = rows;
  const low = rest[rest.length - 1] ?? top;
  const text =
    `${top.group} tem a maior diversidade de Shannon (${fmt(top.shannonMean)} ± ${fmt(top.shannonSd)}, n=${top.n}); ` +
    `${low.group} tem a menor (${fmt(low.shannonMean)}). ` +
    `Diferença de ${fmt(top.shannonMean - low.shannonMean)} entre extremos. ` +
    `Isto é descritivo: confirme com teste estatístico e correção para múltiplas comparações antes de concluir.`;
  return {
    agentId: 'analyst', steps, text,
    actions: [
      action('Abrir diversidade alfa (Shannon)', 'pi pi-chart-bar', '/explorer', { view: 'alpha', metric: 'shannon' }),
      action('Ver PCoA Bray–Curtis', 'pi pi-chart-scatter', '/explorer', { view: 'pcoa', distance: 'braycurtis' })
    ]
  };
}

async function differential(repo: FloraRepository): Promise<AgentReply> {
  const bundle = await repo.exploration(DEFAULT_QUERY);
  const sig = bundle.differential.filter((d) => d.qValue < 0.05).sort((a, b) => Math.abs(b.log2FoldChange) - Math.abs(a.log2FoldChange));
  const steps = [
    step('exploration.differential', 'Listar táxons diferenciais', `${bundle.differential.length} contrastes`),
    step('stats.filter_fdr', 'Filtrar q < 0,05', `${sig.length} significativos`)
  ];
  const text = sig.length
    ? `${sig.length} táxons com q < 0,05. Os mais fortes: ` +
      sig.slice(0, 3).map((d) => `${d.taxon} (log2FC ${fmt(d.log2FoldChange)}, maior em ${d.higherIn})`).join('; ') +
      '. Resultados de abundância relativa são composicionais; interprete o sinal, não a magnitude absoluta.'
    : 'Nenhum táxon passou q < 0,05 nesta configuração.';
  return {
    agentId: 'taxonomist', steps, text,
    actions: [action('Abrir taxonomia por gênero', 'pi pi-sitemap', '/explorer', { view: 'taxonomy', rank: 'genus', topN: 8 })]
  };
}

async function models(repo: FloraRepository): Promise<AgentReply> {
  const rows = await repo.comparison();
  const steps = [step('ml.comparison', 'Comparar modelos treinados', `${rows.length} experimentos`)];
  if (!rows.length) return { agentId: 'taxonomist', steps, actions: [], text: 'Ainda não há experimentos para comparar. Treine um modelo no ML Lab.' };
  const best = [...rows].sort((a, b) => b.cvAccuracyMean - a.cvAccuracyMean)[0];
  const text =
    `${best.model} lidera na validação cruzada (acc ${fmt(best.cvAccuracyMean)}, F1 macro ${fmt(best.f1Macro)}` +
    `${best.rocAuc != null ? `, AUC ${fmt(best.rocAuc)}` : ''}; seed ${best.seed}, ${best.features} features). ` +
    `Ressalvas: cohort pequeno, risco de overfitting e vazamento entre réplicas da mesma unidade; valide em coorte externa.`;
  return { agentId: 'taxonomist', steps, text, actions: [action('Abrir ML Lab', 'pi pi-microchip', '/ml')] };
}

async function qc(repo: FloraRepository): Promise<AgentReply> {
  const snap = await repo.pipeline();
  const { rows, summary } = snap.qc;
  const fails = rows.filter((r) => r.status === 'fail');
  const warns = rows.filter((r) => r.status === 'warn');
  const steps = [
    step('pipeline.qc_table', 'Ler QC por amostra', `${rows.length} amostras`),
    step('pipeline.reconcile', 'Reconciliar metadata × ASV', `${summary.matched} casadas, ${summary.metadataOnly + summary.asvOnly} órfãs`)
  ];
  const detail = fails.slice(0, 3).map((r) => `${r.sampleId} (${r.issues[0] ?? 'falha'})`).join(', ');
  const text =
    `${fails.length} falhas e ${warns.length} alertas; ${summary.lowDepth} amostras com baixa profundidade. ` +
    (fails.length ? `Pior caso: ${detail}. ` : '') +
    (snap.ingested ? 'A ingestão já foi confirmada.' : 'A ingestão só fecha com metadata, ASV e taxonomia bem-sucedidos; resolva as falhas antes de confirmar.');
  return { agentId: 'qc', steps, text, actions: [action('Abrir QC no Pipeline Studio', 'pi pi-sitemap', '/pipeline')] };
}

async function reporter(repo: FloraRepository): Promise<AgentReply> {
  const draft = await repo.reportDraft();
  const included = draft.sections.filter((s) => s.included);
  const empty = included.filter((s) => !s.narrative.trim());
  const noFigure = included.filter((s) => s.figure === null);
  const steps = [
    step('report.draft', 'Ler rascunho', `${draft.sections.length} seções`),
    step('report.parameters', 'Coletar parâmetros', `${draft.parameters.length} parâmetros para Métodos`)
  ];
  const text =
    `${included.length}/${draft.sections.length} seções incluídas. ` +
    (empty.length ? `Sem texto: ${empty.map((s) => s.title).join(', ')}. ` : 'Todas as incluídas têm texto. ') +
    (noFigure.length ? `${noFigure.length} sem figura. ` : '') +
    'Registre seed e versões no bloco de Métodos para reprodutibilidade.';
  return { agentId: 'reporter', steps, text, actions: [action('Abrir Report Builder', 'pi pi-file', '/reports')] };
}

export const AGENT_IDS = AGENTS.map((a) => a.id);
