# FLORA · Microbiome Research Workspace

Interface Angular do `flora ui`. A aplicação abre em cinco módulos e lê uma única fonte de dados, escolhida em `src/environments/environment.ts`.

| Módulo | Rota | Função |
| --- | --- | --- |
| Research Dashboard | `/dashboard` | Amostras, ASVs, grupos, qualidade, diversidade e análises recentes. Logs ficam em Diagnóstico. |
| Scientific Explorer | `/explorer` | PCoA, alfa, beta, abundância e co-ocorrência com os mesmos filtros. |
| Data Pipeline Studio | `/pipeline` | Importação, colunas, QC por amostra, distribuição de reads, rarefação, CLR/TSS e o trilho QIIME2/DADA2. |
| AI & ML Lab | `/ml` | Comparação de modelos, ROC, F1, matriz de confusão, SHAP e rastreamento de experimentos. Tema escuro só nesta área. |
| Scientific Report Builder | `/reports` | Texto, figuras, métodos, parâmetros e exportação HTML/PDF. |

Projetos (`/projects`) e downloads (`/downloads`) continuam acessíveis pela biblioteca. Rotas antigas (`/overview`, `/workspace`, `/visuals`, `/reporting`) redirecionam para os módulos novos.

## Trocar mock pela API

Toda a UI fala com `FloraRepository`. A implementação é escolhida num único lugar:

```ts
// src/environments/environment.ts
export const environment = {
  useMocks: true,
  apiBaseUrl: ''
};
```

- `useMocks: true` carrega o estudo 16S de demonstração (80 amostras, 1.842 ASVs, grupos Rhizosphere, Bulk soil e Endosphere). A interface marca esses números como mock.
- `useMocks: false` usa `HttpFloraRepository`, que chama a API já existente do `flora ui`. Não há cliente além desse esqueleto.

`apiBaseUrl` vazio significa mesma origem (`/api/...`), que é o caso quando `flora ui` serve o build. Se o `ng serve` roda em outra porta, aponte para o servidor Python:

```ts
export const environment = {
  useMocks: false,
  apiBaseUrl: 'http://127.0.0.1:8765'
};
```

Depois de mudar o arquivo, rode de novo `npm run build` ou `npm start`.

### O que a API já atende

| Ação na UI | Endpoint |
| --- | --- |
| Painel e diagnóstico | `GET /api/status`, `GET /api/logs` |
| Ingestão | `POST /api/ingest/metadata`, `/api/ingest/asv`, `/api/ingest/taxonomy` |
| Normalização | `GET /api/feature_matrix` |
| Explorer | `GET /api/viz/pcoa`, `/alpha`, `/beta_heatmap`, `/taxonomy`, `/network` e `POST /api/diversity` |
| ML | `POST /api/ml/classify`, `POST /api/ml/cluster` |
| Relatório no backend | `POST /api/report` |
| Downloads | `POST /api/download/synthetic`, `/emp`, `/mgnify`, `/sra` |

A ingestão só fica verde se as três respostas tiverem `success: true`. Cada gráfico trata o próprio erro. Projetos, QC por amostra, árvore taxonômica editável, SHAP e ROC não existem na API atual: o esqueleto HTTP mostra o que o endpoint devolve e um aviso no restante. Quando esses recursos entrarem no Python, o ajuste fica em `src/app/core/data/http/http-flora.repository.ts`.

No mock, o caminho de taxonomia `fail-taxonomy` faz só essa etapa falhar, para conferir a agregação.

## Build

O build de produção continua saindo em `src/flora/ui/static/app`, de onde o `flora ui` serve a SPA.

```bash
cd frontend/angular
npm install
npm run build
npm start
```

`npm start` sobe em `http://127.0.0.1:4200`.

## Tema

PrimeNG em modo styled, preset Aura customizado em `src/app/core/theme/flora.preset.ts`. Tokens de superfície: fundo `#F8FAF9`, cartão `#FFFFFF`, primária `#155E53`, texto `#22332F`, muted `#64736E`, borda `#DCE5E1`. Gráficos continuam em Plotly e herdam o tema claro, ou o tema escuro dentro do ML Lab.
