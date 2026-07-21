# FLORA — Prompt de Construção da Interface (UI) para Agente

> **Tipo de tarefa:** construção de front-end / interface web.
> **Escopo:** *somente a UI*. Não implementar, alterar ou reescrever nenhum algoritmo,
> modelo estatístico ou lógica de processamento do FLORA.
> **Base:** cobrir **todas as capacidades de todos os módulos** da plataforma (abaixo),
> e **não** apenas replicar a interface atual.
> **Direção visual:** enterprise, séria, tema **azul escuro (navy)**.

---

## 1. Missão

Você é responsável por projetar e construir a **camada de interface** de uma plataforma
enterprise de análise de microbioma (dados de amplicon 16S rRNA e metagenômica). A UI é
uma aplicação web que dá acesso, de forma organizada e auditável, a **todo o ciclo de
vida da análise**: aquisição de dados públicos, validação, ingestão, engenharia de
atributos, diversidade ecológica, machine learning, otimização, avaliação,
explicabilidade, visualização, geração de relatórios e orquestração de pipeline.

A interface deve permitir que um pesquisador conduza qualquer módulo **isoladamente** ou
como parte de um **fluxo completo**, sempre com parâmetros ajustáveis e feedback claro de
estado.

---

## 2. Escopo e fronteiras

**Dentro do escopo (fazer):**

- Toda a camada visual: layout, navegação, componentes, formulários, tabelas, painéis de
  visualização, estados de carregamento/erro/vazio, notificações.
- Formulários que exponham **todos os parâmetros** de cada módulo (seção 5 e 6).
- Consumo da API JSON do backend (contrato na seção 7) via chamadas assíncronas.
- Renderização das figuras retornadas pelo backend (gráficos interativos) e das tabelas
  de métricas/resultados.
- Design system completo em tema azul escuro (seção 8), responsivo e acessível.

**Fora do escopo (não fazer):**

- Não escrever/alterar lógica de download, transformação, cálculo de diversidade,
  treinamento de modelos, SHAP, otimização, geração de relatório no backend.
- Não criar novos endpoints de negócio nem mudar o esquema do banco.
- Não hardcodar resultados: todo dado exibido vem da API.
- Se um endpoint necessário ainda não existir, **declare a suposição** de contrato
  (formato de request/response esperado) em vez de implementar o backend.

---

## 3. Princípios de UX

- **Fluxo guiado + acesso livre:** um caminho recomendado (aquisição → ingestão →
  atributos → diversidade → ML → relatório) coexiste com navegação direta a qualquer
  módulo.
- **Parametrização à vista:** cada parâmetro relevante do módulo é um controle no
  formulário, com valor padrão pré-preenchido, faixa/validação e texto de ajuda.
- **Feedback de estado obrigatório:** toda ação assíncrona tem estados *idle → carregando
  → sucesso/erro*, sem telas mudas.
- **Rastreabilidade:** a UI exibe proveniência (fonte, nº de amostras, parâmetros
  aplicados, data) sempre que disponível.
- **Duas camadas de leitura:** resumo escaneável no topo, detalhe técnico abaixo.
- **Consciência composicional:** onde a normalização importa (ex.: correlações,
  diversidade), a UI orienta o usuário sobre a transformação aplicada.

---

## 4. Mapa de navegação (derivado dos módulos)

A UI é organizada nas seções abaixo. **Cada seção mapeia capacidades reais de módulos** —
não a interface atual.

| # | Seção | Módulos de origem |
|---|-------|-------------------|
| 1 | **Painel / Status** | pipeline, db, config |
| 2 | **Configuração** | `config` (FloraConfig completo) |
| 3 | **Aquisição de dados** | `io.downloaders` (MGnify, NCBI SRA, ENA, EMP) |
| 4 | **Validação** | `io.validators` (FASTQ, manifesto, metadados) |
| 5 | **Ingestão** | `db.ingestion` (BIOM, ASV TSV, metadados, taxonomia, catálogo) |
| 6 | **Explorador do banco** | `db.connection`, `utils.inspect_db` (esquema, tabelas, contagens) |
| 7 | **Engenharia de atributos** | `feature_engineering` (normalização, redução, seleção, codificação) |
| 8 | **Diversidade** | `diversity` (alfa e beta) |
| 9 | **Machine Learning** | `ml.classification`, `ml.regression`, `ml.clustering` |
| 10 | **Otimização** | `ml.optimization` (tuner Optuna) |
| 11 | **Avaliação & Viés** | `ml.evaluation` (métricas, qualidade das partições) |
| 12 | **Explicabilidade** | `ml.explainability` (SHAP) |
| 13 | **Visualizações** | `viz` (taxonomia, diversidade, ML) |
| 14 | **Relatórios** | `reports.html_report` (FLORAReport) |
| 15 | **Pipeline** | `pipelines.main_pipeline` (execução encadeada) |

