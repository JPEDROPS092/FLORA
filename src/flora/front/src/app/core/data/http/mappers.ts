import {
  ChartResult,
  DifferentialTaxon,
  DownloadJob,
  GroupComparison,
  IngestPreview,
  MlExperiment,
  PlotFigure,
  Provenance,
  RecentAnalysis,
  ReportSection,
  SampleQcRow,
  TaxonNode
} from '../../models/domain';

/** Loose JSON object coming from the Python API (snake_case). */
export type Raw = Record<string, unknown>;

const obj = (v: unknown): Raw => (v && typeof v === 'object' ? (v as Raw) : {});
const arr = (v: unknown): Raw[] => (Array.isArray(v) ? (v as Raw[]) : []);
const str = (v: unknown, d = ''): string => (v === null || v === undefined ? d : String(v));
const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const numOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)) : []);
const pairs = (v: unknown): { label: string; value: string }[] => arr(v).map((p) => ({ label: str(p['label']), value: str(p['value']) }));

export function toProvenance(raw: unknown): Provenance {
  const p = obj(raw);
  return {
    pipelineVersion: str(p['pipeline_version'], 'FLORA'),
    seed: num(p['seed']),
    parameters: pairs(p['parameters']),
    packages: arr(p['packages']).map((x) => ({ name: str(x['name']), version: str(x['version']) })),
    inputs: strings(p['inputs']),
    history: arr(p['history']).map((x) => ({ at: str(x['at']), event: str(x['event']) }))
  };
}

export function toChart(raw: unknown): ChartResult {
  const c = obj(raw);
  const status = c['status'] === 'ok' || c['status'] === 'error' ? c['status'] : 'empty';
  const fig = obj(c['figure']);
  return {
    status,
    figure: status === 'ok' ? { data: arr(fig['data']), layout: obj(fig['layout']) } : undefined,
    error: c['error'] === undefined ? undefined : str(c['error'])
  };
}

export function toFigure(raw: unknown): PlotFigure {
  const f = obj(raw);
  return { data: arr(f['data']), layout: obj(f['layout']) };
}

export function toExperiment(raw: unknown): MlExperiment {
  const e = obj(raw);
  return {
    id: str(e['id']),
    name: str(e['name']),
    model: str(e['model']),
    status: e['status'] === 'failed' ? 'failed' : 'completed',
    createdAt: str(e['created_at']).slice(0, 16).replace('T', ' '),
    accuracy: num(e['accuracy']),
    f1Macro: num(e['f1_macro']),
    rocAuc: numOrNull(e['roc_auc']),
    cvAccuracyMean: num(e['cv_accuracy_mean']),
    trainN: num(e['train_n']),
    testN: num(e['test_n']),
    features: num(e['features']),
    importanceKind: e['importance_kind'] === 'shap' ? 'shap' : 'impurity',
    confusion: toChart(e['confusion']),
    roc: toChart(e['roc']),
    importance: toChart(e['importance']),
    labels: strings(e['labels']),
    matrix: (Array.isArray(e['matrix']) ? (e['matrix'] as unknown[]) : []).map((row) => (Array.isArray(row) ? row.map((n) => num(n)) : [])),
    importances: arr(e['importances']).map((i) => ({ feature: str(i['feature']), value: num(i['value']) })),
    config: pairs(e['config']),
    limitations: strings(e['limitations']),
    provenance: toProvenance(e['provenance']),
    error: e['error'] === undefined ? undefined : str(e['error']),
    mocked: false
  };
}

export function toRecent(raw: unknown): RecentAnalysis {
  const r = obj(raw);
  const status = r['status'] === 'failed' || r['status'] === 'running' ? r['status'] : 'completed';
  return {
    id: str(r['id']),
    name: str(r['name']),
    kind: str(r['kind']),
    status,
    finishedAt: str(r['finished_at']),
    projectId: str(r['project_id']),
    summary: str(r['summary']),
    provenance: toProvenance(r['provenance'])
  };
}

export function toPreview(raw: unknown): IngestPreview {
  const p = obj(raw);
  const s = obj(p['summary']);
  return {
    columns: strings(p['columns']),
    rows: arr(p['rows']).map(
      (r): SampleQcRow => ({
        sampleId: str(r['sample_id']),
        metadataId: str(r['metadata_id']),
        group: r['group'] === null || r['group'] === undefined ? null : str(r['group']),
        inMetadata: !!r['in_metadata'],
        inAsv: !!r['in_asv'],
        reads: numOrNull(r['reads']),
        status: r['status'] === 'fail' || r['status'] === 'warn' ? r['status'] : 'pass',
        issues: strings(r['issues'])
      })
    ),
    summary: {
      matched: num(s['matched']),
      metadataOnly: num(s['metadata_only']),
      asvOnly: num(s['asv_only']),
      lowDepth: num(s['low_depth']),
      totalAsvs: num(s['total_asvs'])
    },
    histogram: toFigure(p['histogram']),
    mocked: false,
    warnings: strings(p['warnings'])
  };
}

export function toTree(raw: unknown): TaxonNode[] {
  return arr(raw).map((n) => ({
    key: str(n['key']),
    label: str(n['label']),
    rank: str(n['rank']),
    abundance: num(n['abundance']),
    children: n['children'] ? toTree(n['children']) : undefined
  }));
}

export function toComparisons(raw: unknown): GroupComparison[] {
  return arr(raw).map((c) => ({
    group: str(c['group']),
    n: num(c['n']),
    shannonMean: num(c['shannon_mean']),
    shannonSd: num(c['shannon_sd']),
    observedMean: num(c['observed_mean'])
  }));
}

export function toDifferential(raw: unknown): DifferentialTaxon[] {
  return arr(raw).map((d) => ({
    taxon: str(d['taxon']),
    rank: d['rank'] === 'phylum' ? 'phylum' : 'genus',
    log2FoldChange: num(d['log2_fold_change']),
    pValue: num(d['p_value']),
    qValue: num(d['q_value']),
    higherIn: str(d['higher_in']),
    contrast: str(d['contrast'])
  }));
}

export function toSections(raw: unknown): ReportSection[] {
  return arr(raw).map((s) => {
    const table = s['table'] ? obj(s['table']) : null;
    return {
      id: str(s['id']),
      title: str(s['title']),
      narrative: str(s['narrative']),
      included: s['included'] !== false,
      figure: (s['figure'] as ReportSection['figure']) ?? null,
      table: table ? { columns: strings(table['columns']), rows: (Array.isArray(table['rows']) ? (table['rows'] as unknown[]) : []).map((r) => strings(r)) } : null
    };
  });
}

export function toDownload(raw: unknown): DownloadJob {
  const j = obj(raw);
  const status = j['status'];
  return {
    id: str(j['id']),
    source: str(j['source']),
    status: status === 'failed' || status === 'queued' || status === 'ready' ? status : 'completed',
    detail: str(j['detail']),
    artifacts: arr(j['artifacts']).map((a) => ({ label: str(a['label']), path: str(a['path']) })),
    mocked: false,
    createdAt: str(j['created_at'])
  };
}
