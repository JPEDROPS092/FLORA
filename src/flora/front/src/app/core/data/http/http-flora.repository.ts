import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../../environments/environment';
import { buildReportFiles } from '../../export/report-document';
import {
  ClusterRequest,
  ClusterSummary,
  DashboardSnapshot,
  DataSourceInfo,
  DiagnosticEntry,
  DownloadJob,
  DownloadRequest,
  ExplorationBundle,
  ExplorationQuery,
  ExportRequest,
  IngestOutcome,
  IngestPreview,
  IngestRequest,
  IngestStepResult,
  MlExperiment,
  ModelComparisonRow,
  NormalizationConfig,
  PipelineSnapshot,
  PlotFigure,
  ProjectDraft,
  Provenance,
  ReportDraft,
  ResearchProject,
  ScientificExport,
  TrainRequest
} from '../../models/domain';
import { FloraRepository } from '../flora.repository';
import { aggregateIngest } from '../ingest-aggregate';
import { settleChart } from '../settle-chart';
import { t } from '../../i18n/i18n';

interface StatusResponse {
  success: boolean;
  error?: string;
  status?: string;
  workdir?: string;
  frontend?: { mode?: string };
  tables?: Record<string, number>;
}

interface LogResponse {
  success: boolean;
  error?: string;
  lines?: string[];
}

interface IngestResponse {
  success: boolean;
  error?: string;
  samples_ingested?: number;
  observations_ingested?: number;
  taxonomy_rows?: number;
}

interface DiversityResponse {
  success: boolean;
  error?: string;
  metrics?: string[];
  samples?: number;
  preview?: Record<string, unknown>[];
}

interface MatrixResponse {
  success: boolean;
  error?: string;
  n_samples?: number;
  n_features?: number;
  normalize?: string;
}

interface ClassifyResponse {
  success: boolean;
  error?: string;
  model?: string;
  accuracy?: number;
  f1_macro?: number;
  roc_auc?: number | null;
  cv_accuracy_mean?: number;
  top_features?: Record<string, unknown>[];
  classification_report?: string;
}

interface ClusterResponse {
  success: boolean;
  error?: string;
  method?: string;
  n_clusters?: number;
  silhouette?: number;
  davies_bouldin?: number;
  noise_fraction?: number;
}

interface ReportResponse {
  success: boolean;
  error?: string;
  report_path?: string;
  report_preview_url?: string;
  pdf_path?: string | null;
  warnings?: string[];
}

interface DownloadResponse {
  success: boolean;
  error?: string;
  manifest?: string;
  output_dir?: string;
  asv_table?: string;
  taxonomy?: string;
  metadata?: string;
  accessions?: string[];
}

interface PlotResponse {
  success: boolean;
  error?: string;
  plot?: { data?: Record<string, unknown>[]; layout?: Record<string, unknown> };
}

const EMPTY_PROVENANCE: Provenance = {
  pipelineVersion: 'API Python',
  seed: 0,
  parameters: [],
  packages: [],
  inputs: [],
  history: [{ at: '', event: t('A API atual não devolve histórico de execução.') }]
};

/**
 * Skeleton over the existing flora ui endpoints.
 * Screens that need projects, per-sample QC or SHAP degrade with an explicit note.
 */
export class HttpFloraRepository extends FloraRepository {
  readonly source: DataSourceInfo = {
    mode: 'http',
    label: environment.apiBaseUrl || 'mesma origem',
    apiBaseUrl: environment.apiBaseUrl,
    mocked: false
  };

  private projectStore: ResearchProject[] = [];
  private experimentStore: MlExperiment[] = [];
  private jobs: DownloadJob[] = [];
  private normalization: NormalizationConfig = {
    rarefactionDepth: 10000,
    method: 'clr',
    minPrevalence: 0.05,
    minAbundance: 0
  };

  constructor(private readonly http: HttpClient) {
    super();
  }