---

## 5. Especificação por seção

Para **cada** seção: cabeçalho com título + descrição curta, cartões de formulário com os
parâmetros listados, botão de ação primária, e área de resultado (tabela/figura/relatório
+ estados).

### 5.1 Painel / Status
- **Objetivo:** visão geral do estado atual da plataforma.
- **Exibir:** indicador de conexão do backend; métricas do banco (nº de amostras,
  nº de features/ASVs, nº de táxons, métricas de diversidade calculadas); progresso das
  etapas do pipeline (metadados → ASV → taxonomia → diversidade → ML) com selo
  *pendente / em progresso / concluído*.
- **Ações:** atualizar status; atalhos para as próximas etapas sugeridas.

### 5.2 Configuração (parametrização global)
Formulário editável para **todo o `FloraConfig`**, agrupado por área. Persistir/carregar
(YAML) e validar faixas. Campos:

- **Banco:** caminho do banco (arquivo ou memória), nº de threads (≥1), limite de memória
  (ex.: `4GB`), modo somente-leitura.
- **Pipeline:** truncamento forward/reverse, trim esquerdo forward/reverse, nº de threads,
  confiança da taxonomia (0–1), profundidade de rarefação.
- **Machine learning:** proporção de teste (0–1), semente aleatória, nº de folds de
  validação cruzada (≥2), paralelismo (`-1` = todos os núcleos), nº de trials de
  otimização, URI de rastreamento de experimentos.
- **Logging:** nível (DEBUG/INFO/WARNING/ERROR/CRITICAL), arquivo de log (opcional),
  saída rica on/off.
- **Armazenamento:** diretórios de dados brutos, Parquet, resultados e classificadores.

### 5.3 Aquisição de dados
Abas por fonte, cada uma com seus parâmetros e retorno de manifesto/relatório de download:

- **MGnify:** filtro de bioma (ex.: `root:Environmental:Terrestrial:Forest`), accession do
  estudo, nº máximo de amostras, diretório de saída.
- **NCBI SRA:** lista de accessions (`SRR…`, uma por linha), diretório de saída.
- **ENA:** accessions/estudo, diretório de saída.
- **Earth Microbiome Project (EMP):** seleção do subconjunto/portal, diretório de saída.
- Comum: verificação de integridade do download (tamanho, código de resposta) e
  geração de manifesto compatível; exibir tabela do manifesto resultante.

### 5.4 Validação
- **Objetivo:** checar integridade e conformidade **antes** de processar; coletar todos os
  problemas de uma vez.
- **Modos:** validar FASTQ, validar manifesto, validar metadados.
- **Entradas:** caminho(s) de arquivo, coluna de identificador de amostra, esquema
  esperado.
- **Saída:** *ValidationReport* renderizado como lista de achados com severidade
  (ok / aviso / erro), contagens e mensagens acionáveis.

### 5.5 Ingestão
Cartões por tipo de fonte, todos carregando para o armazém analítico:

- **Tabela ASV:** BIOM **ou** TSV (com opção formato largo/longo); coluna de identificador.
- **Metadados:** TSV/CSV; coluna de identificador de amostra.
- **Taxonomia:** atribuições (ex.: SILVA / Greengenes2).
- **Catálogo de download:** ingerir um diretório baixado (auto-detectar a fonte a partir
  dos accessions) populando catálogo + arquivos + amostras.
- **Saída:** nº de linhas/amostras registradas, com opção de materialização Parquet
  reutilizável.

### 5.6 Explorador do banco
- **Objetivo:** inspeção read-only do armazém.
- **Exibir:** lista de tabelas do esquema estrela (dimensão de amostras, fato de
  observações ASV, taxonomia, diversidade alfa/beta, redução de dimensionalidade),
  colunas, chaves, contagens de linhas e amostra de dados.
- **Ações:** selecionar tabela → pré-visualizar linhas; diagnóstico de integridade.

### 5.7 Engenharia de atributos
Sub-áreas, cada uma com controles próprios:

- **Normalização:** método (soma total / log-razão centrada / bruto); pseudo-contagem;
  **rarefação** (profundidade); **sugerir profundidade** automaticamente; gerar **curva de
  rarefação**.
- **Seleção de atributos:** por **variância** (limiar), por **prevalência** (limiar), por
  **importância** (Random Forest / SHAP, nº de atributos).
- **Redução de dimensionalidade:** **PCoA** e **UMAP** (nº de componentes, semente,
  métrica de distância) → coordenadas por amostra.
- **Codificação de metadados:** conversão de colunas categóricas/ordinais em numéricas
  (label / ordinal).
- **Saída:** matriz de atributos resultante (pré-visualização) e embeddings para plotar.

