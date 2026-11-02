import { DifferentialTaxon, NormalizationConfig, Provenance, TaxonNode } from '../../models/domain';
import { t } from '../../i18n/i18n';

export const STUDY_ID = 'FL16S-SORGHUM-01';
export const STUDY_NAME = t('Rizosfera de sorgo sob seca');
export const ASV_COUNT = 1842;
export const RAREFACTION_DEPTH = 10000;

export const GROUP_COLOR: Record<string, string> = {
  Rhizosphere: '#155E53',
  'Bulk soil': '#C47B2B',
  Endosphere: '#3D6B8C'
};

export interface MockSample {
  id: string;
  metadataId: string;
  group: string | null;
  host: string;
  site: string;
  reads: number | null;
  inMetadata: boolean;
  inAsv: boolean;
  shannon: number;
  simpson: number;
  observed: number;
  chao1: number;
  pc1: number;
  pc2: number;
  status: 'pass' | 'warn' | 'fail';
  issues: string[];
}

interface AbundanceRow {
  name: string;
  rank: 'phylum' | 'genus';
  values: Record<string, number>;
}

const SITES = ['Sete Lagoas', 'Janaúba', 'Rio Verde'];

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export const METADATA_COLUMNS = [
  'sample_id',
  'group',
  'host',
  'site',
  'collection_date',
  'sequencing_depth',
  'replicate'
];

export const PHYLA: AbundanceRow[] = [
  { name: 'Pseudomonadota', rank: 'phylum', values: { Rhizosphere: 28, 'Bulk soil': 18, Endosphere: 36 } },
  { name: 'Bacillota', rank: 'phylum', values: { Rhizosphere: 22, 'Bulk soil': 9, Endosphere: 18 } },
  { name: 'Actinomycetota', rank: 'phylum', values: { Rhizosphere: 16, 'Bulk soil': 11, Endosphere: 9 } },
  { name: 'Bacteroidota', rank: 'phylum', values: { Rhizosphere: 11, 'Bulk soil': 8, Endosphere: 14 } },
  { name: 'Acidobacteriota', rank: 'phylum', values: { Rhizosphere: 7, 'Bulk soil': 24, Endosphere: 3 } },
  { name: 'Verrucomicrobiota', rank: 'phylum', values: { Rhizosphere: 5, 'Bulk soil': 14, Endosphere: 4 } },
  { name: 'Chloroflexota', rank: 'phylum', values: { Rhizosphere: 4, 'Bulk soil': 10, Endosphere: 2 } },
  { name: 'Outros', rank: 'phylum', values: { Rhizosphere: 7, 'Bulk soil': 6, Endosphere: 14 } }
];

export const GENERA: AbundanceRow[] = [
  { name: 'Pseudomonas', rank: 'genus', values: { Rhizosphere: 9.4, 'Bulk soil': 2.1, Endosphere: 4.8 } },
  { name: 'Bacillus', rank: 'genus', values: { Rhizosphere: 7.6, 'Bulk soil': 1.8, Endosphere: 3.2 } },
  { name: 'Streptomyces', rank: 'genus', values: { Rhizosphere: 4.1, 'Bulk soil': 3.4, Endosphere: 1.1 } },
  { name: 'Sphingomonas', rank: 'genus', values: { Rhizosphere: 2.2, 'Bulk soil': 6.8, Endosphere: 1.4 } },
  { name: 'Bradyrhizobium', rank: 'genus', values: { Rhizosphere: 3.8, 'Bulk soil': 2.9, Endosphere: 0.6 } },
  { name: 'Methylobacterium', rank: 'genus', values: { Rhizosphere: 1.1, 'Bulk soil': 0.4, Endosphere: 6.9 } },
  { name: 'Burkholderia', rank: 'genus', values: { Rhizosphere: 3.3, 'Bulk soil': 1.2, Endosphere: 2.7 } },
  { name: 'Acidibacter', rank: 'genus', values: { Rhizosphere: 0.8, 'Bulk soil': 4.9, Endosphere: 0.3 } },
  { name: 'Rhizobium', rank: 'genus', values: { Rhizosphere: 2.9, 'Bulk soil': 1.1, Endosphere: 0.9 } },
  { name: 'Massilia', rank: 'genus', values: { Rhizosphere: 1.7, 'Bulk soil': 2.4, Endosphere: 1.2 } },
  { name: 'Pedobacter', rank: 'genus', values: { Rhizosphere: 1.4, 'Bulk soil': 1.6, Endosphere: 2.8 } },
  { name: t('Outros gêneros'), rank: 'genus', values: { Rhizosphere: 61.7, 'Bulk soil': 71.4, Endosphere: 74.1 } }
];