  async dashboard(): Promise<DashboardSnapshot> {
    const status = await this.send<StatusResponse>('GET', '/api/status');
    const tables = status.tables ?? {};
    const samples = numberFrom(tables, ['samples', 'metadata']);
    const asvs = numberFrom(tables, ['taxonomy', 'asv_table', 'features']);
    const alpha = await settleChart(() => this.loadPlot('/api/viz/alpha', { metric: 'shannon', group_by: 'biome' }));
    const pcoa = await settleChart(() => this.loadPlot('/api/viz/pcoa', { normalize: 'clr', color_by: 'biome' }));
    return {
      source: this.source,
      studyId: 'workspace',
      studyName: 'Workspace atual',
      marker: '16S',
      samples,
      asvs,
      groups: 0,
      groupNames: [],
      quality: { pass: samples, warn: 0, fail: 0, meanReads: 0, medianReads: 0 },
      recent: [],
      alpha,
      pcoa,
      mocked: false,
      partial: true,
      note: t('Contagens vindas de /api/status. Qualidade por amostra e projetos não têm endpoint ainda.'),
      status: status.status ?? 'unknown',
      workdir: status.workdir
    };
  }

  async diagnostics(lines = 120): Promise<DiagnosticEntry[]> {
    const payload = await this.send<LogResponse>('GET', '/api/logs', { params: { n: lines } });
    return (payload.lines ?? []).map((line) => ({ timestamp: '', level: 'INFO' as const, message: line }));
  }

  async projects(): Promise<ResearchProject[]> {
    const status = await this.dashboard();
    const current: ResearchProject = {
      id: 'workspace',
      name: 'Workspace atual',
      question: t('Pergunta ainda não persistida na API.'),
      status: 'active',
      datasetName: status.workdir ?? 'workdir',
      marker: '16S',
      samples: status.samples,
      asvs: status.asvs,
      groups: [],
      analyses: [],
      results: [],
      updatedAt: '',
      mocked: false
    };
    return [current, ...this.projectStore];
  }

  async saveProject(draft: ProjectDraft): Promise<ResearchProject> {
    const project: ResearchProject = {
      id: `local-${this.projectStore.length + 1}`,
      name: draft.name.trim(),
      question: draft.question.trim(),
      status: 'draft',
      datasetName: t('Somente nesta sessão'),
      marker: '16S',
      samples: 0,
      asvs: 0,
      groups: [],
      analyses: [],
      results: [],
      updatedAt: new Date().toISOString(),
      mocked: false
    };
    this.projectStore = [project, ...this.projectStore];
    return project;
  }

  async pipeline(): Promise<PipelineSnapshot> {
    const status = await this.send<StatusResponse>('GET', '/api/status');
    const tables = status.tables ?? {};
    const hasSamples = numberFrom(tables, ['samples']) > 0;
    return {
      ingested: hasSamples,
      mocked: false,
      normalization: { ...this.normalization },
      note: t('Etapas QIIME2/DADA2 são acompanhamento local. A API expõe ingestão, diversidade e matriz.'),
      qc: emptyPreview(t('O QC por amostra chega depois do POST /api/ingest. A API não lista erros por amostra.')),
      stages: [
        { id: 'import', tool: 'QIIME2', name: 'Importar', detail: 'Fora deste esqueleto', status: 'pending' },
        { id: 'cutadapt', tool: 'QIIME2', name: 'Primers', detail: 'Fora deste esqueleto', status: 'pending' },
        { id: 'dada2', tool: 'DADA2', name: 'Denoise', detail: 'Fora deste esqueleto', status: 'pending' },
        { id: 'taxonomy', tool: 'FLORA', name: 'Taxonomia', detail: hasSamples ? t('Tabela presente') : t('Aguardando ingestão'), status: hasSamples ? 'complete' : 'pending' },
        { id: 'table', tool: 'FLORA', name: t('Tabela'), detail: t('{n} amostras', { n: numberFrom(tables, ['samples']) }), status: hasSamples ? 'attention' : 'pending' },
        { id: 'norm', tool: 'FLORA', name: t('Normalizar'), detail: this.normalization.method.toUpperCase(), status: hasSamples ? 'complete' : 'pending' }
      ]
    };
  }