### 5.8 Diversidade
- **Alfa:** seleção múltipla de métricas (riqueza/observadas, Shannon, Chao1, Simpson,
  Pielou…), profundidade de rarefação opcional → tabela por amostra + gráfico.
- **Beta:** métrica de dissimilaridade (ex.: Bray-Curtis) → matriz de distância +
  ordenação; ligar às variáveis de metadado.

### 5.9 Machine Learning
Abas por tarefa, interface consistente (mesma forma para trocar estimador sem fricção):

- **Classificação:** estimador (Random Forest / SVM / XGBoost), coluna-alvo, esquema de
  validação cruzada estratificada, semente → *ClassificationResult* (métricas, matriz de
  confusão).
- **Regressão:** estimador (Random Forest / Ridge), alvo contínuo (ex.: índice de
  diversidade), validação cruzada → métricas (R², erro) + gráfico observado vs. previsto.
- **Clustering:** algoritmo (K-Means / HDBSCAN), fonte (matriz de atributos ou embedding
  PCoA/UMAP), nº de clusters/params → rótulos + métricas de qualidade (Silhouette,
  Davies-Bouldin) + dispersão colorida por cluster.

### 5.10 Otimização de hiperparâmetros
- **Objetivo:** busca bayesiana (TPE) sobre qualquer classificador/regressor.
- **Controles:** tarefa/estimador alvo, nº de trials, métrica-objetivo, espaço de busca,
  orçamento de tempo.
- **Saída:** melhores hiperparâmetros (persistíveis) + histórico/curva de otimização;
  botão para aplicar os parâmetros no formulário de ML.

### 5.11 Avaliação & Viés
- **Métricas:** avaliação de classificação e de regressão em detalhe.
- **Qualidade das partições (antes do treino):** *DataQualityReport* com desequilíbrio de
  classes, potencial vazamento e qualidade do split, apresentado como painel de
  diagnósticos com severidade.

### 5.12 Explicabilidade
- **Objetivo:** explicar o modelo treinado (TreeExplainer para árvores; fallback
  Kernel).
- **Saída:** importância global e por amostra; resumo dos atributos mais influentes com
  espaço para leitura biológica; gráfico de resumo SHAP.

### 5.13 Visualizações
Galeria unificada que renderiza as figuras do backend (interativas, com exportação
estática opcional):

- **Taxonomia:** barplot de composição; heatmap.
- **Diversidade:** PCoA; curvas de rarefação; alfa; heatmap de beta.
- **ML:** matriz de confusão; importância de atributos; dispersão de clusters; observado
  vs. previsto (regressão).
- Cada figura: seletor de parâmetros (nível taxonômico, agrupamento por metadado, etc.),
  título, e botão de exportar.

### 5.14 Relatórios
- **Objetivo:** montar um relatório **auto-contido** que abre sem dependências externas.
- **Controles:** selecionar seções a incluir (sumário, proveniência, configuração
  aplicada, qualidade dos dados, diversidade, modelagem, explicabilidade,
  reprodutibilidade), formato das figuras, destino do arquivo.
- **Saída:** link/preview do relatório gerado; a UI monta a composição, o backend gera.

### 5.15 Pipeline (orquestração)
- **Objetivo:** rodar o fluxo completo ou etapas selecionadas.
- **Controles:** seleção de etapas (ingestão → atributos → diversidade → ML → relatório),
  configuração aplicada, semente global.
- **Saída:** progresso por etapa (estado + tempo), com estado persistido a cada passo e
  possibilidade de retomar/rodar parcialmente.

---

## 6. Padrões de formulário e parametrização

- Todo parâmetro tem **valor padrão** visível (usar os defaults do `FloraConfig`), texto
  de ajuda curto e validação (faixas numéricas, obrigatoriedade, formato).
- Parâmetros numéricos com faixa mostram limites; seleções múltiplas para métricas;
  campos de caminho com placeholder realista.
- Um **resumo de parâmetros aplicados** acompanha cada resultado (para rastreabilidade).
- Nada de valores fixos escondidos na lógica da UI: se precisa ser decidido, é um controle.

---

## 7. Contrato com o backend (a UI consome, não implementa)

A UI é uma **aplicação de página única (SPA)** que fala com uma **API JSON** por chamadas
assíncronas. Assuma um contrato REST-like por módulo; onde um endpoint ainda não existir,
**documente o formato esperado** em vez de criar o backend. Padrão geral:

