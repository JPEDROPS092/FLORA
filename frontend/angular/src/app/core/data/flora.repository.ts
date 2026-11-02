import {
  DashboardSnapshot,
  DataSourceInfo,
  DiagnosticEntry,
  DownloadJob,
  DownloadRequest,
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
  ProjectDraft,
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
}
