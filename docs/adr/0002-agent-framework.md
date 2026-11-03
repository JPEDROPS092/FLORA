# ADR 0002 — FLORA Scientific Agent Framework (proposta adaptada ao repositório)

- **Status:** Proposto (revisão 2: Scientific Runtime)
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

1. **Scientific Runtime primeiro; agentes são consumidores.** A execução científica
   (contratos, registry, políticas, jobs, proveniência) funciona sem LLM. UI, CLI, REST,
   agente (LangGraph) e clientes MCP chamam o mesmo caminho computacional.
2. **Sem segunda infraestrutura.** Ferramentas são *adaptadores finos* sobre `FLORAPipeline`,
   `ml/`, `viz/` e `reports/`. Os módulos existentes não são movidos agora.
3. **Contratos antes de agentes.** Pydantic v2 + JSON Schema são a fonte única para rotas
   HTTP (#5), tools e tipos do front. Quatro entidades: `DatasetRef`, `ToolSpec`,
   `ExecutionPlan`, `ExecutionRecord`.
4. **O agente escolhe uma capacidade registrada, nunca uma função Python.** O runtime valida
   compatibilidade e política antes de executar, e intermedeia toda chamada (inclusive de
   modelos confiáveis). Ferramentas recebem IDs de datasets, nunca caminhos ou shell.
5. **LangGraph e FastMCP opcionais**, atrás de `AgentBackend` (extras `agents`, `mcp`,
   `local-llm`, `workflows`). O motor simulado do front continua sem LLM nem rede.
6. **Coordenação em SQLite (WAL); DuckDB/Parquet só para análise.** Planos, aprovações,
   jobs, eventos e checkpoints ficam em SQLite com um coordenador de escrita. Arquivos e
   artefatos no filesystem gerenciado, referenciados por ID.
7. **Jobs em processos isolados.** Cancelar precisa interromper o processo de fato;
   `idempotency_key`, leases, heartbeats e reconciliação após reinício. Um job que perdeu
   o processo nunca é marcado como concluído nem reexecutado sem verificar seus efeitos.
   Retomar um grafo LangGraph e retomar um processo científico são estados distintos.
8. **Primeiro domínio: 16S.** Shotgun, RNA-seq e multiômica entram depois como módulos
   opcionais; o núcleo não vira framework genérico na v1. Nextflow só com a primeira etapa
   externa pesada.
9. **Local-first com `ModelRouter`.** Provedores Ollama, llama.cpp (embutido ou servidor) e
   APIs compatíveis com OpenAI, escolhidos por papel (roteamento/metadados, planejamento e
   seleção de ferramentas, interpretação) e por orçamento de VRAM. Dados saem da máquina
   apenas por política explícita (`external_data_transfer: deny_by_default`,
   `remote_fallback: approval_required`). A camada `flora.llm` e a tela *Modelos de IA* já
   cobrem provedor e modelo; falta o roteamento por papel.
10. **Modelo de implantação:** usuário local confiável. O servidor HTTP **não** é seguro para
    exposição pública; auth, autorização e isolamento são pré-requisito (#6).

### Correções específicas

- `differential_taxa` só é implementada com método estatístico adequado a dados
  composicionais (ex.: ANCOM-BC2), com versão e pressupostos documentados. Não é um teste
  convencional sobre abundâncias relativas.
- Cancelamento e retomada seguem a decisão 7.

### Validação em três camadas

| Camada | Tipo | Exemplos |
|---|---|---|
| Contratual | Determinística | schema, tipos, parâmetros, integridade de arquivos |
| Científica | Determinística | replicatas, desenho, FDR, composicionalidade, vazamento treino/teste, dispersão (PERMANOVA) |
| Interpretativa | Assistida por LLM | explicações, hipóteses, limitações; sempre rotulada como interpretação |

O agente pode recomendar um método; o validador rejeita configurações incompatíveis.
Cada número de relatório aponta para o artefato, método e execução que o produziram.

### Modelos locais de partida (RTX 3050 6 GB; segunda GPU de 4 GB opcional)

Avaliar nas mesmas ferramentas do FLORA, medindo `tool_call_success_rate`,
`structured_output_validity`, `tokens_per_second` e `peak_vram_mb`:

| Ordem | Modelo | Papel sugerido |
|---|---|---|
| 1 | Qwen3.5 4B | agente principal: planejamento e chamada de ferramentas |
| 2 | IBM Granite 4.2 3B | validar argumentos e gerar JSON estruturado |
| 3 | Phi-4-mini | extração de metadados, classificação de tarefas |

Com duas GPUs, um servidor por GPU (modelo leve na de 4 GB, científico na de 6 GB) antes de
tentar dividir um modelo. Tags Ollama e consumo de VRAM acima são **hipóteses a medir**.

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

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| P0.1 | Inventário das 15 rotas + contratos Pydantic | compatibilidade HTTP preservada |
| P0.2 | `DatasetRef`, `ToolSpec`, `ExecutionPlan` | schemas e testes completos |
| P0.3 | Registry com ferramentas 16S existentes | execução sem LLM |
| P0.4 | SQLite + JobManager | persistência, cancelamento e recuperação testados |
| P0.5 | Manifesto incremental e hashes | cada resultado rastreável |
| P0.6 | Política de segurança | auth, escopo, paths e aprovação testados (#6) |
| P0.7 | LangGraph + backend simulado | mesmo contrato para ambos |
| P0.8 | `ModelRouter` por papel sobre `flora.llm` | modelo local executa chamadas válidas |
| P0.9 | Integração com a UI existente | plano, aprovação, status e artefatos reais |
| P0.10 | Benchmark 16S | casos conhecidos, resultados reproduzíveis |
| P1.1 | FastMCP | ferramentas externas com autenticação |
| P1.2 | Bases científicas (NCBI, ENA, GEO, UniProt) | cache e limites |
| P1.3 | RO-Crate | exportação verificável |
| P1.4 | Nextflow | primeiro pipeline externo |
| P2 | Shotgun, RNA-seq, multiômica | extensões independentes por domínio |

PRs pequenas: contratos e compatibilidade primeiro; registry e adaptadores 16S em outra.
Não criar vários agentes nem dezenas de MCPs antes de uma execução vertical 16S verificável.

**Definition of Done (v1):** análise 16S completa sem LLM; mesmo workflow pedido por agente
ou UI; ferramenta inválida rejeitada antes de executar; etapas caras exigem aprovação; jobs
canceláveis e recuperáveis; resultados com hash, versões, parâmetros e proveniência; front
mostra planos, logs e artefatos reais; testes protegem os casos 16S atuais.

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
