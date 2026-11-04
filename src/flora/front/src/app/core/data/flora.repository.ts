import {
  DashboardSnapshot,
  DataSourceInfo,
  DiagnosticEntry,
  CatalogEntry,
  CatalogQuery,
  DownloadJob,
  DownloadRequest,
  LibrarySource,
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

  abstract dashboard(): Promise<DashboardSnapshot>;
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
  abstract datasets(): Promise<LocalDataset[]>;
  abstract uploadFile(file: File, kind: UploadKind): Promise<{ path: string; columns: string[] }>;
  abstract searchLibrary(source: LibrarySource, query: string): Promise<StudyEntry[]>;
  abstract resolveRuns(studyAccession: string): Promise<string[]>;
  abstract catalog(query: CatalogQuery): Promise<CatalogEntry[]>;
  abstract datasetMetadata(source: string, accession: string): Promise<MetadataPreview>;
  abstract downloadDataset(source: string, accession: string): Promise<DownloadJob>;
}
