# Auditoria do Repositório — Issue #2

**Data:** 2026-11-02 · **Branch auditada:** `main` (commit `ff7a65a`) · **Ambiente:** Windows 11, Python 3.13.16, Node 26.13.0, npm 11.20.0 (sem conda)

---

## 1. Sumário executivo

A biblioteca Python é **real e funcional**: 90 testes passam, o servidor `flora ui` sobe e responde, e os 13 endpoints HTTP documentados estão de fato implementados. O frontend Angular, por outro lado, é **somente scaffolding** — nenhum arquivo `.ts` existe no repositório, e o build falha por ausência de código-fonte. O maior risco encontrado está no empacotamento: **quatro bugs independentes no build (hatch/pyproject) quebravam qualquer `pip install` a partir do código-fonte**, todos corrigidos nesta auditoria (seção 3).

---

## 2. Baseline de build

### 2.1 Python — `pip install -e .`

| Tentativa | Resultado | Causa |
|-----------|-----------|-------|
| 1 (ambiente limpo) | ❌ `ImportError: BuilderHookInterface` | `hatch_build.py` importava classe de módulo/nome inexistentes no hatchling atual |
| 2 | ❌ `OSError: [WinError 193]` | Hook tentava executar `scripts/build_frontend.sh` (bash) diretamente no Windows; só `CalledProcessError` era capturado |
| 3 | ❌ `TypeError: exclude must be an array of strings` | `[tool.hatch.build.targets.wheel.exclude]` declarado como tabela chave→bool em vez de array |
| 4 | ❌ `FileNotFoundError: Forced include not found: .../front/dist` | `force-include` exige o `dist/` presente; sem frontend compilado o build morre (sem fallback, contrariando o próprio hook) |
| 5 (pós-correções) | ✅ **Sucesso** | Hook emite warning e segue; fallback para HTML embutido funciona |

**Correções aplicadas** (commit pendente de PR):
- `hatch_build.py:14` — `from hatchling.builders.hooks.plugin.interface import BuildHookInterface` (módulo e nome corretos).
- `hatch_build.py:55` — captura `(CalledProcessError, OSError)`: fallback com warning, sem abortar o build.
- `pyproject.toml` — `wheel.exclude` convertido para array de strings (mesmos padrões, mesma intenção).
- `pyproject.toml` — `force-include` substituído por `artifacts = ["src/flora/front/dist"]`: inclui o `dist/` (gitignored) no wheel quando existe, sem erro quando ausente. Removida a entrada redundante de `__init__.py` (já coberto por `packages`).

### 2.2 Testes

```
90 passed, 33 warnings em 278s
 Cobertura total: 50,76%  →  FALHA no gate --cov-fail-under=70 (pyproject.toml)
```

