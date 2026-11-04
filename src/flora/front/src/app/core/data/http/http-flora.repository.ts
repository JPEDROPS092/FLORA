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
  CatalogEntry,
  CatalogQuery,
  DownloadJob,
  DownloadRequest,
  LibrarySource,
  MetadataPreview,
  StudyEntry,
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
  PipelineStage,
  PlotFigure,
  ExampleProject,
  ProjectDraft,
  SyncJob,
  SyncSourceDraft,
  Provenance,
  ReportDraft,
  ResearchProject,
  ScientificExport,
  TrainRequest
} from '../../models/domain';
import { FloraRepository } from '../flora.repository';
import { aggregateIngest } from '../ingest-aggregate';
import { settleChart } from '../settle-chart';
import { LANG, t } from '../../i18n/i18n';
import { Raw, toCatalogEntry, toChart, toComparisons, toDifferential, toDownload, toMetadataPreview, toStudy, toExperiment, toPreview, toRecent, toSections, toTree, toFigure } from './mappers';

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

  private failedExperiments: MlExperiment[] = [];
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
    const [status, d] = await Promise.all([
      this.send<StatusResponse>('GET', '/api/status'),
      this.send<Raw>('GET', '/api/dashboard', { params: { lang: LANG, min_reads: this.normalization.rarefactionDepth } })
    ]);
    const groupBy = String(d['group_by'] ?? 'biome');
    const q = (d['quality'] ?? {}) as Raw;
    const alpha = await settleChart(() => this.loadPlot('/api/viz/alpha', { metric: 'shannon', group_by: groupBy }));
    const pcoa = await settleChart(() => this.loadPlot('/api/viz/pcoa', { normalize: 'clr', color_by: groupBy }));
    const samples = Number(d['samples'] ?? 0);
    return {
      source: this.source,
      studyId: String(d['study_id'] ?? 'workspace'),
      studyName: String(d['study_name'] ?? ''),
      marker: String(d['marker'] ?? '16S'),
      samples,
      asvs: Number(d['asvs'] ?? 0),
      groups: Number(d['groups'] ?? 0),
      groupNames: ((d['group_names'] as string[]) ?? []).map(String),
      quality: {
        pass: Number(q['pass'] ?? 0),
        warn: Number(q['warn'] ?? 0),
        fail: Number(q['fail'] ?? 0),
        meanReads: Number(q['mean_reads'] ?? 0),
        medianReads: Number(q['median_reads'] ?? 0)
      },
      recent: ((d['recent'] as unknown[]) ?? []).map(toRecent),
      alpha,
      pcoa,
      mocked: false,
      partial: false,
      status: status.status ?? String(d['status'] ?? 'unknown'),
      workdir: String(d['workdir'] ?? status.workdir ?? '')
    };
  }

  async diagnostics(lines = 120): Promise<DiagnosticEntry[]> {
    const payload = await this.send<LogResponse>('GET', '/api/logs', { params: { n: lines } });
    return (payload.lines ?? []).map((line) => ({ timestamp: '', level: 'INFO' as const, message: line }));
  }

  async projects(): Promise<ResearchProject[]> {
    const res = await this.send<{ projects: Record<string, unknown>[]; active: string }>('GET', '/api/projects');
    return (res.projects ?? []).map((p) => this.toProject(p, res.active));
  }

  async saveProject(draft: ProjectDraft): Promise<ResearchProject> {
    const res = await this.send<{ project: Record<string, unknown> }>('POST', '/api/projects', {
      body: { name: draft.name.trim(), question: draft.question.trim() }
    });
    return this.toProject(res.project, '');
  }

  async examples(): Promise<ExampleProject[]> {
    const res = await this.send<{ examples: Record<string, unknown>[] }>('GET', '/api/examples');
    return (res.examples ?? []).map((e) => ({
      id: String(e['id']), name: String(e['name']), question: String(e['question']), description: String(e['description']),
      biome: String(e['biome']), synthetic: !!e['synthetic'], verified: !!e['verified'], installable: !!e['installable'],
      source: this.toSource(e['source'])
    }));
  }

  async installExample(id: string): Promise<{ project: ResearchProject; job: SyncJob }> {
    const res = await this.send<{ project: Record<string, unknown>; job: Record<string, unknown> }>('POST', '/api/examples/install', { body: { id } });
    return { project: this.toProject(res.project, String(res.project['id'])), job: this.toJob(res.job) };
  }

  async startSync(projectId: string, source: SyncSourceDraft): Promise<SyncJob> {
    const res = await this.send<{ job: Record<string, unknown> }>('POST', '/api/projects/sync', {
      body: { id: projectId, source: { type: source.type, accession: source.accession, params: source.params ?? {} } }
    });
    return this.toJob(res.job);
  }

  async syncJob(jobId: string): Promise<SyncJob> {
    const res = await this.send<{ job: Record<string, unknown> }>('GET', '/api/sync-jobs', { params: { id: jobId } });
    return this.toJob(res.job);
  }

  async cancelSync(jobId: string): Promise<SyncJob> {
    const res = await this.send<{ job: Record<string, unknown> }>('POST', '/api/sync-jobs/cancel', { body: { id: jobId } });
    return this.toJob(res.job);
  }

  async activateProject(projectId: string): Promise<void> {
    await this.send('POST', '/api/projects/activate', { body: { id: projectId } });
  }

  private toSource(raw: unknown): SyncSourceDraft {
    const r = (raw ?? {}) as Record<string, unknown>;
    return { type: (r['type'] as SyncSourceDraft['type']) ?? 'synthetic', accession: String(r['accession'] ?? ''), params: (r['params'] as Record<string, string | number>) ?? {} };
  }

  private toJob(r: Record<string, unknown>): SyncJob {
    const result = (r['result'] ?? {}) as Record<string, unknown>;
    return {
      id: String(r['id']), projectId: String(r['project_id']), source: this.toSource(r['source']), status: r['status'] as SyncJob['status'],
      progress: Number(r['progress'] ?? 0), message: String(r['message'] ?? ''), error: String(r['error'] ?? ''),
      log: (r['log'] as string[]) ?? [], upToDate: !!result['up_to_date']
    };
  }

  private toProject(p: Record<string, unknown>, active: string): ResearchProject {
    const stage = (p['stage'] as ResearchProject['stage']) ?? 'empty';
    const sources = (p['sources'] as Record<string, unknown>[]) ?? [];
    return {
      id: String(p['id']), name: String(p['name']), question: String(p['question'] ?? ''),
      status: stage === 'ingested' ? 'active' : 'draft',
      datasetName: sources.length ? `${sources[0]['type']}${sources[0]['accession'] ? ' · ' + sources[0]['accession'] : ''}` : t('Ainda sem dataset'),
      marker: String(p['marker'] ?? '16S'), samples: Number(p['samples'] ?? 0), asvs: Number(p['asvs'] ?? 0),
      groups: (p['groups'] as string[]) ?? [], analyses: (p['analyses'] as ResearchProject['analyses']) ?? [],
      results: (p['results'] as ResearchProject['results']) ?? [], updatedAt: String(p['updated_at'] ?? '').slice(0, 16).replace('T', ' '),
      mocked: false, stage, synthetic: !!p['synthetic'], active: String(p['id']) === active,
      source: sources.length ? { type: sources[0]['type'] as SyncSourceDraft['type'], accession: String(sources[0]['accession'] ?? '') } : undefined
    };
  }

  async pipeline(): Promise<PipelineSnapshot> {
    const res = await this.send<Raw>('GET', '/api/pipeline', { params: { lang: LANG, min_reads: this.normalization.rarefactionDepth } });
    const counts = (res['counts'] ?? {}) as Record<string, number>;
    const steps = (res['steps'] ?? {}) as Record<string, { status?: string; at?: string; message?: string }>;
    const ingested = !!res['ingested'];
    const qc = toPreview(res['qc']);
    const stage = (key: string, hasData: boolean): PipelineStage['status'] => {
      const status = steps[key]?.status;
      if (status === 'failed') return 'failed';
      return status === 'completed' || hasData ? 'complete' : 'pending';
    };
    const external = t('Fora do escopo da API (QIIME2/DADA2 rodam fora do FLORA)');
    const tableStatus: PipelineStage['status'] = !ingested
      ? 'pending'
      : qc.summary.lowDepth + qc.summary.metadataOnly + qc.summary.asvOnly + qc.rows.filter((r) => r.status === 'fail').length > 0
        ? 'attention'
        : 'complete';
    return {
      ingested,
      mocked: false,
      normalization: { ...this.normalization },
      note: t('Importação, primers e denoise acontecem fora do FLORA; aqui aparecem ingestão, QC e normalização.'),
      qc,
      stages: [
        { id: 'import', tool: 'QIIME2', name: t('Importar'), detail: external, status: 'pending' },
        { id: 'cutadapt', tool: 'QIIME2', name: t('Primers'), detail: external, status: 'pending' },
        { id: 'dada2', tool: 'DADA2', name: t('Denoise'), detail: external, status: 'pending' },
        { id: 'taxonomy', tool: 'FLORA', name: t('Taxonomia'), detail: t('{n} linhas de taxonomia', { n: counts['taxa'] ?? 0 }), status: stage('ingest_taxonomy', (counts['taxa'] ?? 0) > 0) },
        { id: 'table', tool: 'FLORA', name: t('Tabela'), detail: t('{n} amostras · {a} ASVs', { n: counts['samples'] ?? 0, a: counts['asvs'] ?? 0 }), status: tableStatus },
        {
          id: 'norm', tool: 'FLORA', name: t('Normalizar'),
          detail: t('Rarefação {d} · {m}', { d: this.normalization.rarefactionDepth, m: this.normalization.method.toUpperCase() }),
          status: ingested ? 'complete' : 'pending'
        }
      ]
    };
  }

  async previewIngest(request: IngestRequest): Promise<IngestPreview> {
    const res = await this.send<Raw>('POST', '/api/ingest/preview', {
      body: {
        metadata_path: request.metadataPath,
        asv_path: request.asvPath,
        sample_col: request.sampleColumn,
        group_col: request.groupColumn,
        wide_format: request.wideFormat,
        min_reads: this.normalization.rarefactionDepth,
        lang: LANG
      }
    });
    return toPreview(res);
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
    const summary = await this.send<Raw>('GET', '/api/explore/summary', {
      params: { lang: LANG, group_by: group, groups: query.groups.join(','), rank: query.rank, min_reads: this.normalization.rarefactionDepth }
    });
    const notes = ((summary['notes'] as string[]) ?? []).join(' ');
    return {
      query,
      pcoa,
      alpha,
      beta,
      taxonomy,
      relations,
      tree: toTree(summary['tree']),
      comparisons: toComparisons(summary['comparisons']),
      differential: toDifferential(summary['differential']),
      distanceNote: t('Métrica pedida ao endpoint /api/viz/beta_heatmap.'),
      sampleCount: Number(summary['sample_count'] ?? 0),
      asvCount: Number(summary['asv_count'] ?? 0),
      mocked: false,
      note: notes || undefined
    };
  }

  async experiments(): Promise<MlExperiment[]> {
    const res = await this.send<{ experiments: unknown[] }>('GET', '/api/ml/experiments');
    return [...this.failedExperiments, ...(res.experiments ?? []).map(toExperiment)];
  }

  async trainModel(request: TrainRequest): Promise<MlExperiment> {
    try {
      const response = await this.send<{ success: boolean; error?: string; experiment?: unknown }>('POST', '/api/ml/classify', {
        body: {
          model: request.model,
          target_column: request.targetColumn,
          train_filter: request.trainFilter,
          test_filter: request.testFilter,
          normalize: request.normalize === 'none' ? null : request.normalize,
          cv_folds: request.cvFolds,
          seed: request.seed,
          lang: LANG
        }
      });
      if (!response.success || !response.experiment) {
        throw new Error(response.error ?? t('Classificação recusada.'));
      }
      return toExperiment(response.experiment);
    } catch (error) {
      const message = error instanceof Error ? error.message : t('Falha no treino.');
      const failed: MlExperiment = {
        id: `http-failed-${Date.now()}`,
        name: request.model,
        model: request.model,
        status: 'failed',
        createdAt: new Date().toISOString().slice(0, 16).replace('T', ' '),
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
      this.failedExperiments = [failed, ...this.failedExperiments];
      return failed;
    }
  }

  async clusterSamples(request: ClusterRequest): Promise<ClusterSummary> {
    try {
      const response = await this.send<ClusterResponse>('POST', '/api/ml/cluster', {
        body: {
          method: request.method,
          n_clusters: request.nClusters,
          normalize: request.normalize,
          seed: request.seed
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
    const latest = new Map<string, MlExperiment>();
    for (const experiment of await this.experiments()) {
      if (experiment.status === 'completed' && !latest.has(experiment.model)) {
        latest.set(experiment.model, experiment);
      }
    }
    return [...latest.values()].map((experiment) => ({
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
    const res = await this.send<Raw>('GET', '/api/report/draft', { params: { lang: LANG } });
    const figures: ReportDraft['figures'] = {};
    for (const [key, fig] of Object.entries((res['figures'] ?? {}) as Raw)) {
      figures[key as keyof ReportDraft['figures']] = toFigure(fig);
    }
    return {
      title: String(res['title'] ?? t('Relatório FLORA')),
      projectId: String(res['project_id'] ?? 'workspace'),
      mocked: false,
      note: t('O HTML/PDF local usa o texto editado. O backend gera outro artefato em POST /api/report.'),
      parameters: ((res['parameters'] as { label: string; value: string }[]) ?? []).map((p) => ({ label: String(p.label), value: String(p.value) })),
      figures,
      sections: toSections(res['sections'])
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
          output_format: request.format === 'both' ? 'both' : request.format,
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
    const res = await this.send<{ jobs: unknown[] }>('GET', '/api/downloads');
    return (res.jobs ?? []).map(toDownload);
  }

  async searchLibrary(source: LibrarySource, query: string): Promise<StudyEntry[]> {
    const res = await this.send<{ studies: unknown[] }>('GET', '/api/downloads/library', { params: { source, q: query, limit: 20 } });
    return (res.studies ?? []).map(toStudy);
  }

  async resolveRuns(studyAccession: string): Promise<string[]> {
    const res = await this.send<{ runs: string[] }>('GET', '/api/downloads/library/runs', { params: { study: studyAccession, limit: 10 } });
    return res.runs ?? [];
  }

  async catalog(query: CatalogQuery): Promise<CatalogEntry[]> {
    const res = await this.send<{ studies: unknown[] }>('GET', '/api/library/catalog', {
      params: {
        q: query.q,
        biome: query.biome,
        host: query.host,
        region: query.region,
        seq_type: query.seqType,
        amazonia: query.amazonia ? '1' : ''
      }
    });
    return (res.studies ?? []).map(toCatalogEntry);
  }

  async datasetMetadata(source: string, accession: string): Promise<MetadataPreview> {
    const res = await this.send<{ preview: unknown }>('GET', `/api/library/${encodeURIComponent(source)}/${encodeURIComponent(accession)}/metadata`, {
      params: { limit: 50 }
    });
    return toMetadataPreview(res.preview);
  }

  async downloadDataset(source: string, accession: string): Promise<DownloadJob> {
    try {
      const response = await this.send<DownloadResponse & { job?: unknown }>(
        'POST',
        `/api/library/${encodeURIComponent(source)}/${encodeURIComponent(accession)}/download`,
        { body: {} }
      );
      if (!response.success || !response.job) {
        throw new Error(response.error ?? t('Download recusado.'));
      }
      return toDownload(response.job);
    } catch (error) {
      return {
        id: `http-failed-${Date.now()}`,
        source,
        status: 'failed',
        detail: error instanceof Error ? error.message : t('Falha no download.'),
        artifacts: [],
        mocked: false,
        createdAt: new Date().toISOString()
      };
    }
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
      const response = await this.send<DownloadResponse & { job?: unknown }>('POST', path, { body });
      if (!response.success || !response.job) {
        throw new Error(response.error ?? t('Download recusado.'));
      }
      return toDownload(response.job);
    } catch (error) {
      // The server records failed attempts too, so this local object is only the immediate answer.
      return {
        id: `http-failed-${Date.now()}`,
        source: request.source,
        status: 'failed',
        detail: error instanceof Error ? error.message : t('Falha no download.'),
        artifacts: [],
        mocked: false,
        createdAt: new Date().toISOString()
      };
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

function apiMetric(metric: ExplorationQuery['metric']): string {
  return metric === 'observed' ? 'observed_features' : metric;
}