export const RANK_TABLE: Record<string, AbundanceRow[]> = {
  phylum: PHYLA,
  class: [
    { name: 'Gammaproteobacteria', rank: 'phylum', values: { Rhizosphere: 24, 'Bulk soil': 14, Endosphere: 31 } },
    { name: 'Bacilli', rank: 'phylum', values: { Rhizosphere: 18, 'Bulk soil': 7, Endosphere: 14 } },
    { name: 'Actinobacteria', rank: 'phylum', values: { Rhizosphere: 14, 'Bulk soil': 10, Endosphere: 8 } },
    { name: 'Alphaproteobacteria', rank: 'phylum', values: { Rhizosphere: 12, 'Bulk soil': 16, Endosphere: 18 } },
    { name: 'Bacteroidia', rank: 'phylum', values: { Rhizosphere: 9, 'Bulk soil': 8, Endosphere: 11 } },
    { name: 'Acidobacteriae', rank: 'phylum', values: { Rhizosphere: 6, 'Bulk soil': 20, Endosphere: 2 } },
    { name: 'Outras classes', rank: 'phylum', values: { Rhizosphere: 17, 'Bulk soil': 25, Endosphere: 16 } }
  ],
  order: [
    { name: 'Pseudomonadales', rank: 'phylum', values: { Rhizosphere: 14, 'Bulk soil': 4, Endosphere: 8 } },
    { name: 'Rhizobiales', rank: 'phylum', values: { Rhizosphere: 11, 'Bulk soil': 9, Endosphere: 12 } },
    { name: 'Bacillales', rank: 'phylum', values: { Rhizosphere: 12, 'Bulk soil': 4, Endosphere: 6 } },
    { name: 'Burkholderiales', rank: 'phylum', values: { Rhizosphere: 8, 'Bulk soil': 6, Endosphere: 7 } },
    { name: 'Streptomycetales', rank: 'phylum', values: { Rhizosphere: 5, 'Bulk soil': 4, Endosphere: 2 } },
    { name: 'Outras ordens', rank: 'phylum', values: { Rhizosphere: 50, 'Bulk soil': 73, Endosphere: 65 } }
  ],
  family: [
    { name: 'Pseudomonadaceae', rank: 'phylum', values: { Rhizosphere: 11, 'Bulk soil': 3, Endosphere: 6 } },
    { name: 'Bacillaceae', rank: 'phylum', values: { Rhizosphere: 9, 'Bulk soil': 3, Endosphere: 4 } },
    { name: 'Sphingomonadaceae', rank: 'phylum', values: { Rhizosphere: 4, 'Bulk soil': 9, Endosphere: 3 } },
    { name: 'Methylobacteriaceae', rank: 'phylum', values: { Rhizosphere: 2, 'Bulk soil': 1, Endosphere: 8 } },
    { name: 'Streptomycetaceae', rank: 'phylum', values: { Rhizosphere: 5, 'Bulk soil': 4, Endosphere: 2 } },
    { name: t('Outras famílias'), rank: 'phylum', values: { Rhizosphere: 69, 'Bulk soil': 80, Endosphere: 77 } }
  ],
  genus: GENERA
};

