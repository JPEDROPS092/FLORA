import { t } from '../core/i18n/i18n';
export interface TechItem {
  name: string;
  /** file in /icons; omitted → monogram badge (no brand icon available) */
  icon?: string;
  mono?: string;
  note: string;
  url: string;
}
export interface TechGroup { title: string; blurb: string; items: TechItem[] }

export interface Institution {
  name: string;
  org: string;
  mono: string;
  color: string;
  role: string;
  url: string;
  /** optional official logo dropped in /branding/institutions (not bundled: trademarks) */
  logo?: string;
}

export const TECH_GROUPS: readonly TechGroup[] = [
  {
    title: t('Interface'),
    blurb: t('O workspace que você está vendo.'),
    items: [
      { name: 'Angular', icon: 'angular.svg', note: t('Framework da SPA: componentes standalone, signals e rotas.'), url: 'https://angular.dev' },
      { name: 'PrimeNG', icon: 'primeng.svg', note: t('Componentes de tabela, formulário, gaveta e diálogo, com tema próprio FLORA.'), url: 'https://primeng.org' },
      { name: 'TypeScript', icon: 'typescript.svg', note: t('Tipagem forte nos contratos entre UI, mock e API.'), url: 'https://www.typescriptlang.org' },
      { name: 'RxJS', icon: 'rxjs.svg', note: t('Fluxos reativos para rotas, status da API e eventos.'), url: 'https://rxjs.dev' },
      { name: 'Plotly', icon: 'plotly.svg', note: t('PCoA, diversidade, taxonomia e ROC interativos.'), url: 'https://plotly.com/javascript/' }
    ]
  },
  {
    title: t('Dados & estatística'),
    blurb: t('O núcleo analítico em Python.'),
    items: [
      { name: 'DuckDB', icon: 'duckdb.svg', note: t('Warehouse analítico embarcado: tabelas de ASV, metadata e taxonomia.'), url: 'https://duckdb.org' },
      { name: 'Polars', icon: 'polars.svg', note: t('DataFrames rápidos para transformar tabelas grandes.'), url: 'https://pola.rs' },
      { name: 'pandas', icon: 'pandas.svg', note: t('Manipulação tabular e compatibilidade com o ecossistema.'), url: 'https://pandas.pydata.org' },
      { name: 'NumPy', icon: 'numpy.svg', note: t('Álgebra de matrizes: CLR, distâncias e rarefação.'), url: 'https://numpy.org' },
      { name: 'SciPy', icon: 'scipy.svg', note: t('Testes estatísticos e distâncias beta (Bray–Curtis, Jaccard).'), url: 'https://scipy.org' },
      { name: 'Pydantic', icon: 'pydantic.svg', note: t('Validação de configuração e dos contratos da API.'), url: 'https://docs.pydantic.dev' }
    ]
  },
  {
    title: t('IA & aprendizado de máquina'),
    blurb: t('Modelos, explicabilidade e rastreio de experimentos.'),
    items: [
      { name: 'scikit-learn', icon: 'scikitlearn.svg', note: t('Random Forest, validação cruzada e métricas.'), url: 'https://scikit-learn.org' },
      { name: 'XGBoost', mono: 'XG', note: t('Gradient boosting para comparar com a Random Forest.'), url: 'https://xgboost.ai' },
      { name: 'SHAP', mono: 'SH', note: t('Explica quais táxons mais pesam em cada predição.'), url: 'https://shap.readthedocs.io' },
      { name: 'Optuna', icon: 'optuna.svg', note: t('Busca de hiperparâmetros reprodutível.'), url: 'https://optuna.org' },
      { name: 'MLflow', icon: 'mlflow.svg', note: t('Registro de parâmetros, métricas e artefatos de cada experimento.'), url: 'https://mlflow.org' }
    ]
  },
  {
    title: t('Pipeline de amplicons'),
    blurb: t('Ferramentas de referência citadas no Pipeline Studio.'),
    items: [
      { name: 'QIIME 2', mono: 'Q2', note: t('Plataforma de análise de microbioma; origem de muitos artefatos 16S.'), url: 'https://qiime2.org' },
      { name: 'DADA2', mono: 'D2', note: t('Denoising de amplicons em ASVs exatas.'), url: 'https://benjjneb.github.io/dada2/' },
      { name: 'BIOM', mono: 'BI', note: t('Formato de tabela de observações lido pelo FLORA.'), url: 'https://biom-format.org' },
      { name: 'Python', icon: 'python.svg', note: t('Linguagem do backend, CLI `flora` e servidor local.'), url: 'https://www.python.org' }
    ]
  }
];

export const INSTITUTIONS: readonly Institution[] = [
  { name: 'MGnify', org: 'EMBL-EBI', mono: 'EBI', color: '#1f7a5a', role: t('Estudos de amplicons e metagenomas já analisados; baixamos os resumos taxonômicos por accession (MGYS…).'), url: 'https://www.ebi.ac.uk/metagenomics/' },
  { name: 'SRA', org: 'NCBI · NIH/NLM', mono: 'NCBI', color: '#20558a', role: t('Maior repositório público de leituras brutas (FASTQ), via sra-tools.'), url: 'https://www.ncbi.nlm.nih.gov/sra' },
  { name: 'ENA', org: 'EMBL-EBI', mono: 'ENA', color: '#3a7d44', role: t('Alternativa automática quando o sra-tools não está instalado.'), url: 'https://www.ebi.ac.uk/ena/' },
  { name: 'Earth Microbiome Project', org: 'EMP · Qiita / UCSD', mono: 'EMP', color: '#8a5a12', role: t('Coleção padronizada de amostras globais, com tabelas Deblur 150 bp e metadata.'), url: 'https://earthmicrobiome.org' }
];
