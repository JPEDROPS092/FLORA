import { environment } from '../../../../environments/environment';
import {
  ClusterRequest,
  ClusterSummary,
  DashboardSnapshot,
  DataSourceInfo,
  DiagnosticEntry,
  DownloadJob,
  DownloadRequest,
  LibrarySource,
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
  ExampleProject,
  ProjectDraft,
  SyncJob,
  SyncSourceDraft,
  ReportDraft,
  ResearchProject,
  ScientificExport,
  TrainRequest
} from '../../models/domain';
import { FloraRepository } from '../flora.repository';
import { aggregateIngest } from '../ingest-aggregate';
import { settleChart } from '../settle-chart';
import { buildReportFiles } from '../../export/report-document';
import {
  ASV_COUNT,
  DIFFERENTIAL,
  GENERA,
  METADATA_COLUMNS,
  MOCK_LOGS,
  MockSample,
  RANK_TABLE,
  STUDY_ID,
  STUDY_NAME,
  TAXON_TREE,
  analyzableSamples,
  baseProvenance,
  createSamples,
  defaultNormalization
} from './mock-study';
import {
  alphaBox,
  betaHeatmap,
  confusionHeatmap,
  importanceBars,
  pcoaScatter,
  readHistogram,
  relationHeatmap,
  rocFigure,
  taxonomyBar
} from './figures';
import { t } from '../../i18n/i18n';

const SOURCE: DataSourceInfo = {
  mode: 'mock',
  label: t('FL16S-SORGHUM-01 · 80 amostras · 1.842 ASVs'),
  apiBaseUrl: environment.apiBaseUrl,
  mocked: true
};

const LIMITATIONS = [
  t('n = 80 e três classes: a acurácia interna não substitui um conjunto externo.'),
  t('A divisão registrada nos filtros não é executada como SQL no mock; o holdout é estratificado pela seed.'),
  t('CLR em contagens esparsas de 16S comprime zeros e pode inflar correlações.'),
  t('SHAP e importância descrevem o modelo, não um efeito biológico causal.'),
  t('Amostras abaixo de 10.000 reads foram excluídas antes do treino.')
];

function wait(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 90));
}

