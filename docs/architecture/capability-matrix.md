# Matriz de capacidades — FLORA Studio

- **Data:** 2026-11-02
- **Branch:** `dev` (após `be56a44`)
- **Issue:** #2 (complementa `docs/audit.md`, que auditou `main`)
- **Legenda:** ✅ implementado · 🟡 parcial · ❌ ausente

Evidência de execução na `dev` (Linux, Node 22, Python venv limpo):

| Verificação | Resultado |
|---|---|
| `npm ci` em `src/flora/front` | ✅ |
| `npm run build` | ✅ após remover `.postcssrc.json` (referenciava `@tailwindcss/postcss`, removido pelo ADR 0001); bundle inicial 543,88 kB (120,09 kB transferidos), **acima do orçamento de 500 kB** (warning) |
| `npm test` | ✅ 1 arquivo, 1 teste |
| `pip install -e .` | ✅ |
| `flora ui` (smoke) | ✅ `/` → 200 HTML (modo `angular-spa`); `/api/status` → JSON `connected`; `/api/viz/pcoa` sem dados → 400 |
| `pytest` UI | ⚠️ não executado: o extra de cobertura (`pytest-cov`) não estava instalado e o `addopts` o exige |

## 1. Backend (Python)

| Capacidade | Estado | Evidência |
|---|---|---|
| Servidor HTTP (`http.server`) | ✅ | `src/flora/ui/server.py` |
| `GET /api/status`, `/api/feature_matrix`, `/api/logs`, `/api/report/preview` | ✅ | `server.py` (rotas GET), smoke test |
| `GET /api/viz/*` (taxonomy, pcoa, alpha, taxonomy_heatmap, beta_heatmap, krona, tree, network) | ✅ | `handlers/viz.py`; retorna 400 sem dados |
| `POST /api/ingest/{metadata,asv,taxonomy}` | ✅ | `handlers/ingest.py` |
| `POST /api/diversity` | ✅ | `handlers/ingest.py` |
| `POST /api/ml/{classify,cluster}` | ✅ | `handlers/ml.py` |
| `POST /api/download/{mgnify,sra,emp,synthetic}` | ✅ | `handlers/downloads.py` |
| `POST /api/report` | ✅ | `handlers/report.py` |
| Endpoints "desejados" de `docs/ui_agent_prompt.md` | ❌ | catálogo real × desejado pendente (#5) |
| Segurança para uso público (CORS restrito, paths, uploads, auth) | ❌ | `Access-Control-Allow-Origin: *` confirmado; ver #6 |
| Cobertura de testes de `ui/server.py` | 🟡 | 9% na auditoria de `main`; testes em `tests/unit/test_ui_*.py`, `tests/integration/test_ui_server.py` |

## 2. Frontend (Angular 21 + PrimeNG 21)

| Capacidade | Estado | Evidência |
|---|---|---|
| Scaffolding Angular 21 standalone, build, lint, Vitest | ✅ | `src/flora/front/` |
| ADR do design system (PrimeNG, tokens CSS) | 🟡 | `docs/adr/0001-design-system-primeng.md`; sem PoC, medições nem comparação (#3) |
| Tokens navy/cyan, tema claro/escuro | 🟡 | `src/styles/{tokens,themes,scientific}.css`; alternância de tema não verificada |
| AppShell (sidebar + topbar) | 🟡 | `app/layout/shell.*`; sem drawer mobile, breadcrumbs, pesquisa/comandos, skip link |
| Rotas lazy | ❌ | única rota `dashboard` é eager (`app.routes.ts`) |
| Guards de dados; estados loading/empty/error | ❌ | — |
| Serviço HTTP tipado | 🟡 | `core/api/flora-api.service.ts` (25 linhas, só `/api/status`) |
| Páginas de aquisição, ingestão, diversidade, ML, viz, relatório | ❌ | previstas para #7–#14 |
| Testes de componente | 🟡 | `app.spec.ts` (1 teste) |
| E2E / testes em 3 viewports | ❌ | — |
| Servir `dist/` via `flora ui` com fallback embutido | ✅ | smoke test; `ui/frontend.py` |

## 3. Legado

| Item | Estado | Observação |
|---|---|---|
| `frontend/angular/` (raiz) | 🟡 | árvore Angular antiga com `app.component.spec.ts`; relação com `src/flora/front/` não documentada — decidir remover ou arquivar |
| `backlog/backlog.md` (50 itens "concluídos") | 🟡 | itens de Python não reverificados item a item aqui |

## 4. Pendências para encerrar a auditoria

- Reverificar item a item o `backlog/backlog.md` contra código/testes.
- Rodar a suíte Python completa com `pytest-cov` e registrar a cobertura.
- Decidir o destino de `frontend/angular/`.
- Responsáveis: a definir pelo mantenedor.
