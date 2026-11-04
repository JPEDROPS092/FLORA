import {
  DashboardSnapshot,
  DataSourceInfo,
  DiagnosticEntry,
  CatalogEntry,
  CatalogQuery,
  DownloadJob,
  DownloadRequest,
  AnalysisKind,
  EngineConfig,
  EngineEnvironments,
  EngineInfo,
  EngineResults,
  TreeStatus,
  EngineJob,
  WorkspaceInfo,
  DatasetTable,
  ExploreSchema,
  TablePage,
  LibrarySource,
  SampleMap,
  LocalDataset,
  UploadKind,
  MetadataPreview,
  StudyEntry,
  ExplorationBundle,
  ExplorationQuery,
  ClusterRequest,
  ClusterSummary,
  ExportRequest,
  IngestOutcome,
  IngestPreview,
  IngestRequest,
  MlExperiment,
  ModelComparisonRow,
  NormalizationConfig,
  PipelineSnapshot,
  ExampleProject,
  ProjectDraft,
  SyncJob,
  SyncSourceDraft,
  ReportDraft,
  ResearchProject,
  ScientificExport
} from '../models/domain';

export abstract class FloraRepository {
  abstract readonly source: DataSourceInfo;

  abstract dashboard(groupBy?: string): Promise<DashboardSnapshot>;
  abstract diagnostics(lines?: number): Promise<DiagnosticEntry[]>;
  abstract projects(): Promise<ResearchProject[]>;
  abstract saveProject(draft: ProjectDraft): Promise<ResearchProject>;
  abstract examples(): Promise<ExampleProject[]>;
  /** Creates a project from an example and starts its sync job. */
  abstract installExample(id: string): Promise<{ project: ResearchProject; job: SyncJob }>;
  abstract startSync(projectId: string, source: SyncSourceDraft): Promise<SyncJob>;
  abstract syncJob(jobId: string): Promise<SyncJob>;
  abstract cancelSync(jobId: string): Promise<SyncJob>;
  abstract activateProject(projectId: string): Promise<void>;
  abstract deleteProject(id: string): Promise<void>;
  abstract pipeline(): Promise<PipelineSnapshot>;
  abstract previewIngest(request: IngestRequest): Promise<IngestPreview>;
  abstract confirmIngest(request: IngestRequest): Promise<IngestOutcome>;
  abstract applyNormalization(config: NormalizationConfig): Promise<PipelineSnapshot>;
  abstract exploration(query: ExplorationQuery): Promise<ExplorationBundle>;
  abstract experiments(): Promise<MlExperiment[]>;
  abstract trainModel(request: import('../models/domain').TrainRequest): Promise<MlExperiment>;
  abstract clusterSamples(request: ClusterRequest): Promise<ClusterSummary>;
  abstract comparison(): Promise<ModelComparisonRow[]>;
  abstract reportDraft(): Promise<ReportDraft>;
  abstract exportReport(request: ExportRequest): Promise<ScientificExport>;
  abstract downloads(): Promise<DownloadJob[]>;
  abstract requestDownload(request: DownloadRequest): Promise<DownloadJob>;
  /** Base URL of the API, to build file-download links ('' when mocked). */
  abstract readonly apiBase: string;
  abstract workspaceInfo(): Promise<WorkspaceInfo>;
  abstract analysis(kind: AnalysisKind, params: Record<string, string | number>): Promise<Record<string, unknown>>;
  abstract applyQc(body: Record<string, unknown>): Promise<Record<string, unknown>>;
  abstract clearProjectData(): Promise<void>;
  abstract computeDiversity(depth?: number | null): Promise<Record<string, unknown>>;
  abstract analysisSettings(): Promise<{ taxonomyDb: string; options: string[]; minReads: number | null }>;
  abstract saveTaxonomyDb(value: string): Promise<void>;
  abstract treeStatus(): Promise<TreeStatus>;
  abstract saveTree(newick: string): Promise<{ tips: number; overlap: number; features: number }>;
  abstract engineResults(id: string): Promise<EngineResults>;
  abstract engineEnvironments(): Promise<EngineEnvironments>;
  abstract saveEngineEnvironment(config: EngineConfig): Promise<EngineInfo[]>;
  abstract engines(fresh?: boolean): Promise<EngineInfo[]>;
  abstract runEngine(body: Record<string, unknown>): Promise<EngineJob>;
  abstract engineJobs(): Promise<EngineJob[]>;
  abstract cancelEngineJob(id: string): Promise<void>;
  abstract exploreSchema(): Promise<ExploreSchema>;
  abstract exploreTable(name: DatasetTable, query: string, offset: number, limit: number): Promise<TablePage>;
  abstract datasets(): Promise<LocalDataset[]>;
  abstract uploadFile(file: File, kind: UploadKind): Promise<{ path: string; columns: string[] }>;
  abstract searchLibrary(source: LibrarySource, query: string): Promise<StudyEntry[]>;
  abstract resolveRuns(studyAccession: string): Promise<string[]>;
  abstract catalog(query: CatalogQuery): Promise<CatalogEntry[]>;
  abstract datasetMap(source: string, accession: string): Promise<SampleMap>;
  abstract datasetMetadata(source: string, accession: string): Promise<MetadataPreview>;
  abstract downloadDataset(source: string, accession: string): Promise<DownloadJob>;
}