function mean(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function sd(values: number[]): number {
  if (values.length < 2) {
    return 0;
  }
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export class MockFloraRepository extends FloraRepository {
  readonly source = SOURCE;

  private readonly samples = createSamples();
  private normalization = defaultNormalization();
  private projectStore: ResearchProject[] = this.seedProjects();
  private experimentStore: MlExperiment[] = [this.seedExperiment('random_forest', 42, 0), this.seedExperiment('xgboost', 42, 1)];
  private jobs: DownloadJob[] = this.seedJobs();
  private ingested = true;
  private readonly syncJobs = new Map<string, { job: SyncJob; polls: number }>();

  async dashboard(): Promise<DashboardSnapshot> {
    await wait();
    const reads = this.samples.map((sample) => sample.reads).filter((value): value is number => value !== null);
    const pass = this.samples.filter((sample) => sample.status === 'pass');
    const groups = [...new Set(pass.map((sample) => sample.group).filter((group): group is string => Boolean(group)))];
    const analyzed = analyzableSamples(this.samples, groups, this.normalization.rarefactionDepth);
    return {
      source: this.source,
      studyId: STUDY_ID,
      studyName: STUDY_NAME,
      marker: '16S V4',
      samples: this.samples.length,
      asvs: ASV_COUNT,
      groups: 3,
      groupNames: ['Rhizosphere', 'Bulk soil', 'Endosphere'],
      quality: {
        pass: this.samples.filter((sample) => sample.status === 'pass').length,
        warn: this.samples.filter((sample) => sample.status === 'warn').length,
        fail: this.samples.filter((sample) => sample.status === 'fail').length,
        meanReads: Math.round(mean(reads)),
        medianReads: Math.round(median(reads))
      },
      recent: this.recentFromState(),
      alpha: await settleChart(async () => alphaBox(analyzed, 'shannon')),
      pcoa: await settleChart(async () => pcoaScatter(analyzed)),
      mocked: true,
      partial: false,
      status: 'mock',
      workdir: 'results/FL16S-SORGHUM-01'
    };
  }

  async diagnostics(lines = 120): Promise<DiagnosticEntry[]> {
    await wait();
    return MOCK_LOGS.slice(-lines).map((line) => {
      const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|WARNING|ERROR) (.*)$/);
      if (!match) {
        return { timestamp: '', level: 'INFO' as const, message: line };
      }
      return { timestamp: match[1], level: match[2] as DiagnosticEntry['level'], message: match[3] };
    });
  }

  async projects(): Promise<ResearchProject[]> {
    await wait();
    return this.projectStore.map((project) => ({ ...project }));
  }

  async saveProject(draft: ProjectDraft): Promise<ResearchProject> {
    await wait();
    const project: ResearchProject = {
      id: `project-${this.projectStore.length + 1}`,
      name: draft.name.trim(),
      question: draft.question.trim(),
      status: 'draft',
      datasetName: t('Ainda sem dataset'),
      marker: '16S',
      samples: 0,
      asvs: 0,
      groups: [],
      analyses: [],
      results: [],
      updatedAt: new Date().toISOString().slice(0, 16).replace('T', ' '),
      mocked: true
    };
    this.projectStore = [project, ...this.projectStore];
    return project;
  }

  async examples(): Promise<ExampleProject[]> {
    await wait();
    const base = { biome: '', synthetic: false, verified: false, installable: true };
    return [
      { ...base, id: 'synthetic-demo', name: 'Synthetic Microbiome Demo', question: t('Os quatro biomas sintéticos diferem em diversidade?'), description: t('80 amostras, 200 ASVs, seed 42. Dados sintéticos, não reais.'),
        biome: 'synthetic', synthetic: true, verified: true, source: { type: 'synthetic', accession: 'seed-42' } },
      { ...base, id: 'amazon-forest-mgnify', name: 'Amazonian Forest Microbiome', question: t('Quais táxons caracterizam o solo da floresta amazônica?'), description: t('Template MGnify (MGYS00005116). Ainda não verificado na fonte.'),
        biome: 'soil', source: { type: 'mgnify', accession: 'MGYS00005116' } },
      { ...base, id: 'tropical-soil-sra', name: 'Brazilian Tropical Soil', question: t('Como o solo tropical varia entre sítios?'), description: t('Template NCBI SRA (SRP151124). Baixa FASTQ; precisa de processamento.'),
        biome: 'soil', source: { type: 'sra', accession: 'SRP151124' } }
    ];
  }

  async installExample(id: string): Promise<{ project: ResearchProject; job: SyncJob }> {
    await wait();
    const example = (await this.examples()).find((e) => e.id === id);
    if (!example) throw new Error(t('Exemplo desconhecido.'));
    const project = await this.saveProject({ name: example.name, question: example.question });
    project.synthetic = example.synthetic;
    project.source = { type: example.source.type, accession: example.source.accession };
    return { project, job: await this.startSync(project.id, example.source) };
  }

  async startSync(projectId: string, source: SyncSourceDraft): Promise<SyncJob> {
    await wait();
    const job: SyncJob = { id: `job-${this.syncJobs.size + 1}`, projectId, source, status: 'queued', progress: 0, message: t('Na fila'), error: '', log: [], upToDate: false };
    this.syncJobs.set(job.id, { job, polls: 0 });
    return { ...job };
  }

  async syncJob(jobId: string): Promise<SyncJob> {
    await wait();
    const entry = this.syncJobs.get(jobId);
    if (!entry) throw new Error(t('Job não encontrado.'));
    if (entry.job.status === 'queued' || entry.job.status === 'running') {
      entry.polls += 1;
      entry.job.progress = Math.min(100, entry.polls * 34);
      entry.job.status = entry.job.progress >= 100 ? 'completed' : 'running';
      entry.job.message = entry.job.status === 'completed' ? t('Simulação concluída (dados mockados)') : t('Simulando sincronização');
    }
    return { ...entry.job };
  }

  async cancelSync(jobId: string): Promise<SyncJob> {
    const entry = this.syncJobs.get(jobId);
    if (!entry) throw new Error(t('Job não encontrado.'));
    entry.job.status = 'cancelled';
    entry.job.message = t('Cancelado');
    return { ...entry.job };
  }

  async activateProject(): Promise<void> {
    await wait();
  }

  async pipeline(): Promise<PipelineSnapshot> {
    await wait();
    return this.pipelineSnapshot();
  }

  async previewIngest(request: IngestRequest): Promise<IngestPreview> {
    await wait();
    return this.buildPreview(request);
  }

  async confirmIngest(request: IngestRequest): Promise<IngestOutcome> {
    await wait();
    const steps: IngestStepResult[] = [
      this.localStep('metadata', request.metadataPath, request.metadataPath ? t('{n} amostras lidas', { n: this.samples.length }) : ''),
      this.localStep('asv', request.asvPath, request.asvPath ? t('{n} ASVs no formato {fmt}', { n: ASV_COUNT, fmt: request.wideFormat ? t('largo') : t('longo') }) : ''),
      this.localStep(
        'taxonomy',
        request.taxonomyPath === 'fail-taxonomy' ? '' : request.taxonomyPath,
        request.taxonomyPath && request.taxonomyPath !== 'fail-taxonomy' ? t('{n} linhas de taxonomia', { n: ASV_COUNT }) : ''
      )
    ];
    if (request.taxonomyPath === 'fail-taxonomy') {
      steps[2] = { step: 'taxonomy', success: false, error: t('Falha simulada na taxonomia (caminho fail-taxonomy).') };
    }
    const outcome = aggregateIngest(steps);
    this.ingested = outcome.success;
    return outcome;
  }

  async applyNormalization(config: NormalizationConfig): Promise<PipelineSnapshot> {
    await wait();
    this.normalization = { ...config };
    return this.pipelineSnapshot();
  }

  async exploration(query: ExplorationQuery): Promise<ExplorationBundle> {
    await wait();
    const groups = query.groups.length ? query.groups : ['Rhizosphere', 'Bulk soil', 'Endosphere'];
    const analyzed = analyzableSamples(this.samples, groups, this.normalization.rarefactionDepth);
    const empty = analyzed.length === 0;
    const rankRows = compositionRows(RANK_TABLE[query.rank] ?? GENERA, groups, query.topN);
    const differential = DIFFERENTIAL.filter((row) => (query.rank === 'phylum' ? row.rank === 'phylum' : row.rank === 'genus'));
    return {
      query: { ...query, groups },
      pcoa: empty
        ? { status: 'empty', error: t('Nenhuma amostra passou nos filtros e na rarefação.') }
        : await settleChart(async () => pcoaScatter(analyzed)),
      alpha: empty
        ? { status: 'error', error: t('Diversidade alfa exige amostras acima do limiar de rarefação.') }
        : await settleChart(async () => alphaBox(analyzed, query.metric)),
      beta: empty
        ? { status: 'empty', error: t('Matriz beta vazia para estes grupos.') }
        : await settleChart(async () => betaHeatmap(analyzed)),
      taxonomy: await settleChart(async () => taxonomyBar(rankRows, groups, query.rank)),
      relations: await settleChart(async () => relationHeatmap(query.topN)),
      tree: TAXON_TREE,
      comparisons: this.compare(analyzed),
      differential,
      distanceNote:
        query.distance === 'jaccard'
          ? t('Jaccard (mock) segue a mesma ordenação; a escala exibida é Bray–Curtis de demonstração.')
          : t('Bray–Curtis de demonstração, coerente com a separação no PCoA. Não é a matriz 80×80.'),
      sampleCount: analyzed.length,
      asvCount: ASV_COUNT,
      mocked: true
    };
  }

  async experiments(): Promise<MlExperiment[]> {
    await wait();
    return this.experimentStore.map((experiment) => ({ ...experiment }));
  }

  async trainModel(request: TrainRequest): Promise<MlExperiment> {
    await wait();
    if (!request.trainFilter.trim() || !request.testFilter.trim()) {
      return this.failedExperiment(request, t('train_filter e test_filter são obrigatórios.'));
    }
    const experiment = this.seedExperiment(request.model, request.seed, this.experimentStore.length, request);
    this.experimentStore = [experiment, ...this.experimentStore];
    return experiment;
  }

  async clusterSamples(request: ClusterRequest): Promise<ClusterSummary> {
    await wait();
    const silhouette = request.method === 'kmeans' ? 0.41 : 0.37;
    return {
      success: true,
      method: request.method,
      nClusters: request.method === 'hdbscan' ? 3 : request.nClusters,
      silhouette,
      daviesBouldin: request.method === 'kmeans' ? 0.92 : null,
      noiseFraction: request.method === 'hdbscan' ? 0.06 : 0,
      mocked: true
    };
  }

  async comparison(): Promise<ModelComparisonRow[]> {
    await wait();
    const latest = new Map<string, MlExperiment>();
    for (const experiment of this.experimentStore) {
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
    await wait();
    return this.buildDraft();
  }

  async exportReport(request: ExportRequest): Promise<ScientificExport> {
    await wait();
    const draft = this.buildDraft();
    const files = buildReportFiles({
      title: request.title || draft.title,
      sections: request.sections,
      parameters: draft.parameters,
      figures: draft.figures,
      mocked: true
    });
    return {
      success: true,
      title: request.title || draft.title,
      html: files.html,
      pdfBase64: files.pdfBase64,
      warnings: request.format === 'pdf' ? [t('O PDF textual não incorpora as figuras; elas estão no HTML.')] : [],
      mocked: true
    };
  }

  async downloads(): Promise<DownloadJob[]> {
    await wait();
    return this.jobs.map((job) => ({ ...job }));
  }

  async searchLibrary(source: LibrarySource, query: string): Promise<StudyEntry[]> {
    await wait();
    const q = query.trim().toLowerCase();
    const base = { description: '', biome: '', samples: 0, centre: '', bioproject: '', secondary: '', updated: '', origin: 'curated' as const, importable: true };
    const all: StudyEntry[] = [
      { ...base, source: 'synthetic', accession: 'SYNTHETIC', title: t('Coorte sintética'), description: t('Gerada localmente com seed; quatro biomas brasileiros. Dados não reais.'), biome: 'Synthetic', samples: 80, centre: 'FLORA', url: '' },
      { ...base, source: 'emp', accession: 'EMP-R1', title: 'Earth Microbiome Project — Release 1', biome: 'Global', samples: 2000, centre: 'EMP · Qiita / UCSD', url: 'https://doi.org/10.5281/zenodo.890000' },
      { ...base, source: 'mgnify', accession: 'MGYS00005116', title: t('Solo de floresta amazônica (MGnify)'), biome: 'Amazonian Forest', samples: 80, centre: 'MGnify', url: 'https://www.ebi.ac.uk/metagenomics/studies/MGYS00005116' },
      { ...base, source: 'ena', accession: 'SRP151124', title: t('Solo tropical brasileiro (NCBI SRA)'), biome: 'Brazilian Tropical Soil', samples: 60, centre: 'NCBI SRA', url: 'https://www.ncbi.nlm.nih.gov/sra/?term=SRP151124' },
      { ...base, source: 'ena', accession: 'ERP009703', title: t('Rizosfera amazônica'), biome: 'Amazonian Rhizosphere', samples: 120, centre: 'ENA', url: 'https://www.ebi.ac.uk/ena/browser/view/ERP009703' }
    ];
    const pool = source === 'curated' ? all : all.filter((e) => e.source === source);
    return pool.filter((e) => !q || `${e.accession} ${e.title} ${e.biome}`.toLowerCase().includes(q));
  }

  async resolveRuns(): Promise<string[]> {
    await wait();
    return [];
  }

  async requestDownload(request: DownloadRequest): Promise<DownloadJob> {
    await wait();
    const job = this.jobFromRequest(request, 'completed');
    this.jobs = [job, ...this.jobs];
    return job;
  }

  private pipelineSnapshot(): PipelineSnapshot {
    const preview = this.buildPreview({
      metadataPath: 'results/raw/FL16S-SORGHUM-01/metadata.tsv',
      asvPath: 'results/raw/FL16S-SORGHUM-01/asv_table.tsv',
      taxonomyPath: 'results/raw/FL16S-SORGHUM-01/taxonomy.tsv',
      sampleColumn: 'sample_id',
      groupColumn: 'group',
      wideFormat: true
    });
    const method = this.normalization.method.toUpperCase();
    return {
      ingested: this.ingested,
      mocked: true,
      normalization: { ...this.normalization },
      qc: preview,
      stages: [
        { id: 'import', tool: 'QIIME2', name: t('Importar'), detail: 'FASTQ Casava 1.8 + metadata', status: 'complete' },
        { id: 'cutadapt', tool: 'QIIME2', name: t('Primers'), detail: 'cutadapt 515F/806R', status: 'complete' },
        { id: 'dada2', tool: 'DADA2', name: t('Denoise'), detail: 'truncLen 240/200 · maxEE 2', status: 'complete' },
        { id: 'taxonomy', tool: 'QIIME2', name: t('Taxonomia'), detail: 'SILVA 138.2', status: 'complete' },
        {
          id: 'table',
          tool: 'FLORA',
          name: t('Tabela'),
          detail: t('{n} amostras · {a} ASVs', { n: this.samples.length, a: ASV_COUNT }),
          status: preview.summary.lowDepth + preview.summary.metadataOnly + preview.summary.asvOnly > 0 ? 'attention' : 'complete'
        },
        {
          id: 'norm',
          tool: 'FLORA',
          name: t('Normalizar'),
          detail: t('Rarefação {d} · {m}', { d: this.normalization.rarefactionDepth, m: method }),
          status: this.ingested ? 'complete' : 'pending'
        }
      ]
    };
  }

  private buildPreview(request: IngestRequest): IngestPreview {
    const columns = request.metadataColumns?.length ? request.metadataColumns : METADATA_COLUMNS;
    const warnings: string[] = [t('Estudo mockado FL16S-SORGHUM-01. Os arquivos enviados não substituem a coorte de demonstração.')];
    if (request.metadataColumns?.length && !request.metadataColumns.includes(request.sampleColumn)) {
      warnings.push(t('A coluna "{col}" não está no cabeçalho enviado.', { col: request.sampleColumn }));
    }
    const rows = [...this.samples]
      .sort((a, b) => statusRank(a) - statusRank(b))
      .map((sample) => ({
        sampleId: sample.id,
        metadataId: sample.metadataId,
        group: sample.group,
        inMetadata: sample.inMetadata,
        inAsv: sample.inAsv,
        reads: sample.reads,
        status: sample.status,
        issues: sample.issues
      }));
    const reads = this.samples.map((sample) => sample.reads).filter((value): value is number => value !== null);
    return {
      columns,
      rows,
      summary: {
        matched: this.samples.filter((sample) => sample.inMetadata && sample.inAsv && sample.metadataId === sample.id).length,
        metadataOnly: this.samples.filter((sample) => sample.inMetadata && !sample.inAsv).length,
        asvOnly: this.samples.filter((sample) => sample.inAsv && !sample.inMetadata).length,
        lowDepth: this.samples.filter((sample) => (sample.reads ?? 0) > 0 && (sample.reads ?? 0) < this.normalization.rarefactionDepth).length,
        totalAsvs: ASV_COUNT
      },
      histogram: readHistogram(reads),
      mocked: true,
      warnings
    };
  }

  private compare(samples: MockSample[]): ExplorationBundle['comparisons'] {
    const groups = [...new Set(samples.map((sample) => sample.group).filter((group): group is string => Boolean(group)))];
    return groups.map((group) => {
      const rows = samples.filter((sample) => sample.group === group);
      const shannon = rows.map((sample) => sample.shannon);
      return {
        group,
        n: rows.length,
        shannonMean: Math.round(mean(shannon) * 100) / 100,
        shannonSd: Math.round(sd(shannon) * 100) / 100,
        observedMean: Math.round(mean(rows.map((sample) => sample.observed)))
      };
    });
  }

  private localStep(step: IngestStepResult['step'], path: string, detail: string): IngestStepResult {
    if (!path.trim()) {
      return { step, success: false, error: 'caminho ausente' };
    }
    return { step, success: true, detail };
  }

  private seedExperiment(
    model: TrainRequest['model'],
    seed: number,
    offset: number,
    request?: TrainRequest
  ): MlExperiment {
    const swing = request ? ((seed + offset * 17) % 7) / 100 : 0;
    const accuracy = model === 'xgboost' ? 0.88 - swing : 0.86 - swing / 2;
    const f1 = accuracy - 0.02;
    const auc = model === 'xgboost' ? 0.94 : 0.91;
    const labels = ['Rhizosphere', 'Bulk soil', 'Endosphere'];
    const matrix =
      model === 'xgboost'
        ? [
            [18, 2, 1],
            [1, 16, 1],
            [1, 0, 12]
          ]
        : [
            [17, 3, 1],
            [2, 15, 1],
            [1, 1, 11]
          ];
    const importances = [
      { feature: 'Pseudomonas', value: model === 'xgboost' ? 0.084 : 0.071 },
      { feature: 'Methylobacterium', value: 0.066 },
      { feature: 'Acidibacter', value: -0.058 },
      { feature: 'Bacillus', value: 0.051 },
      { feature: 'Sphingomonas', value: -0.047 },
      { feature: 'Bradyrhizobium', value: 0.033 },
      { feature: 'Burkholderia', value: 0.029 },
      { feature: 'Streptomyces', value: 0.018 },
      { feature: 'Massilia', value: -0.014 },
      { feature: 'Pedobacter', value: -0.011 }
    ];
    const provenance = baseProvenance(seed);
    provenance.parameters = [
      ...provenance.parameters,
      { label: 'Modelo', value: model },
      { label: 'Alvo', value: request?.targetColumn ?? 'group' },
      { label: t('Filtro de treino'), value: request?.trainFilter || "site != 'Janaúba'" },
      { label: t('Filtro de teste'), value: request?.testFilter || "site = 'Janaúba'" },
      { label: 'CV', value: String(request?.cvFolds ?? 5) },
      { label: t('Normalização'), value: (request?.normalize ?? 'clr').toUpperCase() }
    ];
    provenance.history = [
      ...provenance.history,
      { at: '2026-02-12 11:18', event: `Treino ${model}, seed ${seed}.` }
    ];
    return {
      id: `exp-${model}-${seed}-${offset}`,
      name: model === 'xgboost' ? t('XGBoost · grupo') : t('Random Forest · grupo'),
      model,
      status: 'completed',
      createdAt: offset === 0 ? '2026-02-12 11:18' : '2026-02-12 11:24',
      accuracy: Math.round(accuracy * 1000) / 1000,
      f1Macro: Math.round(f1 * 1000) / 1000,
      rocAuc: auc,
      cvAccuracyMean: Math.round((accuracy - 0.03) * 1000) / 1000,
      trainN: 56,
      testN: 19,
      features: 612,
      importanceKind: 'shap',
      confusion: { status: 'ok', figure: confusionHeatmap(labels, matrix, true) },
      roc: { status: 'ok', figure: rocFigure(true) },
      importance: { status: 'ok', figure: importanceBars(importances, 'shap') },
      labels,
      matrix,
      importances,
      config: provenance.parameters,
      limitations: LIMITATIONS,
      provenance,
      mocked: true
    };
  }

  private failedExperiment(request: TrainRequest, error: string): MlExperiment {
    return {
      id: `exp-failed-${Date.now()}`,
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
      confusion: { status: 'error', error },
      roc: { status: 'error', error },
      importance: { status: 'error', error },
      labels: [],
      matrix: [],
      importances: [],
      config: [],
      limitations: LIMITATIONS,
      provenance: baseProvenance(request.seed),
      error,
      mocked: true
    };
  }

  private buildDraft(): ReportDraft {
    const analyzed = analyzableSamples(this.samples, ['Rhizosphere', 'Bulk soil', 'Endosphere'], this.normalization.rarefactionDepth);
    const comparisons = this.compare(analyzed);
    const best = this.experimentStore.find((experiment) => experiment.status === 'completed');
    const provenance = baseProvenance();
    return {
      title: t('FL16S-SORGHUM-01 · diversidade e predição de compartimento'),
      projectId: 'sorghum-drought',
      mocked: true,
      parameters: provenance.parameters,
      figures: {
        alpha: alphaBox(analyzed, 'shannon'),
        pcoa: pcoaScatter(analyzed),
        taxonomy: taxonomyBar(GENERA.slice(0, 8), ['Rhizosphere', 'Bulk soil', 'Endosphere'], 'genus'),
        beta: betaHeatmap(analyzed),
        confusion: best?.confusion.figure,
        shap: best?.importance.figure
      },
      sections: [
        {
          id: 'summary',
          title: t('Resumo'),
          included: true,
          figure: null,
          narrative:
            t('O estudo mockado FL16S-SORGHUM-01 compara rizosfera, solo bulk e endosfera de Sorghum bicolor (80 amostras, 1.842 ASVs, marcador 16S V4). Após o controle de qualidade, 75 amostras permanecem acima de 10.000 reads. A ordenação separa os três compartimentos e a diversidade de Shannon é maior no solo bulk.'),
          table: {
            columns: [t('Grupo'), 'n', 'Shannon', 'ASVs observados'],
            rows: comparisons.map((row) => [row.group, String(row.n), `${row.shannonMean} ± ${row.shannonSd}`, String(row.observedMean)])
          }
        },
        {
          id: 'methods',
          title: t('Métodos'),
          included: true,
          figure: null,
          narrative:
            t('As leituras foram importadas no QIIME2 2024.10, os primers 515F/806R removidos com cutadapt e as sequências denoiseadas no DADA2 (truncLen 240/200, maxEE 2). A taxonomia usou SILVA 138.2. A tabela foi rarefeita a 10.000 reads. A matriz para ordenação e modelos foi transformada por CLR com prevalência mínima de 5%. Beta-diversidade: Bray–Curtis e PCoA. Modelos: Random Forest e XGBoost, seed 42, validação cruzada de 5 dobras. Os valores são de demonstração.'),
          table: null
        },
        {
          id: 'alpha',
          title: t('Diversidade alfa'),
          included: true,
          figure: 'alpha',
          narrative: t('Shannon, Simpson, ASVs observados e Chao1 foram calculados depois da rarefação. O solo bulk concentra a maior riqueza; a endosfera é a comunidade mais restrita.'),
          table: null
        },
        {
          id: 'beta',
          title: t('Diversidade beta'),
          included: true,
          figure: 'pcoa',
          narrative: t('O PCoA (Bray–Curtis) separa endosfera, rizosfera e solo bulk no primeiro plano (PC1 28,4%, PC2 14,1%). A matriz exibida é um recorte coerente com essa ordenação.'),
          table: null
        },
        {
          id: 'taxonomy',
          title: t('Composição'),
          included: true,
          figure: 'taxonomy',
          narrative:
            t('Pseudomonas e Bacillus são enriquecidos na rizosfera. Acidibacter e Sphingomonas predominam no solo bulk. Methylobacterium marca a endosfera. Os contrastes usam log2 fold change e q-value de um teste mockado.'),
          table: {
            columns: [t('Táxon'), 'log2FC', 'q', t('Maior em')],
            rows: DIFFERENTIAL.filter((row) => row.rank === 'genus').map((row) => [
              row.taxon,
              row.log2FoldChange.toFixed(2),
              row.qValue.toFixed(3),
              row.higherIn
            ])
          }
        },
        {
          id: 'ml',
          title: 'Modelos',
          included: true,
          figure: 'confusion',
          narrative: best
            ? t('O melhor experimento interno ({model}) alcançou acurácia {acc}, F1 macro {f1} e ROC AUC {auc}. A importância é SHAP médio e não deve ser lida como mecanismo.', { model: best.model, acc: best.accuracy.toFixed(2), f1: best.f1Macro.toFixed(2), auc: best.rocAuc?.toFixed(2) ?? '—' })
            : t('Nenhum modelo concluído.'),
          table: null
        },
        {
          id: 'parameters',
          title: t('Parâmetros reprodutíveis'),
          included: true,
          figure: 'shap',
          narrative: t('Seed, versões e limiares abaixo acompanham qualquer reexecução. Trocar a rarefação ou a transformação altera a matriz e invalida a comparação direta.'),
          table: {
            columns: [t('Parâmetro'), t('Valor')],
            rows: provenance.parameters.map((item) => [item.label, item.value])
          }
        }
      ]
    };
  }

  private recentFromState(): DashboardSnapshot['recent'] {
    const provenance = baseProvenance();
    return [
      {
        id: 'run-qc',
        name: t('QC de amostras'),
        kind: 'ingest',
        status: 'completed',
        finishedAt: '2026-02-12 10:22',
        projectId: 'sorghum-drought',
        summary: '75 passam, 1 alerta, 4 falham.',
        provenance
      },
      {
        id: 'run-alpha',
        name: t('Diversidade alfa'),
        kind: 'alpha',
        status: 'completed',
        finishedAt: '2026-02-12 11:06',
        projectId: 'sorghum-drought',
        summary: t('Shannon após rarefação a 10.000.'),
        provenance
      },
      {
        id: 'run-pcoa',
        name: 'PCoA Bray–Curtis',
        kind: 'beta',
        status: 'completed',
        finishedAt: '2026-02-12 11:09',
        projectId: 'sorghum-drought',
        summary: t('Três compartimentos no primeiro plano.'),
        provenance
      },
      ...this.experimentStore.slice(0, 2).map((experiment) => ({
        id: experiment.id,
        name: experiment.name,
        kind: 'ml',
        status: experiment.status,
        finishedAt: experiment.createdAt,
        projectId: 'sorghum-drought',
        summary: t('Acurácia {a} · F1 {f}', { a: experiment.accuracy.toFixed(2), f: experiment.f1Macro.toFixed(2) }),
        provenance: experiment.provenance
      }))
    ];
  }

  private seedProjects(): ResearchProject[] {
    return [
      {
        id: 'sorghum-drought',
        name: 'Sorgo sob seca',
        question: t('O compartimento radicular prediz a composição de ASVs melhor do que o sítio?'),
        status: 'active',
        datasetName: STUDY_NAME,
        marker: '16S V4',
        samples: 80,
        asvs: ASV_COUNT,
        groups: ['Rhizosphere', 'Bulk soil', 'Endosphere'],
        analyses: [
          { id: 'a1', name: t('Alfa e PCoA'), kind: 'diversity', status: 'completed' },
          { id: 'a2', name: t('Táxons diferenciais'), kind: 'taxonomy', status: 'completed' },
          { id: 'a3', name: t('Random Forest e XGBoost'), kind: 'ml', status: 'completed' }
        ],
        results: [
          { id: 'r1', title: t('Separação de compartimentos'), summary: t('PCoA Bray–Curtis separa os três grupos no PC1–PC2.') },
          { id: 'r2', title: t('Predição de grupo'), summary: t('XGBoost interno: acurácia 0,88, F1 macro 0,86.') }
        ],
        updatedAt: '2026-02-12 11:40',
        mocked: true
      },
      {
        id: 'cerrado-chrono',
        name: t('Cronossequência de Cerrado'),
        question: t('A idade de regeneração desloca Acidobacteriota no solo superficial?'),
        status: 'archived',
        datasetName: 'Cerrado chronosequence 16S',
        marker: '16S V4',
        samples: 46,
        asvs: 2104,
        groups: ['Pasture', 'Early', 'Late'],
        analyses: [{ id: 'c1', name: 'PCoA', kind: 'beta', status: 'completed' }],
        results: [{ id: 'cr1', title: t('Gradiente de idade'), summary: t('Late se aproxima do solo de referência.') }],
        updatedAt: '2025-11-03 16:12',
        mocked: true
      },
      {
        id: 'atl-endo',
        name: t('Endófitos de Mata Atlântica'),
        question: t('Folha e pecíolo compartilham o mesmo núcleo de Methylobacterium?'),
        status: 'draft',
        datasetName: t('Ainda sem tabela'),
        marker: '16S V4',
        samples: 0,
        asvs: 0,
        groups: [],
        analyses: [],
        results: [],
        updatedAt: '2026-01-20 08:02',
        mocked: true
      }
    ];
  }

  private seedJobs(): DownloadJob[] {
    return [
      {
        id: 'job-synthetic',
        source: 'synthetic',
        status: 'ready',
        detail: t('Coorte sintética de 80 × 200 usada como molde do estudo mockado.'),
        artifacts: [
          { label: t('Metadata'), path: 'results/raw/synthetic/metadata.tsv' },
          { label: 'ASV', path: 'results/raw/synthetic/asv_table.tsv' },
          { label: t('Taxonomia'), path: 'results/raw/synthetic/taxonomy.tsv' }
        ],
        mocked: true,
        createdAt: '2026-02-11 18:02'
      },
      {
        id: 'job-emp',
        source: 'emp',
        status: 'queued',
        detail: t('Subconjunto EMP, filtro de bioma terrestre, teto de 200 amostras.'),
        artifacts: [],
        mocked: true,
        createdAt: '2026-02-12 08:16'
      }
    ];
  }

  private jobFromRequest(request: DownloadRequest, status: DownloadJob['status']): DownloadJob {
    const stamp = new Date().toISOString().slice(0, 16).replace('T', ' ');
    if (request.source === 'mgnify' && !request.studyAccession?.trim()) {
      return {
        id: `job-${Date.now()}`,
        source: request.source,
        status: 'failed',
        detail: t('study_accession é obrigatório.'),
        artifacts: [],
        mocked: true,
        createdAt: stamp
      };
    }
    if (request.source === 'sra' && !request.accessions?.length) {
      return {
        id: `job-${Date.now()}`,
        source: request.source,
        status: 'failed',
        detail: t('A lista de accessions é obrigatória.'),
        artifacts: [],
        mocked: true,
        createdAt: stamp
      };
    }
    return {
      id: `job-${Date.now()}`,
      source: request.source,
      status,
      detail: t('Pedido mockado para {dir}. Nenhum arquivo remoto foi baixado.', { dir: request.outputDir }),
      artifacts: [
        { label: 'Manifesto', path: `${request.outputDir.replace(/\/$/, '')}/manifest.tsv` }
      ],
      mocked: true,
      createdAt: stamp
    };
  }
}

function compositionRows(
  rows: { name: string; values: Record<string, number> }[],
  groups: string[],
  topN: number
): { name: string; values: Record<string, number> }[] {
  const named = rows.filter((row) => !row.name.startsWith('Outros')).slice(0, topN);
  const rest = {
    name: 'Outros',
    values: Object.fromEntries(
      groups.map((group) => {
        const used = named.reduce((sum, row) => sum + (row.values[group] ?? 0), 0);
        return [group, Math.round((100 - used) * 10) / 10];
      })
    )
  };
  return [...named, rest];
}

function statusRank(sample: MockSample): number {
  if (sample.status === 'fail') {
    return 0;
  }
  if (sample.status === 'warn') {
    return 1;
  }
  return 2;
}
