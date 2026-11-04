import {
  CatalogEntry,
  CatalogFile,
  ChartResult,
  DifferentialTaxon,
  DownloadJob,
  MetadataPreview,
  StudyEntry,
  SampleMap,
  LocalDataset,
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

export function toCatalogEntry(raw: unknown): CatalogEntry {
  const s = obj(raw);
  return {
    id: str(s['id']),
    title: str(s['title']),
    titlePt: str(s['title_pt']) || str(s['title']),
    description: str(s['description']),
    source: str(s['source']),
    accession: str(s['accession']),
    biome: str(s['biome']),
    biomeLabel: str(s['biome_label']) || str(s['biome']),
    host: str(s['host']),
    hostLabel: str(s['host_label']) || str(s['host']),
    region: str(s['region']),
    regionLabel: str(s['region_label']) || str(s['region']),
    country: str(s['country']),
    lat: numOrNull(s['lat']),
    lon: numOrNull(s['lon']),
    nSamples: Number(s['n_samples']) || 0,
    nRuns: s['n_runs'] === null || s['n_runs'] === undefined || s['n_runs'] === '' ? null : Number(s['n_runs']),
    seqType: str(s['seq_type']),
    marker: str(s['marker']),
    markerRegion: str(s['marker_region']),
    platform: str(s['platform']),
    license: str(s['license']),
    licenseNote: str(s['license_note']),
    citation: str(s['citation']),
    citationDoi: str(s['citation_doi']),
    bioproject: str(s['bioproject']),
    secondary: str(s['secondary']),
    centre: str(s['centre']),
    url: str(s['url']),
    verifiedAt: str(s['verified_at']),
    importable: s['importable'] !== false,
    highlight: str(s['highlight']),
    tags: strings(s['tags']),
    downloadNote: str(s['download_note']),
    files: arr(s['files']).map(toCatalogFile)
  };
}

export function toCatalogFile(raw: unknown): CatalogFile {
  const f = obj(raw);
  return {
    kind: str(f['kind']),
    label: str(f['label']),
    url: str(f['url']),
    size: numOrNull(f['size'])
  };
}

export function toMetadataPreview(raw: unknown): MetadataPreview {
  const p = obj(raw);
  return {
    source: str(p['source']),
    accession: str(p['accession']),
    columns: strings(p['columns']),
    rows: arr(p['rows']).map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, value == null ? '' : String(value)]))),
    rowCount: Number(p['row_count']) || 0,
    truncated: p['truncated'] === true
  };
}

export function toStudy(raw: unknown): StudyEntry {
  const s = obj(raw);
  return {
    source: str(s['source']),
    accession: str(s['accession']),
    title: str(s['title']),
    description: str(s['description']),
    biome: str(s['biome']),
    samples: Number(s['samples']) || 0,
    centre: str(s['centre']),
    bioproject: str(s['bioproject']),
    secondary: str(s['secondary']),
    updated: str(s['updated']),
    url: str(s['url']),
    origin: s['origin'] === 'live' ? 'live' : 'curated',
    importable: s['importable'] !== false
  };
}

export function toLocalDataset(raw: unknown): LocalDataset {
  const d = obj(raw);
  const files = obj(d['files']);
  const origin = d['origin'];
  return {
    id: str(d['id']),
    label: str(d['label']),
    path: str(d['path']),
    origin: origin === 'project' || origin === 'upload' ? origin : 'workdir',
    files: {
      metadata: files['metadata'] ? str(files['metadata']) : undefined,
      asv: files['asv'] ? str(files['asv']) : undefined,
      taxonomy: files['taxonomy'] ? str(files['taxonomy']) : undefined
    },
    missing: arr(d['missing']).map((m) => String(m)),
    complete: d['complete'] === true,
    rawReadsOnly: d['raw_reads_only'] === true,
    samples: Number(d['samples']) || 0,
    columns: arr(d['columns']).map((c) => String(c)),
    modified: str(d['modified'])
  };
}

export function toSampleMap(raw: unknown): SampleMap {
  const m = obj(raw);
  const reason = m['reason'];
  return {
    available: m['available'] === true,
    reason: reason === 'not_downloaded' || reason === 'no_coordinates' || reason === 'no_valid_coordinates' ? reason : '',
    points: arr(m['points']).map((p) => ({
      lat: Number(p['lat']),
      lon: Number(p['lon']),
      group: str(p['group']),
      n: Number(p['n']) || 1,
      ids: strings(p['ids'])
    })),
    groups: arr(m['groups']).map((g) => ({ name: str(g['name']), count: Number(g['count']) || 0 })),
    groupColumn: str(m['group_column']),
    total: Number(m['total']) || 0,
    mapped: Number(m['mapped']) || 0,
    skipped: Number(m['skipped']) || 0
  };
}
