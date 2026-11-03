# Projetos, fontes de dados e sincronização

Cada projeto vive em `<workdir>/projects/<id>/`:

| Arquivo | Conteúdo |
|---|---|
| `project.json` | metadados, estágio, fontes, contagens |
| `flora.duckdb` | dados analíticos **só deste projeto** |
| `raw/<fonte>/` | arquivos baixados |
| `manifest.json` | SHA-256 e tamanho de cada arquivo, por fonte |
| `jobs/<id>.json` | estado, progresso e log de cada sincronização |

O projeto ativo (`projects/active.json`) define qual DuckDB as rotas existentes (`/api/status`,
`/api/viz/*`, `/api/diversity`…) usam. Sem projeto ativo vale o comportamento legado.

## Estágios
`empty` → `raw_downloaded` → `ingested`. Só `ingested` (matriz ASV + metadata + taxonomia no DuckDB) permite
análise. MGnify e SRA baixam arquivos brutos e param em `raw_downloaded`; eles **não** viram matriz ASV sozinhos.
EMP e o exemplo sintético trazem as três tabelas e chegam a `ingested`.

## API
| Método | Rota | Uso |
|---|---|---|
| GET | `/api/projects` | lista + id do ativo |
| GET | `/api/projects/detail?id=` | projeto + jobs |
| POST | `/api/projects` | cria `{name, question, …}` |
| POST | `/api/projects/update` | edita campos descritivos |
| POST | `/api/projects/activate` | `{id}` |
| POST | `/api/projects/sync` | `{id, source:{type, accession, params}}` → job |
| GET | `/api/sync-jobs?id=` | progresso |
| POST | `/api/sync-jobs/cancel` | cancelamento cooperativo |
| GET | `/api/examples` | galeria |
| POST | `/api/examples/install` | cria projeto + inicia sync |

## Sincronização
Roda em thread (não bloqueia o HTTP), um job por projeto, no máximo 2 simultâneos. Estados: `queued`, `running`,
`completed`, `failed`, `cancelled`. Uma segunda sincronização com a mesma fonte confere o manifesto e termina
como “já sincronizado” sem baixar nem reingerir. Jobs que estavam rodando quando o servidor caiu são marcados
`failed` na próxima inicialização.

## Limites conhecidos
- Cancelar não interrompe um download já em andamento; a parada ocorre na próxima etapa.
- Um projeto ingerido não aceita outra fonte nem reingestão (crie outro projeto).
- Os downloaders MGnify/SRA/EMP não foram exercitados contra a rede nesta entrega; só o exemplo sintético foi
  verificado ponta a ponta. Os estudos públicos são *templates* não verificados.
- Os textos dos exemplos vêm do backend em inglês.
- Não há upload de arquivos locais nem sincronização agendada; ENA ainda não é um conector próprio.
- O servidor continua sem autenticação (#6).
