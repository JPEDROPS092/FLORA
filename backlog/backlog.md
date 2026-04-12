## FLORA Python Library — Backlog Operacional

---

### Visao Arquitetural

```
[QIIME2 / DADA2]
      |
[Export: BIOM / TSV]
      |
[DuckDB + Parquet — core analytics layer]
      |
[Feature Engineering SQL + Python/Polars]
      |
[ML Pipeline (sklearn / xgboost / SHAP)]
      |
[Visualizacao + Relatorio HTML]
```

**Decisoes arquiteturais fixadas:**
- Storage: Parquet (raw e intermediario) via PyArrow
- Query layer: DuckDB in-process
- Processamento tabular: Polars (alto desempenho)
- ML: Python puro (sklearn, xgboost)
- Tracking: MLflow
- Pipeline QIIME 2: SDK Python

---

### Status Geral

- [x] EP-01 -- Infraestrutura e Fundacao
- [x] EP-02 -- Aquisicao e Validacao de Dados
- [x] EP-03 -- Pipeline QIIME 2 / DADA2
- [x] EP-04 -- Camada DuckDB (Analytics Core)
- [x] EP-05 -- Feature Engineering para ML
- [x] EP-06 -- Modulo de Machine Learning
- [x] EP-07 -- Visualizacao e Relatorios
- [x] EP-08 -- Testes, Documentacao e Publicacao

---

### EP-01 -- Infraestrutura e Fundacao

- [x] US-01 -- Estrutura de pacote Python (src/flora/) com modulos separados por dominio
- [x] US-02 -- pyproject.toml com dependencias, versao e metadados
- [x] US-03 -- Sistema de logging centralizado com niveis configuraveis
- [x] US-04 -- Excecoes customizadas (FloraError, PipelineError, ValidationError, DatabaseError)
- [x] US-05 -- Ambiente Conda isolado (environment.yml)
- [x] US-06 -- Sistema de configuracao via YAML (config.yaml)

---

### EP-02 -- Aquisicao e Validacao de Dados

- [x] US-07 -- Downloader EarthMicrobiome Project (EMP)
- [x] US-08 -- Downloader MGnify (EMBL-EBI REST API) com filtro por bioma
- [x] US-09 -- Downloader NCBI SRA via sra-tools
- [x] US-10 -- Validador de arquivos FASTQ
- [x] US-11 -- Validador de manifest QIIME 2
- [x] US-12 -- Validador de metadados

---

### EP-03 -- Pipeline QIIME 2 / DADA2

- [x] US-13 -- Importacao FASTQ para artefato QIIME 2
- [x] US-14 -- Inspecao de qualidade com DADA2
- [x] US-15 -- Denoising DADA2 (denoise-paired)
- [x] US-16 -- Classificador taxonomico SILVA 138
- [x] US-17 -- Alinhamento MAFFT + arvore FastTree
- [x] US-18 -- Diversidade alfa (Shannon, Faith PD, Observed Features, Chao1)
- [x] US-19 -- Diversidade beta (Bray-Curtis, UniFrac)
- [x] US-20 -- Exportacao .qza para Parquet + ingestao DuckDB

---

### EP-04 -- Camada DuckDB (Analytics Core)

- [x] US-21 -- FloraDB singleton com conexao DuckDB configuravel
- [x] US-22 -- Schema DDL (samples, asv, taxonomy, diversity_alpha, diversity_beta)
- [x] US-23 -- Ingestao BIOM/TSV -> Parquet -> DuckDB (formato long)
- [x] US-24 -- PIVOT helper (long -> wide) para feature matrix ML
- [x] US-25 -- Query helpers para agregacoes taxonomicas
- [x] US-26 -- Exportacao de queries para Parquet ou DataFrame
- [x] US-27 -- Slicing dinamico de dataset para ML

---

### EP-05 -- Feature Engineering para ML

- [x] US-28 -- Rarefacao com curva e selecao automatica de profundidade
- [x] US-29 -- Normalizacao CLR (Centered Log-Ratio)
- [x] US-30 -- TSS (Total Sum Scaling)
- [x] US-31 -- Reducao de dimensionalidade (PCoA, UMAP)
- [x] US-32 -- Selecao de features (variancia, correlacao, Random Forest)
- [x] US-33 -- Codificacao de variaveis de metadados

---

### EP-06 -- Modulo de Machine Learning

- [x] US-34 -- Pipeline de classificacao (Random Forest, SVM, XGBoost)
- [x] US-35 -- Clustering nao supervisionado (K-Means, HDBSCAN)
- [x] US-36 -- Regressao para predicao de indices de diversidade
- [x] US-37 -- Analise de importancia de features com SHAP
- [x] US-38 -- Busca de hiperparametros com Optuna
- [x] US-39 -- Avaliacao de vies de dados
- [x] US-40 -- Serializacao de modelos com MLflow

---

### EP-07 -- Visualizacao e Relatorios

- [x] US-41 -- Grafico de barras taxonomico empilhado (Plotly)
- [x] US-42 -- Heatmap de diversidade beta clusterizado
- [x] US-43 -- PCoA plot interativo
- [x] US-44 -- Curvas de rarefacao por amostra com IC 95%
- [x] US-45 -- Relatorio HTML completo auto-contido

---

### EP-08 -- Testes, Documentacao e Publicacao

- [x] US-46 -- Testes unitarios (pytest, cobertura > 80%)
- [x] US-47 -- Testes de integracao com DuckDB in-memory
- [x] US-48 -- Documentacao (NumPy docstrings + MkDocs)
- [x] US-49 -- Publicacao no PyPI (pyproject.toml + twine)
- [x] US-50 -- Jupyter Notebook tutorial com dataset EMP amazonico

---

### Dependencias entre Epicos

```
EP-01 -> EP-02 -> EP-03 -> EP-04 (DuckDB) -> EP-05 -> EP-06
                                                  |        |
                                                EP-07 <---+
                                                  |
                                                EP-08
```

### Notas Tecnicas

- ASV em formato long (sample_id, feature_id, abundance) para queries analiticas
- PIVOT SQL nativo do DuckDB para feature matrix wide
- CLR: pseudo-count para zeros, geometric mean via SQL, log-ratio em numpy
- DuckDB in-memory em todos os testes
- Polars para transformacoes tabulares de alto desempenho
- Nunca commitar arquivos .duckdb no repositorio
