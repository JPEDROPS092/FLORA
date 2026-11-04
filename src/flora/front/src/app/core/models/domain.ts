export type ThemeMode = 'light' | 'dark';

export interface DataSourceInfo {
  mode: 'mock' | 'http';
  label: string;
  apiBaseUrl: string;
  mocked: boolean;
}

export interface PlotFigure {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
}

export interface ChartResult {
  status: 'ok' | 'error' | 'empty';
  figure?: PlotFigure;
  error?: string;
}

export interface Provenance {
  pipelineVersion: string;
  seed: number;
  parameters: { label: string; value: string }[];
  packages: { name: string; version: string }[];
  inputs: string[];
  history: { at: string; event: string }[];
}

export interface RecentAnalysis {
  id: string;
  name: string;
  kind: string;
  status: 'completed' | 'failed' | 'running';
  finishedAt: string;
  projectId: string;
  summary: string;
  provenance: Provenance;
}

export interface DashboardSnapshot {
  source: DataSourceInfo;
  studyId: string;
  studyName: string;
  marker: string;
  samples: number;
  asvs: number;
  groups: number;
  groupNames: string[];
  quality: {
    pass: number;
    warn: number;
    fail: number;
    meanReads: number;
    medianReads: number;
  };
  recent: RecentAnalysis[];
  alpha: ChartResult;
  pcoa: ChartResult;
  mocked: boolean;
  partial: boolean;
  note?: string;
  workdir?: string;
  status: string;
}

export interface DiagnosticEntry {
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR';
  message: string;
}

export interface ResearchProject {
  id: string;
  name: string;
  question: string;
  status: 'active' | 'archived' | 'draft';
  datasetName: string;
  marker: string;
  samples: number;
  asvs: number;
  groups: string[];
  analyses: { id: string; name: string; kind: string; status: string }[];
  results: { id: string; title: string; summary: string }[];
  updatedAt: string;
  mocked: boolean;
  /** empty → raw_downloaded → ingested. Only `ingested` projects can be analysed. */
  stage?: ProjectStage;
  synthetic?: boolean;
  active?: boolean;
  source?: { type: SyncSourceType; accession: string };
}

export type ProjectStage = 'empty' | 'raw_downloaded' | 'ingested';
export type SyncSourceType = 'synthetic' | 'mgnify' | 'sra' | 'emp';

export interface SyncSourceDraft {
  type: SyncSourceType;
  accession: string;
  params?: Record<string, string | number>;
}

export interface ExampleProject {
  id: string;
  name: string;
  question: string;
  description: string;
  biome: string;
  synthetic: boolean;
  /** false = accession not yet confirmed at the source. */
  verified: boolean;
  installable: boolean;
  source: SyncSourceDraft;
}

export type SyncStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface SyncJob {
  id: string;
  projectId: string;
  source: SyncSourceDraft;
  status: SyncStatus;
  progress: number;
  message: string;
  error: string;
  log: string[];
  upToDate: boolean;
}

export interface ProjectDraft {
  name: string;
  question: string;
}

export interface IngestRequest {
  metadataPath: string;
  asvPath: string;
  taxonomyPath: string;
  sampleColumn: string;
  groupColumn: string;
  wideFormat: boolean;
  metadataColumns?: string[];
}

export interface SampleQcRow {
  sampleId: string;
  metadataId: string;
  group: string | null;
  inMetadata: boolean;
  inAsv: boolean;
  reads: number | null;
  status: 'pass' | 'warn' | 'fail';
  issues: string[];
}

export interface IngestPreview {
  columns: string[];
  rows: SampleQcRow[];
  summary: {
    matched: number;
    metadataOnly: number;
    asvOnly: number;
    lowDepth: number;
    totalAsvs: number;
  };
  histogram: PlotFigure;
  mocked: boolean;
  warnings: string[];
}

export interface IngestStepResult {
  step: 'metadata' | 'asv' | 'taxonomy';
  success: boolean;
  detail?: string;
  error?: string;
}

export interface IngestOutcome {
  success: boolean;
  steps: IngestStepResult[];
  error?: string;
}

export interface PipelineStage {
  id: string;
  tool: string;
  name: string;
  detail: string;
  status: 'complete' | 'attention' | 'pending' | 'failed';
}

export interface NormalizationConfig {
  rarefactionDepth: number;
  method: 'clr' | 'tss' | 'none';
  minPrevalence: number;
  minAbundance: number;
}

export interface PipelineSnapshot {
  stages: PipelineStage[];
  normalization: NormalizationConfig;
  qc: IngestPreview;
  ingested: boolean;
  mocked: boolean;
  note?: string;
}

export type ExplorerView = 'pcoa' | 'alpha' | 'beta' | 'taxonomy' | 'relations' | 'data' | 'qc' | 'rarefaction' | 'stats';