export const DIFFERENTIAL: DifferentialTaxon[] = [
  { taxon: 'Pseudomonas', rank: 'genus', log2FoldChange: 1.82, pValue: 0.0004, qValue: 0.004, higherIn: 'Rhizosphere', contrast: 'Rhizosphere vs Bulk soil' },
  { taxon: 'Bacillus', rank: 'genus', log2FoldChange: 1.41, pValue: 0.0011, qValue: 0.008, higherIn: 'Rhizosphere', contrast: 'Rhizosphere vs Bulk soil' },
  { taxon: 'Sphingomonas', rank: 'genus', log2FoldChange: -1.64, pValue: 0.0008, qValue: 0.006, higherIn: 'Bulk soil', contrast: 'Rhizosphere vs Bulk soil' },
  { taxon: 'Acidibacter', rank: 'genus', log2FoldChange: -2.05, pValue: 0.0002, qValue: 0.003, higherIn: 'Bulk soil', contrast: 'Rhizosphere vs Bulk soil' },
  { taxon: 'Methylobacterium', rank: 'genus', log2FoldChange: 2.21, pValue: 0.0001, qValue: 0.002, higherIn: 'Endosphere', contrast: 'Endosphere vs Rhizosphere' },
  { taxon: 'Bradyrhizobium', rank: 'genus', log2FoldChange: 0.92, pValue: 0.012, qValue: 0.041, higherIn: 'Rhizosphere', contrast: 'Rhizosphere vs Endosphere' },
  { taxon: 'Pseudomonadota', rank: 'phylum', log2FoldChange: 0.74, pValue: 0.008, qValue: 0.028, higherIn: 'Endosphere', contrast: 'Endosphere vs Bulk soil' },
  { taxon: 'Acidobacteriota', rank: 'phylum', log2FoldChange: -1.48, pValue: 0.0006, qValue: 0.005, higherIn: 'Bulk soil', contrast: 'Rhizosphere vs Bulk soil' },
  { taxon: 'Bacillota', rank: 'phylum', log2FoldChange: 1.12, pValue: 0.003, qValue: 0.014, higherIn: 'Rhizosphere', contrast: 'Rhizosphere vs Bulk soil' }
];

export const TAXON_TREE: TaxonNode[] = [
  {
    key: 'p-pseudo',
    label: 'Pseudomonadota · 27%',
    rank: 'phylum',
    abundance: 27,
    children: [
      {
        key: 'c-gamma',
        label: 'Gammaproteobacteria · 18%',
        rank: 'class',
        abundance: 18,
        children: [
          { key: 'g-pseudo', label: 'Pseudomonas · 5,4%', rank: 'genus', abundance: 5.4 },
          { key: 'g-burk', label: 'Burkholderia · 2,4%', rank: 'genus', abundance: 2.4 }
        ]
      },
      {
        key: 'c-alpha',
        label: 'Alphaproteobacteria · 9%',
        rank: 'class',
        abundance: 9,
        children: [
          { key: 'g-sphing', label: 'Sphingomonas · 3,5%', rank: 'genus', abundance: 3.5 },
          { key: 'g-brady', label: 'Bradyrhizobium · 2,4%', rank: 'genus', abundance: 2.4 },
          { key: 'g-meth', label: 'Methylobacterium · 2,8%', rank: 'genus', abundance: 2.8 }
        ]
      }
    ]
  },
  {
    key: 'p-bac',
    label: 'Bacillota · 16%',
    rank: 'phylum',
    abundance: 16,
    children: [
      {
        key: 'c-bacilli',
        label: 'Bacilli · 13%',
        rank: 'class',
        abundance: 13,
        children: [{ key: 'g-bacillus', label: 'Bacillus · 4,2%', rank: 'genus', abundance: 4.2 }]
      }
    ]
  },
  {
    key: 'p-act',
    label: 'Actinomycetota · 12%',
    rank: 'phylum',
    abundance: 12,
    children: [
      {
        key: 'c-act',
        label: 'Actinobacteria · 10%',
        rank: 'class',
        abundance: 10,
        children: [{ key: 'g-strep', label: 'Streptomyces · 2,9%', rank: 'genus', abundance: 2.9 }]
      }
    ]
  },
  {
    key: 'p-acid',
    label: 'Acidobacteriota · 11%',
    rank: 'phylum',
    abundance: 11,
    children: [
      {
        key: 'c-acid',
        label: 'Acidobacteriae · 9%',
        rank: 'class',
        abundance: 9,
        children: [{ key: 'g-acid', label: 'Acidibacter · 2,0%', rank: 'genus', abundance: 2 }]
      }
    ]
  }
];

const RELATION_LABELS = [
  'Pseudomonas',
  'Bacillus',
  'Streptomyces',
  'Sphingomonas',
  'Bradyrhizobium',
  'Methylobacterium',
  'Burkholderia',
  'Acidibacter'
];

