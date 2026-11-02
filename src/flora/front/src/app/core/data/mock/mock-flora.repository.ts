import { environment } from '../../../../environments/environment';
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
  ProjectDraft,
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

const SOURCE: DataSourceInfo = {
  mode: 'mock',
  label: 'FL16S-SORGHUM-01 · 80 amostras · 1.842 ASVs',
  apiBaseUrl: environment.apiBaseUrl,
  mocked: true
};

const LIMITATIONS = [
  'n = 80 e três classes: a acurácia interna não substitui um conjunto externo.',
  'A divisão registrada nos filtros não é executada como SQL no mock; o holdout é estratificado pela seed.',
  'CLR em contagens esparsas de 16S comprime zeros e pode inflar correlações.',
  'SHAP e importância descrevem o modelo, não um efeito biológico causal.',
  'Amostras abaixo de 10.000 reads foram excluídas antes do treino.'
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
      datasetName: 'Ainda sem dataset',
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
      this.localStep('metadata', request.metadataPath, request.metadataPath ? `${this.samples.length} amostras lidas` : ''),
      this.localStep('asv', request.asvPath, request.asvPath ? `${ASV_COUNT} ASVs no formato ${request.wideFormat ? 'largo' : 'longo'}` : ''),
      this.localStep(
        'taxonomy',
        request.taxonomyPath === 'fail-taxonomy' ? '' : request.taxonomyPath,
        request.taxonomyPath && request.taxonomyPath !== 'fail-taxonomy' ? `${ASV_COUNT} linhas de taxonomia` : ''
      )
    ];
    if (request.taxonomyPath === 'fail-taxonomy') {
      steps[2] = { step: 'taxonomy', success: false, error: 'Falha simulada na taxonomia (caminho fail-taxonomy).' };
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
        ? { status: 'empty', error: 'Nenhuma amostra passou nos filtros e na rarefação.' }
        : await settleChart(async () => pcoaScatter(analyzed)),
      alpha: empty
        ? { status: 'error', error: 'Diversidade alfa exige amostras acima do limiar de rarefação.' }
        : await settleChart(async () => alphaBox(analyzed, query.metric)),
      beta: empty
        ? { status: 'empty', error: 'Matriz beta vazia para estes grupos.' }
        : await settleChart(async () => betaHeatmap(analyzed)),
      taxonomy: await settleChart(async () => taxonomyBar(rankRows, groups, query.rank)),
      relations: await settleChart(async () => relationHeatmap(query.topN)),
      tree: TAXON_TREE,
      comparisons: this.compare(analyzed),
      differential,
      distanceNote:
        query.distance === 'jaccard'
          ? 'Jaccard (mock) segue a mesma ordenação; a escala exibida é Bray–Curtis de demonstração.'
          : 'Bray–Curtis de demonstração, coerente com a separação no PCoA. Não é a matriz 80×80.',
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
      return this.failedExperiment(request, 'train_filter e test_filter são obrigatórios.');
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
      warnings: request.format === 'pdf' ? ['O PDF textual não incorpora as figuras; elas estão no HTML.'] : [],
      mocked: true
    };
  }

  async downloads(): Promise<DownloadJob[]> {
    await wait();
    return this.jobs.map((job) => ({ ...job }));
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
        { id: 'import', tool: 'QIIME2', name: 'Importar', detail: 'FASTQ Casava 1.8 + metadata', status: 'complete' },
        { id: 'cutadapt', tool: 'QIIME2', name: 'Primers', detail: 'cutadapt 515F/806R', status: 'complete' },
        { id: 'dada2', tool: 'DADA2', name: 'Denoise', detail: 'truncLen 240/200 · maxEE 2', status: 'complete' },
        { id: 'taxonomy', tool: 'QIIME2', name: 'Taxonomia', detail: 'SILVA 138.2', status: 'complete' },
        {
          id: 'table',
          tool: 'FLORA',
          name: 'Tabela',
          detail: `${this.samples.length} amostras · ${ASV_COUNT} ASVs`,
          status: preview.summary.lowDepth + preview.summary.metadataOnly + preview.summary.asvOnly > 0 ? 'attention' : 'complete'
        },
        {
          id: 'norm',
          tool: 'FLORA',
          name: 'Normalizar',
          detail: `Rarefação ${this.normalization.rarefactionDepth} · ${method}`,
          status: this.ingested ? 'complete' : 'pending'
        }
      ]
    };
  }

  private buildPreview(request: IngestRequest): IngestPreview {
    const columns = request.metadataColumns?.length ? request.metadataColumns : METADATA_COLUMNS;
    const warnings: string[] = ['Estudo mockado FL16S-SORGHUM-01. Os arquivos enviados não substituem a coorte de demonstração.'];
    if (request.metadataColumns?.length && !request.metadataColumns.includes(request.sampleColumn)) {
      warnings.push(`A coluna "${request.sampleColumn}" não está no cabeçalho enviado.`);
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
      { label: 'Filtro de treino', value: request?.trainFilter || "site != 'Janaúba'" },
      { label: 'Filtro de teste', value: request?.testFilter || "site = 'Janaúba'" },
      { label: 'CV', value: String(request?.cvFolds ?? 5) },
      { label: 'Normalização', value: (request?.normalize ?? 'clr').toUpperCase() }
    ];
    provenance.history = [
      ...provenance.history,
      { at: '2026-02-12 11:18', event: `Treino ${model}, seed ${seed}.` }
    ];
    return {
      id: `exp-${model}-${seed}-${offset}`,
      name: model === 'xgboost' ? 'XGBoost · grupo' : 'Random Forest · grupo',
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
      title: 'FL16S-SORGHUM-01 · diversidade e predição de compartimento',
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
          title: 'Resumo',
          included: true,
          figure: null,
          narrative:
            'O estudo mockado FL16S-SORGHUM-01 compara rizosfera, solo bulk e endosfera de Sorghum bicolor (80 amostras, 1.842 ASVs, marcador 16S V4). Após o controle de qualidade, 75 amostras permanecem acima de 10.000 reads. A ordenação separa os três compartimentos e a diversidade de Shannon é maior no solo bulk.',
          table: {
            columns: ['Grupo', 'n', 'Shannon', 'ASVs observados'],
            rows: comparisons.map((row) => [row.group, String(row.n), `${row.shannonMean} ± ${row.shannonSd}`, String(row.observedMean)])
          }
        },
        {
          id: 'methods',
          title: 'Métodos',
          included: true,
          figure: null,
          narrative:
            'As leituras foram importadas no QIIME2 2024.10, os primers 515F/806R removidos com cutadapt e as sequências denoiseadas no DADA2 (truncLen 240/200, maxEE 2). A taxonomia usou SILVA 138.2. A tabela foi rarefeita a 10.000 reads. A matriz para ordenação e modelos foi transformada por CLR com prevalência mínima de 5%. Beta-diversidade: Bray–Curtis e PCoA. Modelos: Random Forest e XGBoost, seed 42, validação cruzada de 5 dobras. Os valores são de demonstração.',
          table: null
        },
        {
          id: 'alpha',
          title: 'Diversidade alfa',
          included: true,
          figure: 'alpha',
          narrative: 'Shannon, Simpson, ASVs observados e Chao1 foram calculados depois da rarefação. O solo bulk concentra a maior riqueza; a endosfera é a comunidade mais restrita.',
          table: null
        },
        {
          id: 'beta',
          title: 'Diversidade beta',
          included: true,
          figure: 'pcoa',
          narrative: 'O PCoA (Bray–Curtis) separa endosfera, rizosfera e solo bulk no primeiro plano (PC1 28,4%, PC2 14,1%). A matriz exibida é um recorte coerente com essa ordenação.',
          table: null
        },
        {
          id: 'taxonomy',
          title: 'Composição',
          included: true,
          figure: 'taxonomy',
          narrative:
            'Pseudomonas e Bacillus são enriquecidos na rizosfera. Acidibacter e Sphingomonas predominam no solo bulk. Methylobacterium marca a endosfera. Os contrastes usam log2 fold change e q-value de um teste mockado.',
          table: {
            columns: ['Táxon', 'log2FC', 'q', 'Maior em'],
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
            ? `O melhor experimento interno (${best.model}) alcançou acurácia ${best.accuracy.toFixed(2)}, F1 macro ${best.f1Macro.toFixed(2)} e ROC AUC ${best.rocAuc?.toFixed(2)}. A importância é SHAP médio e não deve ser lida como mecanismo.`
            : 'Nenhum modelo concluído.',
          table: null
        },
        {
          id: 'parameters',
          title: 'Parâmetros reprodutíveis',
          included: true,
          figure: 'shap',
          narrative: 'Seed, versões e limiares abaixo acompanham qualquer reexecução. Trocar a rarefação ou a transformação altera a matriz e invalida a comparação direta.',
          table: {
            columns: ['Parâmetro', 'Valor'],
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
        name: 'QC de amostras',
        kind: 'ingest',
        status: 'completed',
        finishedAt: '2026-02-12 10:22',
        projectId: 'sorghum-drought',
        summary: '75 passam, 1 alerta, 4 falham.',
        provenance
      },
      {
        id: 'run-alpha',
        name: 'Diversidade alfa',
        kind: 'alpha',
        status: 'completed',
        finishedAt: '2026-02-12 11:06',
        projectId: 'sorghum-drought',
        summary: 'Shannon após rarefação a 10.000.',
        provenance
      },
      {
        id: 'run-pcoa',
        name: 'PCoA Bray–Curtis',
        kind: 'beta',
        status: 'completed',
        finishedAt: '2026-02-12 11:09',
        projectId: 'sorghum-drought',
        summary: 'Três compartimentos no primeiro plano.',
        provenance
      },
      ...this.experimentStore.slice(0, 2).map((experiment) => ({
        id: experiment.id,
        name: experiment.name,
        kind: 'ml',
        status: experiment.status,
        finishedAt: experiment.createdAt,
        projectId: 'sorghum-drought',
        summary: `Acurácia ${experiment.accuracy.toFixed(2)} · F1 ${experiment.f1Macro.toFixed(2)}`,
        provenance: experiment.provenance
      }))
    ];
  }

  private seedProjects(): ResearchProject[] {
    return [
      {
        id: 'sorghum-drought',
        name: 'Sorgo sob seca',
        question: 'O compartimento radicular prediz a composição de ASVs melhor do que o sítio?',
        status: 'active',
        datasetName: STUDY_NAME,
        marker: '16S V4',
        samples: 80,
        asvs: ASV_COUNT,
        groups: ['Rhizosphere', 'Bulk soil', 'Endosphere'],
        analyses: [
          { id: 'a1', name: 'Alfa e PCoA', kind: 'diversity', status: 'completed' },
          { id: 'a2', name: 'Táxons diferenciais', kind: 'taxonomy', status: 'completed' },
          { id: 'a3', name: 'Random Forest e XGBoost', kind: 'ml', status: 'completed' }
        ],
        results: [
          { id: 'r1', title: 'Separação de compartimentos', summary: 'PCoA Bray–Curtis separa os três grupos no PC1–PC2.' },
          { id: 'r2', title: 'Predição de grupo', summary: 'XGBoost interno: acurácia 0,88, F1 macro 0,86.' }
        ],
        updatedAt: '2026-02-12 11:40',
        mocked: true
      },
      {
        id: 'cerrado-chrono',
        name: 'Cronossequência de Cerrado',
        question: 'A idade de regeneração desloca Acidobacteriota no solo superficial?',
        status: 'archived',
        datasetName: 'Cerrado chronosequence 16S',
        marker: '16S V4',
        samples: 46,
        asvs: 2104,
        groups: ['Pasture', 'Early', 'Late'],
        analyses: [{ id: 'c1', name: 'PCoA', kind: 'beta', status: 'completed' }],
        results: [{ id: 'cr1', title: 'Gradiente de idade', summary: 'Late se aproxima do solo de referência.' }],
        updatedAt: '2025-11-03 16:12',
        mocked: true
      },
      {
        id: 'atl-endo',
        name: 'Endófitos de Mata Atlântica',
        question: 'Folha e pecíolo compartilham o mesmo núcleo de Methylobacterium?',
        status: 'draft',
        datasetName: 'Ainda sem tabela',
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
        detail: 'Coorte sintética de 80 × 200 usada como molde do estudo mockado.',
        artifacts: [
          { label: 'Metadata', path: 'results/raw/synthetic/metadata.tsv' },
          { label: 'ASV', path: 'results/raw/synthetic/asv_table.tsv' },
          { label: 'Taxonomia', path: 'results/raw/synthetic/taxonomy.tsv' }
        ],
        mocked: true,
        createdAt: '2026-02-11 18:02'
      },
      {
        id: 'job-emp',
        source: 'emp',
        status: 'queued',
        detail: 'Subconjunto EMP, filtro de bioma terrestre, teto de 200 amostras.',
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
        detail: 'study_accession é obrigatório.',
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
        detail: 'A lista de accessions é obrigatória.',
        artifacts: [],
        mocked: true,
        createdAt: stamp
      };
    }
    return {
      id: `job-${Date.now()}`,
      source: request.source,
      status,
      detail: `Pedido mockado para ${request.outputDir}. Nenhum arquivo remoto foi baixado.`,
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
