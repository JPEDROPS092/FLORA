import { AgentDefinition } from './agent.models';
import { t } from '../i18n/i18n';

export const AGENTS: readonly AgentDefinition[] = [
  {
    id: 'analyst',
    name: t('Analista de diversidade'),
    icon: 'pi pi-chart-scatter',
    role: t('Diversidade alfa/beta e comparação de grupos'),
    description: t('Lê as métricas por grupo, aponta diferenças e abre a vista certa no Explorer.'),
    tools: ['exploration.alpha', 'exploration.beta', 'explorer.set_filters'],
    starters: [t('Compare a diversidade entre os grupos'), t('Quais táxons diferem entre rizosfera e solo?')]
  },
  {
    id: 'qc',
    name: t('Auditor de qualidade'),
    icon: 'pi pi-shield',
    role: t('QC de amostras e ingestão'),
    description: t('Revisa profundidade de leitura, amostras sem metadata e bloqueios da ingestão.'),
    tools: ['pipeline.qc_table', 'dashboard.quality', 'pipeline.open_step'],
    starters: [t('Quais amostras falharam no QC?'), t('A ingestão está pronta para confirmar?')]
  },
  {
    id: 'taxonomist',
    name: t('Taxonomista & ML'),
    icon: 'pi pi-microchip',
    role: t('Táxons diferenciais e modelos'),
    description: t('Resume táxons diferenciais e compara modelos treinados, com ressalvas de validação.'),
    tools: ['exploration.differential', 'ml.comparison', 'ml.open_lab'],
    starters: [t('Qual modelo está melhor e com que ressalvas?'), t('Resuma os táxons diferenciais')]
  },
  {
    id: 'reporter',
    name: t('Redator científico'),
    icon: 'pi pi-file-edit',
    role: t('Seções e métodos do relatório'),
    description: t('Verifica seções incluídas, parâmetros e lacunas antes da exportação.'),
    tools: ['report.draft', 'report.parameters', 'report.open_builder'],
    starters: [t('O relatório está completo para exportar?'), t('Liste os parâmetros que entram em Métodos')]
  }
];

export const AUTO_ROUTES: { agent: AgentDefinition['id']; pattern: RegExp }[] = [
  { agent: 'qc', pattern: /qc|qualidade|qualit|falh|fail|leitura|reads|ingest|metadata|amostra|sample/i },
  { agent: 'reporter', pattern: /relat|report|m[eé]todo|methods|exportar|export/i },
  { agent: 'taxonomist', pattern: /modelo|model|ml|random|xgboost|shap|roc|diferenc|differential|t[aá]xon|taxon|fold/i },
  { agent: 'analyst', pattern: /divers|shannon|alfa|alpha|beta|pcoa|grupo|group|simpson|chao/i }
];

export function agentById(id: AgentDefinition['id']): AgentDefinition {
  return AGENTS.find((a) => a.id === id) ?? AGENTS[0];
}