export interface ExplorationQuery {
  /** Metadata column the groups come from (e.g. `biome`). */
  groupBy: string;
  /** Values of that column to keep. */
  groups: string[];
  metric: 'shannon' | 'simpson' | 'observed' | 'chao1';
  normalize: 'clr' | 'tss' | 'none';
  rank: 'phylum' | 'class' | 'order' | 'family' | 'genus';
  distance: 'braycurtis' | 'jaccard';
  topN: number;
}

export interface TaxonNode {
  key: string;
  label: string;
  rank: string;
  abundance: number;
  children?: TaxonNode[];
}

export interface GroupComparison {
  group: string;
  n: number;
  shannonMean: number;
  shannonSd: number;
  observedMean: number;
}

export interface DifferentialTaxon {
  taxon: string;
  rank: 'phylum' | 'genus';
  log2FoldChange: number;
  pValue: number;
  qValue: number;
  higherIn: string;
  contrast: string;
}

export interface ExplorationBundle {
  query: ExplorationQuery;
  pcoa: ChartResult;
  alpha: ChartResult;
  beta: ChartResult;
  taxonomy: ChartResult;
  relations: ChartResult;
  tree: TaxonNode[];
  comparisons: GroupComparison[];
  differential: DifferentialTaxon[];
  distanceNote: string;
  sampleCount: number;
  asvCount: number;
  mocked: boolean;
  note?: string;
}

export interface ClusterRequest {
  method: 'kmeans' | 'hdbscan';
  nClusters: number;
  normalize: 'clr' | 'tss' | 'none';
  seed: number;
}

export interface ClusterSummary {
  success: boolean;
  error?: string;
  method: string;
  nClusters: number;
  silhouette: number | null;
  daviesBouldin: number | null;
  noiseFraction: number | null;
  mocked: boolean;
}

export interface TrainRequest {
  model: 'random_forest' | 'xgboost';
  targetColumn: string;
  trainFilter: string;
  testFilter: string;
  normalize: 'clr' | 'tss' | 'none';
  cvFolds: number;
  seed: number;
}

export interface MlExperiment {
  id: string;
  name: string;
  model: string;
  status: 'completed' | 'failed';
  createdAt: string;
  accuracy: number;
  f1Macro: number;
  rocAuc: number | null;
  cvAccuracyMean: number;
  trainN: number;
  testN: number;
  features: number;
  importanceKind: 'shap' | 'impurity';
  confusion: ChartResult;
  roc: ChartResult;
  importance: ChartResult;
  labels: string[];
  matrix: number[][];
  importances: { feature: string; value: number }[];
  config: { label: string; value: string }[];
  limitations: string[];
  provenance: Provenance;
  error?: string;
  mocked: boolean;
}

export interface ModelComparisonRow {
  model: string;
  experimentId: string;
  accuracy: number;
  f1Macro: number;
  rocAuc: number | null;
  cvAccuracyMean: number;
  seed: number;
  features: number;
}

export interface ReportSection {
  id: string;
  title: string;
  narrative: string;
  included: boolean;
  figure: 'alpha' | 'pcoa' | 'taxonomy' | 'beta' | 'confusion' | 'shap' | null;
  table: { columns: string[]; rows: string[][] } | null;
}

export interface ReportDraft {
  title: string;
  projectId: string;
  mocked: boolean;
  sections: ReportSection[];
  parameters: { label: string; value: string }[];
  figures: Partial<Record<NonNullable<ReportSection['figure']>, PlotFigure>>;
  note?: string;
}

export interface ExportRequest {
  title: string;
  format: 'html' | 'pdf' | 'both';
  sections: ReportSection[];
  groupBy: string;
}

export interface ScientificExport {
  success: boolean;
  error?: string;
  title: string;
  html: string;
  pdfBase64: string;
  previewUrl?: string;
  warnings: string[];
  mocked: boolean;
}

export interface DownloadRequest {
  source: 'synthetic' | 'emp' | 'mgnify' | 'sra';
  outputDir: string;
  samples?: number;
  features?: number;
  seed?: number;
  studyAccession?: string;
  biome?: string;
  maxSamples?: number;
  accessions?: string[];
}

/** A dataset already on disk (downloaded, uploaded or in the active project) that the pipeline can ingest. */
export interface LocalDataset {
  id: string;
  label: string;
  path: string;
  origin: 'project' | 'workdir' | 'upload';
  files: { metadata?: string; asv?: string; taxonomy?: string };
  missing: string[];
  complete: boolean;
  rawReadsOnly: boolean;
  samples: number;
  columns: string[];
  modified: string;
}

export type UploadKind = 'metadata' | 'asv' | 'taxonomy';

export type LibrarySource = 'curated' | 'mgnify' | 'ena';

/** A public study listed in the library; `accession` is the code used to download it. */
export interface StudyEntry {
  source: string;
  accession: string;
  title: string;
  description: string;
  biome: string;
  samples: number;
  centre: string;
  bioproject: string;
  secondary: string;
  updated: string;
  url: string;
  origin: 'curated' | 'live';
  importable: boolean;
}