- **Funcional:** zero falhas. Fixtures determinísticas (seed 42), DuckDB in-memory.
- **Cobertura abaixo do gate configurado.** Maiores lacunas: `viz/*` (0% — 3 módulos, 207 linhas), `ui/server.py` (9%), `pipelines/main_pipeline.py` (24%), `ml/optimization/tuner.py` (24%), `ml/explainability/shap_analysis.py` (29%), `ml/evaluation/metrics.py` (36%).
- Decisão necessária (issue #15): elevar a cobertura desses módulos **ou** ajustar o gate para refletir a baseline real — não ambos sem registro.

### 2.3 Servidor `flora ui` (smoke test)

- `GET /` → 200, SPA HTML embutida (fallback, pois `front/dist` não existe).
- `GET /api/status` → 200, JSON com 12 tabelas inicializadas (`samples`, `asv`, `taxonomy`, `sample_catalog`, `pipeline_log`, …).

### 2.4 Frontend Angular

- `npm install` → ✅ (gerou `package-lock.json` — **novo arquivo não rastreado**, necessário para o `npm ci` do `scripts/build_frontend.sh`).
- `ng build` → ❌ `Could not resolve "src/main.ts"` / `"src/styles.css"` — **não existe diretório `src/flora/front/src/`**. Confirma: zero arquivos `.ts` no repositório.

---

## 3. Matriz de capacidades (código real × reuso)

| Módulo | Conteúdo real | Estado | Reuso no Studio |
|--------|---------------|--------|-----------------|
| `config` | `FloraConfig` (pydantic): database, pipeline, ml, logging, storage | ✅ completo | Tela de Configuração (#5/#7) |
| `core` | exceções, logging | ✅ completo | transversal |
| `db` | `FloraDB` (connect/query/pivot_asv/aggregate_by_taxon/slice/table_info), ingestion (BIOM/TSV/metadados/taxonomia/catálogo), schema 12 tabelas | ✅ completo | Explorador, Ingestão (#8/#9) |
| `io` | downloaders MGnify/SRA/EMP; validators FASTQ/manifest/metadata (`ValidationReport`) | ✅ completo | Aquisição, Validação (#8) — **validators sem endpoint HTTP** |
| `diversity` | alfa (shannon, observed, chao1, simpson…), beta | ✅ completo | Diversidade (#10) |
| `feature_engineering` | CLR/TSS/rarefy/curva, prevalência/variância/importância, PCoA/UMAP, encoding | ✅ completo | Feature Engineering (#10) — **só 1 endpoint expõe (`feature_matrix`)** |
| `ml` | classifier (RF/SVM/XGB), clusterer (KMeans/HDBSCAN), regressor, SHAP, Optuna tuner, métricas, viés (`DataQualityReport`) | ✅ completo | ML Lab (#12) — **regressão, SHAP, tuner e viés sem endpoints** |
| `pipelines` | `FLORAPipeline` (ingest×3, diversity, feature matrix) + `pipeline_log` | ⚠️ parcial | `flora run` no CLI é stub ("not yet implemented") |
| `reports` | `FLORAReport` auto-contido (métricas/tabelas/plots/texto) | ✅ completo | Relatórios (#14) |
| `viz` | 10 funções Plotly (taxonomia, diversidade, ML) | ✅ completo | 3 expostas via HTTP; **7 sem endpoint** |
| `ui` | `cli.py` (ui/download/ingest/run-stub) + `server.py` (13 endpoints) | ✅ funcional | base da API (#5) |
| `utils` | `inspect_db` | ✅ | Explorador (#9) |
| `front` | somente config: `angular.json`, `package.json`, tsconfigs, eslint, favicon | ❌ **sem código** | toda a Fase 2 |

**Regras de ouro confirmadas:** nada a reescrever nos algoritmos científicos; o trabalho do Studio é **expor** o que já existe (principalmente `ml/regression`, `ml/explainability`, `ml/optimization`, `ml/evaluation`, `io/validators`, 7 funções de `viz` e o `flora run`).

---

## 4. API HTTP catalogada (implementada de fato)

`server.py` — stdlib `http.server`, handlers síncronos, CORS `*`, sem auth, sem jobs/threads de worker (pipeline roda na thread do request).

| Método | Endpoint | Handler |
|--------|----------|---------|
| GET | `/` | SPA (dist Angular se existir, senão HTML embutido) |
| GET | `/api/status` | ✅ |
| POST | `/api/ingest/metadata` | ✅ |
| POST | `/api/ingest/asv` | ✅ |
| POST | `/api/ingest/taxonomy` | ✅ |
| POST | `/api/diversity` | ✅ (alfa; beta não exposta) |
| GET | `/api/feature_matrix` | ✅ |
| POST | `/api/ml/classify` | ✅ |
| POST | `/api/ml/cluster` | ✅ |
| GET | `/api/viz/taxonomy` | ✅ |
| GET | `/api/viz/pcoa` | ✅ |
| GET | `/api/viz/alpha` | ✅ |
| POST | `/api/download/mgnify` | ✅ |
| POST | `/api/download/sra` | ✅ (ENA/EMP não) |
| POST | `/api/report` | ✅ |

Documentados em `docs/ui_agent_prompt.md` mas **ausentes** (contratos a criar nas issues #5+): `/api/db/*`, `/api/validate/*`, `/api/features/{normalize|rarefy|select|reduce|encode}`, `/api/diversity/beta`, `/api/ml/regress`, `/api/optimize`, `/api/evaluate/*`, `/api/explain`, `/api/pipeline/run`, downloads ENA/EMP.

---

## 5. Lacunas e inconsistências críticas

1. **Build do pacote quebrado** — os 4 bugs da seção 2.1 abortavam `pip install`/wheel/sdist. *Corrigidos nesta auditoria.* Sem essas correções, nem CI nem `pip install git+…` funcionariam.
2. **Documentação do frontend não corresponde ao código** — `src/flora/front/README.md` descreve 15 rotas, 5 componentes e serviços "implementados"; `docs/ui.md` afirma "When the pre-built Angular frontend is available…". Realidade: zero arquivos de aplicação. (É exatamente a hipótese que motivou esta issue.)
3. **Scaffolding do frontend aponta para outra direção de design** — `package.json` usa **Angular Material + Tailwind CSS 4 + `@google/genai`**, e `metadata.json`/`.env.example` são artefatos de exportação do **Google AI Studio** (`GEMINI_API_KEY`, `MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API`). Conflita com o roadmap (PrimeNG 21, sem dependências não justificadas) — decisão formal necessária na issue #3 (ADR).
4. **`.gitignore` raiz ignora `src/flora/front/src/`** ("not distributed") e o sdist exclui o código-fonte do frontend: o wheel só carrega `dist/`. Para o Studio, o código Angular precisa ser rastreado no repositório — ajustar quando a issue #4 criar o app.
5. **`package-lock.json` ausente** — `scripts/build_frontend.sh` usa `npm ci`, que exige lockfile; o lock gerado nesta auditoria deve ser commitado.
6. **Gate de cobertura 70% não atingido** (50,76%) — ver §2.2.
7. **`flora run` é stub** no CLI (documentado como funcional em `docs/user_guide.md`).
8. **Documentação científica adiante do código** — `docs/article.md`/`methods.md` descrevem integração QIIME 2 SDK completa; no código não há módulo `qiime` (só ingestão de artefatos exportados). Ajustar na issue #18 (publicação) para não overclaim.

---

## 6. Capacidades reutilizáveis (confirmadas)

- ✅ Pipeline DuckDB + Parquet + Polars funcional, com catálogo fonte-arquivo e `pipeline_log` (proveniência pronta para rastreabilidade, #14).
- ✅ Configuração central (`FloraConfig`) com defaults válidos — basta espelhar na UI.
- ✅ Resultados de ML estruturados (`ClassificationResult`, `DataQualityReport`, importâncias) — serializáveis para JSON.
- ✅ Relatório HTML auto-contido — pronto para #14.
- ✅ Fallback HTML embutido — a plataforma já é utilizável hoje via `flora ui` sem nenhum build de frontend.
- ✅ Fallback do hatch hook — wheel constrói sem Node, degradando para o HTML embutido.

---

## 7. Recomendações para a issue #3 (ADR PrimeNG) e sequência

1. **ADR #3 deve decidir:** descartar o scaffolding atual (Material+Tailwind+Gemini/AI Studio) e iniciar o app Angular 21 do zero em `src/flora/front/src/` com **PrimeNG 21** (alinhado ao roadmap), removendo `@google/genai`, `metadata.json`, `.env.example` e ajustando o `.gitignore` para rastrear o código-fonte. Alternativa: manter Material — mas que fique explícito que isso diverge do roadmap.
2. **Commitar as 4 correções de build** desta auditoria como PR da issue #2 (baseline verde é pré-requisito de tudo).
3. **Issue #5 (contratos de API):** priorizar os endpoints já implementados (contrato real) e declarar os ausentes da §4 como contratos-alvo.
4. **Issue #15:** decidir o destino do gate de cobertura após ampliar testes de `viz`, `server`, `pipelines`, `tuner`, `shap`.
5. Manter `flora ui` e o servidor stdlib (decisão do roadmap: endurecer depois, conforme issue #6).