  async previewIngest(request: IngestRequest): Promise<IngestPreview> {
    const warnings = [t('Validação estrutural local. A correspondência de amostras só é confirmada pelos endpoints de ingestão.')];
    if (request.metadataColumns?.length && !request.metadataColumns.includes(request.sampleColumn)) {
      warnings.push(t('A coluna "{col}" não está no arquivo enviado.', { col: request.sampleColumn }));
    }
    return {
      ...emptyPreview(warnings[0]),
      columns: request.metadataColumns ?? [],
      warnings
    };
  }

  async confirmIngest(request: IngestRequest): Promise<IngestOutcome> {
    const steps = await Promise.all([
      this.step('metadata', '/api/ingest/metadata', {
        path: request.metadataPath,
        sample_col: request.sampleColumn
      }),
      this.step('asv', '/api/ingest/asv', {
        path: request.asvPath,
        wide_format: request.wideFormat
      }),
      this.step('taxonomy', '/api/ingest/taxonomy', { path: request.taxonomyPath })
    ]);
    return aggregateIngest(steps);
  }

  async applyNormalization(config: NormalizationConfig): Promise<PipelineSnapshot> {
    this.normalization = { ...config };
    try {
      await this.send<MatrixResponse>('GET', '/api/feature_matrix', {
        params: {
          normalize: config.method,
          min_prevalence: config.minPrevalence
        }
      });
    } catch (error) {
      const snapshot = await this.pipeline();
      snapshot.note = error instanceof Error ? error.message : t('Falha ao pedir a matriz.');
      snapshot.stages = snapshot.stages.map((stage) =>
        stage.id === 'norm' ? { ...stage, status: 'failed', detail: snapshot.note ?? stage.detail } : stage
      );
      return snapshot;
    }
    return this.pipeline();
  }

  async exploration(query: ExplorationQuery): Promise<ExplorationBundle> {
    const group = query.groups[0] ?? 'biome';
    const [pcoa, alpha, beta, taxonomy, relations] = await Promise.all([
      settleChart(() => this.loadPlot('/api/viz/pcoa', { normalize: query.normalize, color_by: group })),
      settleChart(() => this.loadPlot('/api/viz/alpha', { metric: apiMetric(query.metric), group_by: group })),
      settleChart(() =>
        this.loadPlot('/api/viz/beta_heatmap', {
          normalize: query.normalize,
          metric: query.distance === 'jaccard' ? 'jaccard' : 'bray_curtis',
          max_samples: 60
        })
      ),
      settleChart(() => this.loadPlot('/api/viz/taxonomy', { level: query.rank, group_by: group })),
      settleChart(() => this.loadPlot('/api/viz/network', { level: 'genus', top_n: query.topN, threshold: 0.35 }))
    ]);
    let note = t('Figuras pedidas em separado a /api/viz. A árvore taxonômica estruturada e os testes diferenciais não têm endpoint.');
    try {
      await this.send<DiversityResponse>('POST', '/api/diversity', {
        body: { sampling_depth: this.normalization.rarefactionDepth, metrics: ['shannon', 'observed_features', 'chao1'] }
      });
    } catch (error) {
      note = `${note} Diversidade: ${error instanceof Error ? error.message : 'falhou'}.`;
    }
    return {
      query,
      pcoa,
      alpha,
      beta,
      taxonomy,
      relations,
      tree: [],
      comparisons: [],
      differential: [],
      distanceNote: t('Métrica pedida ao endpoint /api/viz/beta_heatmap.'),
      sampleCount: 0,
      asvCount: 0,
      mocked: false,
      note
    };
  }

  async experiments(): Promise<MlExperiment[]> {
    return this.experimentStore.map((experiment) => ({ ...experiment }));
  }