export interface DownloadJob {
  id: string;
  source: string;
  status: 'ready' | 'queued' | 'failed' | 'completed';
  detail: string;
  artifacts: { label: string; path: string }[];
  mocked: boolean;
  createdAt: string;
}

export interface CatalogFile {
  kind: string;
  label: string;
  url: string;
  size: number | null;
}

/** One curated dataset. Text fields other than the official title are Portuguese. */
export type LocalState = 'ready' | 'metadata_only' | 'partial' | 'none';

export interface CatalogEntry {
  /** What is on disk for this study: complete tables, metadata only, or nothing. */
  localState: LocalState;
  id: string;
  title: string;
  titlePt: string;
  description: string;
  source: string;
  accession: string;
  biome: string;
  biomeLabel: string;
  host: string;
  hostLabel: string;
  region: string;
  regionLabel: string;
  country: string;
  lat: number | null;
  lon: number | null;
  nSamples: number;
  nRuns: number | null;
  seqType: string;
  marker: string;
  markerRegion: string;
  platform: string;
  license: string;
  licenseNote: string;
  citation: string;
  citationDoi: string;
  bioproject: string;
  secondary: string;
  centre: string;
  url: string;
  verifiedAt: string;
  importable: boolean;
  highlight: string;
  tags: string[];
  downloadNote: string;
  files: CatalogFile[];
}

export interface CatalogQuery {
  q?: string;
  biome?: string;
  host?: string;
  region?: string;
  seqType?: string;
  amazonia?: boolean;
}

export interface MetadataPreview {
  source: string;
  accession: string;
  columns: string[];
  rows: Record<string, string>[];
  rowCount: number;
  truncated: boolean;
}

export interface GroupColumn {
  name: string;
  values: { value: string; count: number }[];
}

/** What the loaded dataset contains and how it can be grouped. */
export interface ExploreSchema {
  project: { id: string; name: string; stage: string; question: string; synthetic: boolean } | null;
  counts: { samples: number; asvs: number; observations: number; taxa: number };
  reads: { min: number; median: number; max: number } | null;
  groupColumns: GroupColumn[];
  mocked: boolean;
}

export type DatasetTable = 'samples' | 'features' | 'taxonomy';

export interface TablePage {
  name: DatasetTable;
  columns: string[];
  rows: (string | number)[][];
  total: number;
  offset: number;
}

export interface MapPoint {
  lat: number;
  lon: number;
  group: string;
  /** Samples collected at this exact spot. */
  n: number;
  ids: string[];
}

/** Sample locations of a dataset; `available` is false when the file has no usable coordinates. */
export interface SampleMap {
  available: boolean;
  reason: '' | 'not_downloaded' | 'no_coordinates' | 'no_valid_coordinates';
  points: MapPoint[];
  groups: { name: string; count: number }[];
  groupColumn: string;
  total: number;
  mapped: number;
  skipped: number;
}

export type AnalysisKind = 'qc' | 'rarefaction' | 'alpha_stats' | 'beta_stats' | 'volcano' | 'mixs';

export interface EngineInfo {
  id: string;
  name: string;
  kind: string;
  capabilities: string[];
  available: boolean;
  version: string;
  install: string;
}

export interface EngineJob {
  id: string;
  kind: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  step: string;
  steps: string[];
  log: string[];
  error: string;
  artifacts: Record<string, string>;
  createdAt: string;
}

/** Which project and database file the API is using right now. */
export interface WorkspaceInfo {
  project: { id: string; name: string; stage: string } | null;
  dbPath: string;
  persistent: boolean;
}

export interface TreeStatus {
  present: boolean;
  valid?: boolean;
  tips: number;
  overlap: number;
  features: number;
  error?: string;
}

/** Result table of an R workflow (ALDEx2, ANCOM-BC2, vegan) plus an optional volcano plot. */
export interface EngineResults {
  kind: string;
  columns: string[];
  rows: Record<string, string>[];
  total: number;
  plot: { data: Record<string, unknown>[]; layout: Record<string, unknown> } | null;
}

/** A conda environment found on disk that contains QIIME 2 and/or R's DADA2. */
export interface EngineEnvironment {
  name: string;
  prefix: string;
  qiime: string | null;
  python: string | null;
  rscript: string | null;
  qiime2PythonApi: boolean;
  dada2RPackage: boolean;
}

/** Executables FLORA uses for QIIME 2 (`qiime`, `python`) and R (`rscript`); empty means "whatever is on PATH". */
export interface EngineConfig {
  qiime?: string;
  python?: string;
  rscript?: string;
}

export interface EngineEnvironments {
  environments: EngineEnvironment[];
  config: EngineConfig;
  effective: EngineConfig;
}