const RELATION_MATRIX = [
  [1, 0.62, 0.18, -0.41, 0.33, -0.12, 0.47, -0.36],
  [0.62, 1, 0.22, -0.28, 0.19, -0.08, 0.31, -0.24],
  [0.18, 0.22, 1, 0.11, 0.26, -0.05, 0.09, 0.14],
  [-0.41, -0.28, 0.11, 1, 0.07, -0.16, -0.22, 0.58],
  [0.33, 0.19, 0.26, 0.07, 1, -0.21, 0.16, -0.04],
  [-0.12, -0.08, -0.05, -0.16, -0.21, 1, 0.12, -0.31],
  [0.47, 0.31, 0.09, -0.22, 0.16, 0.12, 1, -0.18],
  [-0.36, -0.24, 0.14, 0.58, -0.04, -0.31, -0.18, 1]
];

export function relationMatrix(topN: number): { labels: string[]; matrix: number[][] } {
  const n = Math.max(2, Math.min(topN, RELATION_LABELS.length));
  return {
    labels: RELATION_LABELS.slice(0, n),
    matrix: RELATION_MATRIX.slice(0, n).map((row) => row.slice(0, n))
  };
}

export function createSamples(): MockSample[] {
  const rand = mulberry32(16);
  const plan = [
    { group: 'Rhizosphere', n: 28, shannon: 4.55, shannonSd: 0.28, simpson: 0.86, observed: 310, pc1: 0.26, pc2: 0.04 },
    { group: 'Bulk soil', n: 27, shannon: 5.32, shannonSd: 0.22, simpson: 0.93, observed: 430, pc1: -0.22, pc2: 0.16 },
    { group: 'Endosphere', n: 25, shannon: 3.28, shannonSd: 0.34, simpson: 0.74, observed: 175, pc1: 0.02, pc2: -0.28 }
  ];
  const samples: MockSample[] = [];
  let index = 1;
  for (const group of plan) {
    for (let offset = 0; offset < group.n; offset += 1) {
      const id = `FL16S_${String(index).padStart(3, '0')}`;
      const observed = Math.round(group.observed + (rand() - 0.5) * 70);
      samples.push({
        id,
        metadataId: id,
        group: group.group,
        host: 'Sorghum bicolor',
        site: SITES[index % SITES.length],
        reads: Math.round(16000 + rand() * 26000),
        inMetadata: true,
        inAsv: true,
        shannon: round(group.shannon + (rand() - 0.5) * group.shannonSd * 2),
        simpson: round(Math.min(0.99, Math.max(0.45, group.simpson + (rand() - 0.5) * 0.06)), 3),
        observed,
        chao1: Math.round(observed * (1.08 + rand() * 0.1)),
        pc1: round(group.pc1 + (rand() - 0.5) * 0.16, 3),
        pc2: round(group.pc2 + (rand() - 0.5) * 0.14, 3),
        status: 'pass',
        issues: []
      });
      index += 1;
    }
  }

  const byId = (id: string) => samples.find((sample) => sample.id === id);

  const low = byId('FL16S_014');
  if (low) {
    low.reads = 640;
    low.status = 'fail';
    low.issues = [t('Profundidade 640 reads, abaixo da rarefação de 10.000.')];
  }
  const missingAsv = byId('FL16S_031');
  if (missingAsv) {
    missingAsv.inAsv = false;
    missingAsv.reads = null;
    missingAsv.status = 'fail';
    missingAsv.issues = [t('Presente na metadata e ausente na tabela ASV.')];
  }
  const missingMeta = byId('FL16S_052');
  if (missingMeta) {
    missingMeta.inMetadata = false;
    missingMeta.group = null;
    missingMeta.status = 'fail';
    missingMeta.issues = [t('Presente na tabela ASV e ausente na metadata.')];
  }
  const borderline = byId('FL16S_067');
  if (borderline) {
    borderline.reads = 8200;
    borderline.status = 'warn';
    borderline.issues = [t('Profundidade 8.200 reads, abaixo do limiar de rarefação.')];
  }
  const mismatch = byId('FL16S_078');
  if (mismatch) {
    mismatch.metadataId = 'FL16S_78';
    mismatch.status = 'fail';
    mismatch.issues = [t('Identificador da metadata (FL16S_78) não corresponde a FL16S_078.')];
  }

  return samples;
}