  async trainModel(request: TrainRequest): Promise<MlExperiment> {
    try {
      const response = await this.send<ClassifyResponse>('POST', '/api/ml/classify', {
        body: {
          model: request.model,
          target_column: request.targetColumn,
          train_filter: request.trainFilter,
          test_filter: request.testFilter,
          normalize: request.normalize === 'none' ? null : request.normalize,
          cv_folds: request.cvFolds
        }
      });
      if (!response.success) {
        throw new Error(response.error ?? t('Classificação recusada.'));
      }
      const importances = (response.top_features ?? []).map((row, index) => ({
        feature: String(row['feature'] ?? row['feature_id'] ?? `feature_${index + 1}`),
        value: Number(row['importance'] ?? row['value'] ?? 0)
      }));
      const experiment: MlExperiment = {
        id: `http-${Date.now()}`,
        name: response.model ?? request.model,
        model: response.model ?? request.model,
        status: 'completed',
        createdAt: new Date().toISOString(),
        accuracy: response.accuracy ?? 0,
        f1Macro: response.f1_macro ?? 0,
        rocAuc: response.roc_auc ?? null,
        cvAccuracyMean: response.cv_accuracy_mean ?? 0,
        trainN: 0,
        testN: 0,
        features: importances.length,
        importanceKind: 'impurity',
        confusion: { status: 'empty', error: t('A API não devolve a matriz de confusão.') },
        roc: { status: 'empty', error: t('A API não devolve a curva ROC.') },
        importance:
          importances.length > 0
            ? {
                status: 'ok',
                figure: {
                  data: [{ type: 'bar', orientation: 'h', x: importances.map((item) => item.value), y: importances.map((item) => item.feature) }],
                  layout: { margin: { l: 120, t: 16, r: 16, b: 40 }, showlegend: false }
                }
              }
            : { status: 'empty', error: t('Sem importâncias na resposta.') },
        labels: [],
        matrix: [],
        importances,
        config: [
          { label: 'Modelo', value: request.model },
          { label: 'Alvo', value: request.targetColumn },
          { label: 'Treino', value: request.trainFilter },
          { label: 'Teste', value: request.testFilter },
          { label: 'CV', value: String(request.cvFolds) },
          { label: 'Seed', value: String(request.seed) }
        ],
        limitations: [
          t('O endpoint /api/ml/classify devolve métricas e top_features, não SHAP, ROC nem matriz de confusão.'),
          response.classification_report ? t('Há um classification_report textual na resposta.') : t('Sem classification_report.')
        ],
        provenance: {
          ...EMPTY_PROVENANCE,
          seed: request.seed,
          parameters: [{ label: 'Modelo', value: request.model }]
        },
        mocked: false
      };
      this.experimentStore = [experiment, ...this.experimentStore];
      return experiment;
    } catch (error) {
      const message = error instanceof Error ? error.message : t('Falha no treino.');
      const failed: MlExperiment = {
        id: `http-failed-${Date.now()}`,
        name: request.model,
        model: request.model,
        status: 'failed',
        createdAt: new Date().toISOString(),
        accuracy: 0,
        f1Macro: 0,
        rocAuc: null,
        cvAccuracyMean: 0,
        trainN: 0,
        testN: 0,
        features: 0,
        importanceKind: 'impurity',
        confusion: { status: 'error', error: message },
        roc: { status: 'error', error: message },
        importance: { status: 'error', error: message },
        labels: [],
        matrix: [],
        importances: [],
        config: [],
        limitations: [],
        provenance: EMPTY_PROVENANCE,
        error: message,
        mocked: false
      };
      this.experimentStore = [failed, ...this.experimentStore];
      return failed;
    }
  }

  async clusterSamples(request: ClusterRequest): Promise<ClusterSummary> {
    try {
      const response = await this.send<ClusterResponse>('POST', '/api/ml/cluster', {
        body: {
          method: request.method,
          n_clusters: request.nClusters,
          normalize: request.normalize
        }
      });
      if (!response.success) {
        return {
          success: false,
          error: response.error ?? 'Agrupamento recusado.',
          method: request.method,
          nClusters: request.nClusters,
          silhouette: null,
          daviesBouldin: null,
          noiseFraction: null,
          mocked: false
        };
      }
      return {
        success: true,
        method: response.method ?? request.method,
        nClusters: response.n_clusters ?? request.nClusters,
        silhouette: response.silhouette ?? null,
        daviesBouldin: response.davies_bouldin ?? null,
        noiseFraction: response.noise_fraction ?? null,
        mocked: false
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : t('Falha no agrupamento.'),
        method: request.method,
        nClusters: request.nClusters,
        silhouette: null,
        daviesBouldin: null,
        noiseFraction: null,
        mocked: false
      };
    }
  }