- `GET /api/status` → estado do pipeline e estatísticas do banco.
- `GET /api/db/*` → esquema, tabelas, contagens, amostras de linha.
- `POST /api/download/{mgnify|sra|ena|emp}` → dispara aquisição; retorna manifesto.
- `POST /api/validate/{fastq|manifest|metadata}` → retorna *ValidationReport*.
- `POST /api/ingest/{metadata|asv|taxonomy|catalog}` → nº de registros ingeridos.
- `GET /api/feature_matrix` → matriz (bruto / soma total / log-razão centrada).
- `POST /api/features/{normalize|rarefy|select|reduce|encode}` → resultado + preview.
- `POST /api/diversity/{alpha|beta}` → tabelas/matrizes de diversidade.
- `POST /api/ml/{classify|regress|cluster}` → resultado + métricas.
- `POST /api/optimize` → melhores hiperparâmetros + histórico.
- `POST /api/evaluate/{classification|regression|split_quality}` → relatório.
- `POST /api/explain` → importâncias SHAP.
- `GET /api/viz/*` → especificação de figura interativa (JSON).
- `POST /api/report` → gera relatório auto-contido.
- `POST /api/pipeline/run` → executa etapas selecionadas; retorna progresso.

**Regras de consumo:** requisições assíncronas; tratamento uniforme de erro (mensagem do
backend exibida em toast/painel); CORS/OPTIONS respeitados; nunca bloquear a UI durante
operações longas (mostrar progresso).

---

## 8. Design system — tema azul escuro (navy)

Comprometer com **tema escuro navy único**, sério e enterprise (não invertido de um tema
claro). Tokens sugeridos (ajuste com bom gosto, mantendo contraste AA):

**Cores**
- Fundo base: `#081221` · superfícies: `#0f2140` / `#12294d`
- Bordas: `#1d3860` · texto: `#e8eefb` / secundário `#aebfdc` / suave `#7d92b6`
- Accent primário: `#4f92ff` · secundário/ciano: `#38c0f0`
- Semânticas (separadas do accent): sucesso `#3ecf8e`, aviso `#e8b04b`, erro `#f26d6d`

**Tipografia**
- Títulos: uma serifada de peso (ar enterprise/editorial), usada com moderação.
- Corpo: sans legível (largura ~65 caracteres em textos longos).
- Dados/números: fonte monoespaçada com `tabular-nums` em tabelas.

**Layout & componentes**
- Navegação lateral fixa + área de conteúdo com largura máxima confortável.
- Cartões para formulários e resultados; cantos suaves; sombra sutil.
- Componentes obrigatórios: botões (primário/secundário/perigo), inputs/select/textarea,
  abas, tabelas com scroll horizontal próprio (`overflow-x:auto`), *badges* de status,
  *toasts*, modais, *skeletons* de carregamento, estados vazios ilustrados, barra de
  progresso por etapa.
- Cor semântica ≠ accent: severidade (ok/aviso/erro) tem cor própria.

---

## 9. Estados universais (obrigatórios em toda ação)

- **Idle:** formulário pronto, defaults preenchidos.
- **Carregando:** botão desabilitado + indicador; skeleton na área de resultado.
- **Sucesso:** resultado renderizado + resumo de parâmetros aplicados + toast.
- **Vazio:** mensagem orientando a próxima ação (ex.: "ingira dados para habilitar").
- **Erro:** mensagem do backend, o que deu errado e como corrigir — sem jargão nem culpa.

---

## 10. Acessibilidade e responsividade

- Contraste mínimo AA em texto e controles no tema escuro.
- Foco de teclado visível em todos os interativos; navegação por teclado nas abas e menus.
- Respeitar `prefers-reduced-motion` (sem animações agressivas).
- Layout responsivo: a navegação colapsa em telas estreitas; o corpo nunca rola na
  horizontal (conteúdo largo rola dentro do próprio contêiner).
- Rótulos associados a inputs; textos de ajuda vinculados; mensagens de erro anunciáveis.

---

## 11. Critérios de aceite (checklist)

- [ ] Todas as 15 seções presentes e navegáveis.
- [ ] Cada módulo expõe **todos** os seus parâmetros como controles com defaults e ajuda.
- [ ] Toda ação assíncrona tem os 5 estados (idle/carregando/sucesso/vazio/erro).
- [ ] Figuras e tabelas renderizadas a partir da resposta da API (nenhum dado fixo).
- [ ] Resumo de parâmetros aplicados acompanha cada resultado (rastreabilidade).
- [ ] Tema azul escuro consistente, com cores semânticas separadas do accent.
- [ ] Responsivo, acessível (AA, foco visível, teclado, reduced-motion).
- [ ] Nenhuma lógica de backend/algoritmo foi criada ou alterada.
- [ ] Endpoints ausentes documentados como contrato esperado, não implementados.

---

## 12. Entregável

Uma interface web completa (SPA) que cubra todos os módulos acima, no tema azul escuro,
consumindo a API do FLORA, com todos os estados e a parametrização exposta — acompanhada
de uma nota curta listando quaisquer contratos de endpoint assumidos.
