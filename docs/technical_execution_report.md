# Relatorio Tecnico de Execucao do Projeto

Este documento registra, de forma objetiva, o que esta sendo feito no projeto FLORA no estado atual da biblioteca, com foco em execucao da pipeline, ingestao dos dados do EMP, artefatos gerados e diferencas entre os fluxos disponiveis.

## 1. Escopo do Trabalho Atual

No estado atual do projeto, voce esta executando quatro linhas principais de trabalho:

- consolidacao da biblioteca Python `flora` como nucleo do projeto;
- validacao da pipeline real com dados do Earth Microbiome Project (EMP);
- geracao de relatorios tecnicos e figuras para uso academico;
- refinamento da camada de visualizacao, documentacao e relatorio institucional.

Em termos praticos, isso significa que o projeto deixou de ser apenas um prototipo conceitual e ja opera como biblioteca analitica local com:

- ingestao de `metadata.tsv`, `asv_table.tsv`, `taxonomy.tsv` e BIOM;
- armazenamento em DuckDB;
- calculo de diversidade alfa e beta;
- geracao de matriz de features para machine learning;
- treinamento supervisionado com XGBoost;
- exportacao de relatorios HTML, Markdown, PNG e documentacao MkDocs.

## 2. Dados em Uso

Os dados utilizados no experimento principal atual estao em:

- `data/raw/emp/metadata.tsv`
- `data/raw/emp/asv_table.tsv`
- `data/raw/emp/taxonomy.tsv`
- `data/raw/emp/emp_deblur_150bp.release1.biom`

Esses arquivos compoem o subconjunto EMP usado para:

- ingestao via CLI padrao do FLORA;
- ingestao via exemplo analitico dedicado `examples/emp_analysis.py`;
- geracao de figuras e relatorio para o PIBIC.

## 3. Execucoes Realizadas

### 3.1 Execucao da CLI padrao

Foi tentada inicialmente a execucao:

```bash
flora run config.yaml --workdir results/ --sampling-depth 5000
```

Essa execucao falhou porque a CLI padrao busca, por default, os arquivos em `data/raw/`, e nao em `data/raw/emp/`.

Erro observado:

- `File not found: data/raw/asv_table.tsv`
- `File not found: data/raw/taxonomy.tsv`

Em seguida, a execucao correta foi feita explicitando os caminhos:

```bash
flora run config.yaml \
  --metadata  data/raw/emp/metadata.tsv \
  --asv-table data/raw/emp/asv_table.tsv \
  --taxonomy  data/raw/emp/taxonomy.tsv
```

### 3.2 Resultado da CLI padrao

Essa execucao concluiu com sucesso e produziu:

- 89 amostras ingeridas;
- 28.857 observacoes ASV;
- 197.711 linhas taxonomicas;
- diversidade calculada para 67 amostras com profundidade 10.000;
- matriz de features final com 87 amostras e 623 ASVs;
- banco `results/flora.duckdb`.

Interpretacao tecnica:

- a CLI padrao cumpre bem o papel de ingestao, diversidade e montagem da matriz;
- ela nao executa o fluxo completo de relatorio analitico do EMP;
- por usar `sampling_depth=10000`, ela descarta mais amostras na etapa de rarefacao.

## 4. Execucao do Pipeline Analitico EMP

O fluxo principal de analise foi executado com:

```bash
python examples/emp_analysis.py
```

Esse script nao e apenas um exemplo simples. No estado atual do projeto, ele funciona como pipeline analitica expandida para:

- ingestao dos dados EMP;
- construcao de matriz CLR;
- filtragem por prevalencia;
- selecao das classes `empo_3` para classificacao;
- treino/teste com XGBoost;
- calculo de diversidade;
- geracao de graficos;
- exportacao de relatorio HTML e Markdown.

## 5. Resultado do Experimento EMP

Os resultados observados no experimento atual foram:

| Indicador | Valor |
| --- | --- |
| Amostras totais ingeridas | 89 |
| Amostras usadas no modelo | 85 |
| Observacoes ASV | 28.857 |
| Taxonomias carregadas | 197.711 |
| Features apos filtro de prevalencia | 1.183 |
| Train | 63 |
| Test | 22 |
| Accuracy | 0.8636 |
| F1-macro | 0.6381 |
| ROC-AUC | 0.9510 |
| Alpha samples | 79 |
| Beta distances | 3916 |

Interpretacao:

- a biblioteca ja consegue executar um fluxo microbioma-para-ML completo em dados reais;
- o `ROC-AUC` alto mostra boa separacao global entre classes;
- o `F1-macro` mais baixo indica efeito do desbalanceamento entre classes;
- o filtro por prevalencia expandiu o espaco de features para 1.183 atributos no experimento EMP dedicado, acima das 623 ASVs do fluxo mais simples da CLI.

## 6. Diferenca Entre os Dois Fluxos

### `flora run`

Esse fluxo e mais enxuto e institucional:

- ingestao de metadados, ASV e taxonomia;
- calculo de diversidade;
- geracao de matriz de features;
- persistencia no DuckDB.