export function analyzableSamples(samples: MockSample[], groups: string[], depth: number): MockSample[] {
  return samples.filter(
    (sample) =>
      sample.status === 'pass' &&
      sample.inAsv &&
      sample.inMetadata &&
      sample.group !== null &&
      (groups.length === 0 || groups.includes(sample.group)) &&
      (sample.reads ?? 0) >= depth
  );
}

export function baseProvenance(seed = 42): Provenance {
  return {
    pipelineVersion: 'flora 0.4.2',
    seed,
    parameters: [
      { label: 'Marcador', value: '16S V4 (515F/806R)' },
      { label: 'QIIME2', value: '2024.10' },
      { label: 'DADA2 truncLen', value: '240 / 200' },
      { label: 'DADA2 maxEE', value: '2' },
      { label: 'Classificador', value: 'SILVA 138.2, sklearn' },
      { label: t('Rarefação'), value: '10.000 reads' },
      { label: t('Transformação'), value: 'CLR' },
      { label: t('Prevalência mínima'), value: '0,05' },
      { label: t('Distância beta'), value: 'Bray–Curtis' },
      { label: 'Seed', value: String(seed) }
    ],
    packages: [
      { name: 'FLORA', version: '0.4.2' },
      { name: 'QIIME2', version: '2024.10' },
      { name: 'DADA2', version: '1.32' },
      { name: 'SILVA', version: '138.2' },
      { name: 'scikit-learn', version: '1.5.2' },
      { name: 'XGBoost', version: '2.1.1' }
    ],
    inputs: [
      'results/raw/FL16S-SORGHUM-01/metadata.tsv',
      'results/raw/FL16S-SORGHUM-01/asv_table.tsv',
      'results/raw/FL16S-SORGHUM-01/taxonomy.tsv'
    ],
    history: [
      { at: '2026-02-12 09:14', event: t('Importação FASTQ e metadata (QIIME2).') },
      { at: '2026-02-12 09:41', event: t('DADA2 denoise: 1.842 ASVs, 80 amostras.') },
      { at: '2026-02-12 10:05', event: t('Taxonomia SILVA 138.2 atribuída.') },
      { at: '2026-02-12 10:22', event: t('QC: 75 amostras passam; 4 falham; 1 alerta.') },
      { at: '2026-02-12 11:03', event: t('Rarefação a 10.000 e matriz CLR.') }
    ]
  };
}

export function defaultNormalization(): NormalizationConfig {
  return {
    rarefactionDepth: RAREFACTION_DEPTH,
    method: 'clr',
    minPrevalence: 0.05,
    minAbundance: 10
  };
}

export const MOCK_LOGS = [
  t('2026-02-12 09:14:02 INFO flora.ui — Estudo mockado FL16S-SORGHUM-01 carregado (80 amostras, 1.842 ASVs).'),
  '2026-02-12 09:41:18 INFO flora.dada2 — truncLenF=240 truncLenR=200 maxEE=2 pool=pseudo.',
  '2026-02-12 10:05:44 INFO flora.taxonomy — SILVA 138.2, 1.842 features classificadas.',
  '2026-02-12 10:22:09 WARNING flora.qc — FL16S_014 profundidade 640.',
  t('2026-02-12 10:22:09 WARNING flora.qc — FL16S_031 ausente na tabela ASV.'),
  t('2026-02-12 10:22:10 WARNING flora.qc — FL16S_052 ausente na metadata.'),
  '2026-02-12 10:22:10 WARNING flora.qc — FL16S_067 profundidade 8.200.',
  '2026-02-12 10:22:11 ERROR flora.qc — FL16S_078 identificador divergente (FL16S_78).',
  t('2026-02-12 11:03:27 INFO flora.features — rarefação 10000, CLR, prevalência 0.05 → 612 features.'),
  '2026-02-12 11:18:55 INFO flora.ml — random_forest seed=42 cv=5 accuracy=0.86.',
  '2026-02-12 11:24:12 INFO flora.ml — xgboost seed=42 cv=5 accuracy=0.88.',
  t('2026-02-12 11:40:00 INFO flora.report — rascunho HTML do relatório científico disponível.')
];
