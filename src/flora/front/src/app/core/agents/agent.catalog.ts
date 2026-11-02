import { AgentDefinition } from './agent.models';

export const AGENTS: readonly AgentDefinition[] = [
  {
    id: 'analyst',
    name: 'Analista de diversidade',
    icon: 'pi pi-chart-scatter',
    role: 'Diversidade alfa/beta e comparação de grupos',
    description: 'Lê as métricas por grupo, aponta diferenças e abre a vista certa no Explorer.',
    tools: ['exploration.alpha', 'exploration.beta', 'explorer.set_filters'],
    starters: ['Compare a diversidade entre os grupos', 'Quais táxons diferem entre rizosfera e solo?']
  },
  {
    id: 'qc',
    name: 'Auditor de qualidade',
    icon: 'pi pi-shield',
    role: 'QC de amostras e ingestão',
    description: 'Revisa profundidade de leitura, amostras sem metadata e bloqueios da ingestão.',
    tools: ['pipeline.qc_table', 'dashboard.quality', 'pipeline.open_step'],
    starters: ['Quais amostras falharam no QC?', 'A ingestão está pronta para confirmar?']
  },
  {
    id: 'taxonomist',
    name: 'Taxonomista & ML',
    icon: 'pi pi-microchip',
    role: 'Táxons diferenciais e modelos',
    description: 'Resume táxons diferenciais e compara modelos treinados, com ressalvas de validação.',
    tools: ['exploration.differential', 'ml.comparison', 'ml.open_lab'],
    starters: ['Qual modelo está melhor e com que ressalvas?', 'Resuma os táxons diferenciais']
  },
  {
    id: 'reporter',
    name: 'Redator científico',
    icon: 'pi pi-file-edit',
    role: 'Seções e métodos do relatório',
    description: 'Verifica seções incluídas, parâmetros e lacunas antes da exportação.',
    tools: ['report.draft', 'report.parameters', 'report.open_builder'],
    starters: ['O relatório está completo para exportar?', 'Liste os parâmetros que entram em Métodos']
  }
];

export const AUTO_ROUTES: { agent: AgentDefinition['id']; pattern: RegExp }[] = [
  { agent: 'qc', pattern: /qc|qualidade|qualit|falh|fail|leitura|reads|ingest|metadata|amostra/i },
  { agent: 'reporter', pattern: /relat|report|m[eé]todo|methods|exportar|export/i },
  { agent: 'taxonomist', pattern: /modelo|model|ml|random|xgboost|shap|roc|diferenc|differential|t[aá]xon|taxon|fold/i },
  { agent: 'analyst', pattern: /divers|shannon|alfa|alpha|beta|pcoa|grupo|group|simpson|chao/i }
];

export function agentById(id: AgentDefinition['id']): AgentDefinition {
  return AGENTS.find((a) => a.id === id) ?? AGENTS[0];
}