  async comparison(): Promise<ModelComparisonRow[]> {
    return this.experimentStore
      .filter((experiment) => experiment.status === 'completed')
      .map((experiment) => ({
        model: experiment.model,
        experimentId: experiment.id,
        accuracy: experiment.accuracy,
        f1Macro: experiment.f1Macro,
        rocAuc: experiment.rocAuc,
        cvAccuracyMean: experiment.cvAccuracyMean,
        seed: experiment.provenance.seed,
        features: experiment.features
      }));
  }

  async reportDraft(): Promise<ReportDraft> {
    const status = await this.dashboard();
    return {
      title: t('Relatório FLORA'),
      projectId: 'workspace',
      mocked: false,
      note: t('O HTML/PDF local usa o texto editado. O backend gera outro artefato em POST /api/report.'),
      parameters: [
        { label: 'Workdir', value: status.workdir ?? 'n/d' },
        { label: t('Amostras'), value: String(status.samples) },
        { label: 'ASVs', value: String(status.asvs) }
      ],
      figures: {},
      sections: [
        {
          id: 'summary',
          title: 'Resumo',
          included: true,
          figure: null,
          narrative: t('Descreva o desenho do estudo. Os números do workspace vêm de /api/status.'),
          table: {
            columns: ['Campo', 'Valor'],
            rows: [
              [t('Amostras'), String(status.samples)],
              ['ASVs', String(status.asvs)],
              ['Status', status.status]
            ]
          }
        },
        {
          id: 'methods',
          title: t('Métodos'),
          included: true,
          figure: null,
          narrative: t('Registre rarefação, transformação, distância e modelo. A API ainda não devolve esses parâmetros.'),
          table: null
        }
      ]
    };
  }

  async exportReport(request: ExportRequest): Promise<ScientificExport> {
    const draft = await this.reportDraft();
    const files = buildReportFiles({
      title: request.title,
      sections: request.sections,
      parameters: draft.parameters,
      figures: draft.figures,
      mocked: false
    });
    const warnings: string[] = [];
    let previewUrl: string | undefined;
    try {
      const response = await this.send<ReportResponse>('POST', '/api/report', {
        body: {
          title: request.title,
          output_path: 'results/report.html',
          output_format: request.format === 'both' ? 'both' : request.format,
          pdf_path: 'results/report.pdf',
          group_by: request.groupBy || null
        }
      });
      if (!response.success) {
        warnings.push(response.error ?? t('POST /api/report recusou o relatório.'));
      } else {
        previewUrl = response.report_preview_url;
        warnings.push(...(response.warnings ?? []));
        if (response.report_path) {
          warnings.push(t('HTML do backend: {path}', { path: response.report_path }));
        }
        if (response.pdf_path) {
          warnings.push(t('PDF do backend: {path}', { path: response.pdf_path }));
        }
      }
    } catch (error) {
      warnings.push(error instanceof Error ? error.message : t('Falha em POST /api/report.'));
    }
    return {
      success: true,
      title: request.title,
      html: files.html,
      pdfBase64: files.pdfBase64,
      previewUrl,
      warnings,
      mocked: false
    };
  }

  async downloads(): Promise<DownloadJob[]> {
    return this.jobs.map((job) => ({ ...job }));
  }

