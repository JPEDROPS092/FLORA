# ADR 0002 — FLORA Scientific Agent Framework (proposta adaptada ao repositório)

- **Status:** Proposto
- **Data:** 2026-11-02
- **Origem:** proposta LangGraph + FastMCP + Nextflow, auditada contra `dev` (`7e6cf01`)
- **Princípio:** agentes decidem sobre workflows; a execução científica permanece
  determinística, versionada e auditável. O LLM nunca calcula resultados.

---

## 1. Auditoria: o que já existe e o que não existe

| Item da proposta | Estado em `dev` | Evidência |
|---|---|---|
| Camada de dados analítica | ✅ | DuckDB/Parquet/Polars (`src/flora/db`, `backlog/backlog.md`) |
| Casos de uso reutilizáveis por ferramentas | ✅ | `FLORAPipeline` (`ingest_*`, `compute_diversity`, `get_feature_matrix`); `ml/`, `viz/`, `reports/` |
| Contrato HTTP/JSON para a UI | 🟡 | 15 rotas em `ui/server.py`; payloads implícitos (sem modelos Pydantic), issue #5 |
| Estado da aplicação | 🟡 | `ui/state.py` guarda só `config`, `workdir` e um `FLORAPipeline` singleton |
| Tracking de experimentos | 🟡 | `mlflow` em `config/settings.py` e `ui/handlers/ml.py`; sem proveniência de pipeline |
| Reprodutibilidade (seed) | 🟡 | `seed`/`random_state` em `feature_engineering/` e `ml/`; sem versões de ferramentas, hashes ou manifesto |
| Aquisição de dados públicos | ✅ | `io/downloaders.py` (EMP, MGnify, SRA/ENA) |
| Metagenômica pesada (Kraken2, MetaPhlAn, MEGAHIT…) | ❌ | nenhum código; só 16S (QIIME2/DADA2 consta no backlog, mas `src/` não referencia essas ferramentas fora de `config/settings.py`) |
| Transcriptômica / genômica | ❌ | fora do escopo atual do pacote |
| Executor de jobs (fila, cancelar, retomar) | ❌ | requisições são síncronas dentro do `http.server` |
| Nextflow / Snakemake / contêineres / SLURM | ❌ | ausentes de `pyproject.toml` e `environment.yml` |
| LangGraph / MCP / SDK de LLM | ❌ | nenhuma dependência |
| Segurança para execução remota | ❌ | `Access-Control-Allow-Origin: *`, sem auth, sem sandbox de paths (issue #6) |
| UI de agentes | 🟡 | `AgentService`/copilot/`/agents` no front, **simulados** (`core/agents/agent.engine.ts`), com contrato `steps` + `actions` pronto |

**Conclusão:** a proposta é compatível, mas o FLORA hoje é um analisador **16S em
processo** sobre DuckDB, não um orquestrador de pipelines pesados. Metagenômica
shotgun, RNA-seq e Nextflow são **novos domínios**, não extensões do que existe.
O primeiro entregável deve, portanto, reaproveitar o 16S já funcional.

## 2. Decisões

1. **Não criar segunda infraestrutura.** Ferramentas MCP são *adaptadores finos*
   sobre os casos de uso existentes (`FLORAPipeline`, `ml/`, `viz/`, `reports/`).
2. **Contratos antes de agentes.** Modelos Pydantic de entrada/saída viram a fonte
   única para: rotas HTTP (#5), schema das tools MCP e tipos do front.
3. **Um fluxo vertical primeiro, em 16S** (já temos QC, taxonomia, alfa/beta, ML e
   relatório): *registrar dataset → QC → diversidade/taxonomia → estatística →
   interpretação → relatório*. Metagenômica shotgun (taxprofiler) vem depois.
4. **LangGraph + FastMCP**, como proposto, mas atrás de uma interface `AgentBackend`
   para que o motor simulado do front continue funcionando sem LLM nem rede.
5. **Nextflow só quando houver etapa externa pesada.** No 16S em processo, o executor
   é um `JobManager` local (thread/process pool) com o mesmo contrato que o executor
   Nextflow terá.
6. **Ferramentas recebem IDs de datasets registrados**, nunca caminhos ou shell
   arbitrários do agente.

## 3. Estrutura proposta (mapeada ao pacote atual)

```text
src/flora/
├── agent_tools/          # contratos Pydantic + registry (substitui "mcp/servers" no começo)
│   ├── registry.py       # catálogo versionado: nome, schema, permissões, custo estimado
│   ├── contracts.py      # *Request/*Result (mesmos modelos das rotas HTTP)
│   └── tools_16s.py      # adapters sobre FLORAPipeline / ml / viz / reports
├── jobs/                 # JobManager, estado persistido (DuckDB), cancelar/retomar
├── provenance/           # manifesto por execução: entradas+hash, versões, params, seed
├── agents/               # grafo LangGraph: planner → curator → specialist → executor → validator → interpreter
│   └── backend.py        # AgentBackend (LangGraph | simulado)
├── mcp/                  # servidor FastMCP expondo agent_tools por domínio
└── ui/handlers/agents.py # /api/agent/* (planos, aprovação, jobs, artefatos, SSE)
```

Os diretórios `workflows/nextflow|snakemake` e `execution/slurm|container` só são
criados na fase P1, quando existir o primeiro workflow externo.

## 4. Reaproveitamento do front já entregue

| Hoje (simulado) | Passa a ser |
|---|---|
| `AgentService.ask()` → `runAgent()` | `AgentBackend` HTTP: `POST /api/agent/plans` |
| `AgentStep` (tool, label, detalhe, ms) | passos reais do grafo com status e logs |
| `AgentAction` + botão "Aplicar" | **portão de aprovação** (human-in-the-loop) antes de cada etapa cara |
| `/agents` (execuções da sessão) | histórico persistido de planos/jobs/artefatos |
| `HttpFloraRepository` | mesmo ponto único de troca mock ↔ API |

Falta no front: visão de **plano editável** (DAG com status por etapa), **fila de jobs**
com logs/cancelar, e **painel de proveniência** por resultado.

## 5. Regras não negociáveis (v1)

- **Reprodutibilidade:** manifesto com versão do FLORA, de dependências, params, seed e
  SHA-256 de cada entrada.
- **Segurança:** allow-list de tools; sem shell; paths só sob `workdir`; limites de
  CPU/RAM/tempo; auth e CORS restrito antes de expor `/api/agent/*` (depende da #6).
- **Aprovação humana** para downloads grandes, jobs caros e mudança de desenho experimental.
- **Validação científica** no nó validador: replicatas por grupo, normalização/contraste
  coerentes, correção FDR, avisos de composicionalidade (já usados nos textos dos agentes simulados).
- **Evidência vs. hipótese:** o relatório separa resultado computado (com manifesto)
  de interpretação do LLM, rotulada como tal.
- **Persistência:** estado de agentes e de jobs em tabelas próprias; retomada após reinício.
- **Observabilidade:** tokens, tempo, CPU/RAM e falhas por tool, registrados no manifesto.
- **Empacotamento:** exportar RO-Crate / Workflow Run RO-Crate a partir do manifesto (P1).

## 6. Roadmap ajustado

| Fase | Entregável | Prior. | Depende de |
|---|---|---|---|
| 0 | Modelos Pydantic das rotas existentes + testes de contrato | P0 | #5 |
| 1 | `agent_tools` registry + adapters 16S (QC, diversidade, taxonomia, ML, relatório) | P0 | 0 |
| 2 | `JobManager` local + estado persistido + manifesto de proveniência | P0 | 1 |
| 3 | Grafo LangGraph com checkpoints e aprovação; `/api/agent/*`; front troca simulado por HTTP | P0 | 1, 2 |
| 4 | Segurança mínima (auth, CORS, sandbox de paths, limites) | P0 | #6, antes de expor 3 |
| 5 | Servidor FastMCP (mesmas tools) para clientes externos | P1 | 1 |
| 6 | MCP de bancos (NCBI/SRA/GEO/UniProt/PubMed) com cache e limites | P1 | 3 |
| 7 | Validador científico + relatório com RO-Crate | P1 | 2, 3 |
| 8 | Metagenômica shotgun via `nf-core/taxprofiler` + executor Nextflow | P1 | 2 |
| 9 | Benchmark reprodutível de agentes (casos com resposta conhecida no mock) | P1 | 3 |
| 10 | RNA-seq (`nf-core/rnaseq`, DESeq2), metatranscriptômica, multiômica | P2 | 8 |

## 7. Riscos e perguntas em aberto

- **Escopo:** RNA-seq e genômica ampliam o produto além de "microbioma 16S". Confirmar se
  entram no roadmap ou ficam como extensões comunitárias via registry.
- **Dependências:** LangGraph/LangChain são pesadas; manter como extra opcional
  (`pip install flora[agents]`).
- **Provedor de LLM e dados:** definir onde dados de pesquisa podem ser enviados
  (nuvem × modelo local) antes de ligar qualquer provedor.
- **Divergência backlog × código:** EP-03 (QIIME2/DADA2) está marcado como concluído,
  mas `src/` não contém essas etapas; reconciliar antes de prometer "pipeline 16S completo".
- **Licenças:** KEGG exige respeito aos termos de uso da API; tratar em `databases`.

## 8. Primeiro passo concreto (sugestão)

Fase 0 + 1 em um PR pequeno: modelos Pydantic das 15 rotas atuais, `registry.py` com
4 tools 16S (`run_qc`, `compute_diversity`, `differential_taxa`, `build_report`) e testes
de contrato. Não exige LLM, rede nem dependência nova, e entrega o schema que o front,
as rotas e o MCP vão compartilhar.