Ele e util para:

- validar rapidamente se os dados entram na base;
- montar banco e matriz de trabalho;
- usar a biblioteca de forma mais padrao.

### `examples/emp_analysis.py`

Esse fluxo e mais completo e orientado a relatorio:

- usa a base EMP como estudo de caso reproduzivel;
- aplica CLR e filtro por prevalencia;
- seleciona classes ambientais especificas;
- treina modelo XGBoost;
- calcula SHAP quando o ambiente permite;
- gera figuras estaticas e interativas;
- escreve `results/emp_report.html`;
- escreve `docs/emp_report.md`.

Ele e util para:

- demonstracao cientifica do projeto;
- producao de material para PIBIC;
- avaliacao de desempenho do pipeline ponta a ponta.

## 7. Problemas e Alertas Encontrados

### 7.1 Caminhos padrao da CLI

Problema:

- a CLI assume `data/raw/` como diretorio default.

Impacto:

- quando os dados estao em `data/raw/emp/`, a execucao falha sem os argumentos `--metadata`, `--asv-table` e `--taxonomy`.

Conclusao:

- esse comportamento esta coerente com a implementacao, mas precisa ser documentado com clareza para o usuario.

### 7.2 Rarefacao remove amostras

Mensagens observadas:

- `Dropping 22 samples with depth < 10000 (24.7% of total)` na CLI;
- `Dropping 10 samples with depth < 5000 (11.2% of total)` no experimento EMP.

Interpretacao:

- a escolha da profundidade de rarefacao altera diretamente o numero de amostras retidas;
- isso afeta diversidade alfa e comparabilidade entre execucoes.

### 7.3 Warning do XGBoost

Warning observado:

- `Parameters: { "use_label_encoder" } are not used.`

Interpretacao:

- nao bloqueia a execucao;
- indica parametro legado ou desnecessario na versao atual do XGBoost;
- convem limpar isso no codigo para reduzir ruído operacional.

### 7.4 Warnings do Matplotlib no exemplo EMP

Warning observado:

- `Tight layout not applied.`

Interpretacao:

- os artefatos foram gerados, mas alguns graficos estaticos ainda estao no limite do layout;
- isso nao quebra o pipeline, apenas indica necessidade de polimento visual adicional.

### 7.5 SHAP no ambiente local

No ambiente atual, o SHAP pode gerar erro por incompatibilidade entre:

- `numpy 2.x`
- `cv2`
- binarios compilados de dependencias antigas

Impacto:

- o pipeline segue funcional;
- a etapa de explicabilidade precisa de ambiente mais limpo para ficar totalmente robusta.

## 8. Artefatos Gerados

Os artefatos principais gerados no estado atual do projeto sao:

### Banco e resultados

- `results/flora.duckdb`
- `results/emp_flora.duckdb`
- `results/emp_report.html`

### Relatorios em Markdown

- `docs/emp_report.md`
- `docs/graph_guide.md`
- `docs/report.md`
- `docs/pibic_relatorio_parcial.tex`

### Figuras

Diretorio:

- `docs/assets/emp/`

Arquivos principais:

- `pcoa_braycurtis.png`
- `alpha_shannon.png`
- `alpha_chao1.png`
- `beta_heatmap.png`
- `taxonomy_barplot.png`
- `taxonomy_heatmap.png`
- `roc_curve.png`
- `confusion_matrix.png`
- `feature_importance.png`
- `shap_summary.png`

Tambem existem versoes `.html` interativas para inspecao detalhada.

## 9. O Que Ja Esta Pronto

No estado atual, ja estao prontos:

- biblioteca instalada e funcional;
- CLI operacional;
- ingestao de dados EMP;
- banco DuckDB populado;
- pipeline analitica completa de exemplo;
- graficos tecnicos para relatorio;
- markdown analitico em `docs/`;
- LaTeX base para o relatorio parcial;
- MkDocs com navegacao para os principais documentos.

## 10. O Que Ainda Faz Sentido Melhorar

As proximas melhorias mais relevantes sao:

- remover warning do XGBoost;
- melhorar layout final de alguns PNGs estaticos;
- tornar o fluxo `flora run` mais amigavel para datasets em subpastas;
- estabilizar ambiente de SHAP;
- aumentar cobertura de testes para fazer o `pytest` padrao passar tambem com `cov-fail-under`;
- integrar automaticamente os resultados do EMP ao texto final do relatorio PIBIC.

## 11. Conclusao Tecnica

No estado atual, o que voce esta fazendo no projeto nao e mais apenas desenvolvimento exploratorio. Voce ja esta:

- validando uma biblioteca cientifica funcional;
- executando pipelines em dados reais;
- gerando evidencias quantitativas de desempenho;
- produzindo material de documentacao e relatorio academico;
- aproximando o projeto de uma entrega cientifica reprodutivel.

Em termos de maturidade, o FLORA ja opera como biblioteca analitica real, com um fluxo coerente de dados, visualizacao e relatorio. O trabalho restante e majoritariamente de polimento, estabilidade de ambiente e refinamento metodologico.

