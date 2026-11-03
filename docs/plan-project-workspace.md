# Plano — Project Workspace, conexão de dados e sincronização

Branch: `feat/project-workspace` (a partir de `dev`).

## Estado encontrado
- `FLORAState` tem **um** `FLORAPipeline` e DuckDB `:memory:` por padrão: nada persiste e não há isolamento.
- `/projects` no front já existe (`ProjectsPageComponent`, `FloraRepository.projects/saveProject`);
  no modo HTTP os projetos são só de sessão.
- Downloaders MGnify / SRA / EMP e o gerador sintético existem como rotas síncronas.

## Decisões
1. **Um diretório por projeto** em `<workdir>/projects/<id>/` com `project.json`, `flora.duckdb`,
   `raw/`, `manifest.json` e `jobs/`. Isso dá persistência e isolamento sem tocar no `FLORAPipeline`.
   (O pedido sugeria DuckDB para o registro; o registro é JSON atômico por projeto, que é mais simples e
   robusto para o MVP. Migrar para DuckDB é possível sem mudar a API.)
2. **Projeto ativo**: `state.pipeline` passa a apontar para o pipeline do projeto ativo; sem projeto ativo
   o comportamento legado é preservado.
3. **Sincronização em jobs** (thread), persistidos em `jobs/<id>.json`, com `queued/running/completed/failed/cancelled`.
   Jobs interrompidos por reinício viram `failed`. Cancelar é cooperativo (entre etapas; um download em curso termina).
4. **Incremental**: `manifest.json` guarda SHA-256 e tamanho por arquivo; se a fonte/parâmetros e os arquivos
   conferem, a sincronização termina como `up_to_date` sem baixar nem ingerir de novo.
5. **Estágios honestos**: `empty → raw_downloaded → ingested`. FASTQ/arquivos brutos nunca contam como matriz ASV;
   só `ingested` habilita análise.
6. **Exemplos**: o sintético (seed 42, 80 amostras, 200 ASVs) é instalável offline e rotulado como sintético.
   Estudos públicos entram como *templates* com `verified: false` até alguém confirmar o accession na fonte.
7. **Fora do escopo desta entrega**: testes automatizados (a pedido), upload de arquivos, sync agendada,
   ENA como conector separado, ingestão automática de FASTQ.

## Fases
1. Backend: `flora.projects` (registry, sync, exemplos) + rotas `/api/projects*`, `/api/sync-jobs*`, `/api/examples*`.
2. Front: repositório HTTP com projetos reais; página de projetos com galeria, “Conectar fonte”, progresso, ativar.
3. Mock: mesmos contratos, marcados como mock.
4. Documentação de uso.