  async requestDownload(request: DownloadRequest): Promise<DownloadJob> {
    const path =
      request.source === 'synthetic'
        ? '/api/download/synthetic'
        : request.source === 'emp'
          ? '/api/download/emp'
          : request.source === 'mgnify'
            ? '/api/download/mgnify'
            : '/api/download/sra';
    const body =
      request.source === 'synthetic'
        ? { output_dir: request.outputDir, samples: request.samples ?? 80, features: request.features ?? 200, seed: request.seed ?? 42 }
        : request.source === 'emp'
          ? { output_dir: request.outputDir, biome_filter: request.biome, max_samples: request.maxSamples ?? 200 }
          : request.source === 'mgnify'
            ? {
                output_dir: request.outputDir,
                study_accession: request.studyAccession,
                biome: request.biome,
                max_samples: request.maxSamples ?? 20
              }
            : { output_dir: request.outputDir, accessions: request.accessions ?? [] };
    try {
      const response = await this.send<DownloadResponse>('POST', path, { body });
      if (!response.success) {
        throw new Error(response.error ?? 'Download recusado.');
      }
      const artifacts = [
        artifact('Manifesto', response.manifest),
        artifact('ASV', response.asv_table),
        artifact('Taxonomia', response.taxonomy),
        artifact('Metadata', response.metadata)
      ].filter((item): item is { label: string; path: string } => item !== null);
      const job: DownloadJob = {
        id: `http-${Date.now()}`,
        source: request.source,
        status: 'completed',
        detail: response.output_dir ?? request.outputDir,
        artifacts,
        mocked: false,
        createdAt: new Date().toISOString()
      };
      this.jobs = [job, ...this.jobs];
      return job;
    } catch (error) {
      const job: DownloadJob = {
        id: `http-failed-${Date.now()}`,
        source: request.source,
        status: 'failed',
        detail: error instanceof Error ? error.message : t('Falha no download.'),
        artifacts: [],
        mocked: false,
        createdAt: new Date().toISOString()
      };
      this.jobs = [job, ...this.jobs];
      return job;
    }
  }

  private async step(step: IngestStepResult['step'], path: string, body: unknown): Promise<IngestStepResult> {
    try {
      const response = await this.send<IngestResponse>('POST', path, { body });
      if (!response.success) {
        return { step, success: false, error: response.error ?? t('A API recusou a etapa.') };
      }
      const count = response.samples_ingested ?? response.observations_ingested ?? response.taxonomy_rows;
      return { step, success: true, detail: count !== undefined ? `${count} registros` : 'ok' };
    } catch (error) {
      return { step, success: false, error: error instanceof Error ? error.message : t('Falha na etapa.') };
    }
  }

  private async loadPlot(path: string, params: Record<string, string | number | null | undefined>): Promise<PlotFigure | null> {
    const response = await this.send<PlotResponse>('GET', path, { params });
    if (!response.success) {
      throw new Error(response.error ?? `Falha em ${path}`);
    }
    if (!response.plot?.data?.length) {
      return null;
    }
    return { data: response.plot.data, layout: response.plot.layout ?? {} };
  }

  private async send<T>(
    method: 'GET' | 'POST',
    path: string,
    options?: { body?: unknown; params?: Record<string, string | number | boolean | null | undefined> }
  ): Promise<T> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(options?.params ?? {})) {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    }
    try {
      return await firstValueFrom(
        this.http.request<T>(method, `${environment.apiBaseUrl}${path}`, {
          body: options?.body,
          params
        })
      );
    } catch (error) {
      if (error instanceof HttpErrorResponse) {
        const payload = error.error;
        if (payload && typeof payload === 'object' && 'error' in payload && typeof payload.error === 'string') {
          throw new Error(payload.error);
        }
        throw new Error(error.message || `HTTP ${error.status}`);
      }
      throw error instanceof Error ? error : new Error(t('Falha de rede'));
    }
  }
}

function numberFrom(tables: Record<string, number>, keys: string[]): number {
  for (const key of keys) {
    if (typeof tables[key] === 'number') {
      return tables[key];
    }
  }
  return 0;
}

function emptyPreview(warning: string): IngestPreview {
  return {
    columns: [],
    rows: [],
    summary: { matched: 0, metadataOnly: 0, asvOnly: 0, lowDepth: 0, totalAsvs: 0 },
    histogram: { data: [], layout: {} },
    mocked: false,
    warnings: [warning]
  };
}

function artifact(label: string, path: string | undefined): { label: string; path: string } | null {
  return path ? { label, path } : null;
}

function apiMetric(metric: ExplorationQuery['metric']): string {
  return metric === 'observed' ? 'observed_features' : metric;
}
