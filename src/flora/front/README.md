# FLORA Frontend

Angular 21 SPA for the FLORA microbiome analysis platform. Built with Angular Material, Tailwind CSS 4, and TypeScript 5.9.

---

## Overview

This directory contains the modern web frontend served by the FLORA Python server. When built and available at `dist/`, the Python server (`flora ui`) automatically serves these static files instead of the fallback HTML interface.

**Tech stack:**

- Angular 21 (standalone components, lazy-loaded routes)
- Angular Material 21 + Angular CDK
- Tailwind CSS 4 (via PostCSS)
- TypeScript 5.9
- Vitest for unit tests

---

## Development

### Prerequisites

- Node.js >= 20
- npm >= 10

### Setup

```bash
cd src/flora/front
npm install
```

### Local development server

```bash
npm run dev
# Starts at http://localhost:3000
```

This runs the Angular dev server with hot module replacement. API calls to `/api/*` are proxied to the Python server when it runs alongside.

### Build for production

```bash
# From the project root
./scripts/build_frontend.sh

# Or manually
cd src/flora/front
npm run build
```

The build output is written to `dist/` (flattened from the Angular CLI's `dist/app/browser/`).

---

## Project structure

```
src/flora/front/
├── src/
│   ├── index.html                  # SPA entry point
│   ├── main.ts                     # Browser bootstrap
│   ├── styles.css                  # Global styles (Tailwind + theme)
│   └── app/
│       ├── app.ts                  # Root component
│       ├── app.html                # Root template
│       ├── app.config.ts           # Browser app config
│       ├── app.routes.ts           # 15 routes
│       ├── layout.ts               # Sidebar + header layout
│       ├── api.service.ts          # HTTP client for /api/*
│       ├── pages/
│       │   ├── dashboard.ts        # Status cards + pipeline progress
│       │   ├── acquisition.ts      # MGnify/SRA download forms
│       │   ├── features.ts         # Normalization, rarefaction, reduction
│       │   ├── pipeline.ts         # Pipeline orchestration UI
│       │   └── generic.ts          # Placeholder for under-construction pages
│       └── ui/
│           ├── components.ts       # Card, Button, Input, Select, Badge
│           └── toast.service.ts    # Toast notifications
├── public/                         # Static assets (favicon)
├── angular.json                    # Angular CLI config
├── package.json                    # npm dependencies
├── tsconfig.json                   # TypeScript config
└── .postcssrc.json                 # Tailwind/PostCSS config
```

---

## Routes

| Route | Component | Status |
|-------|-----------|--------|
| `/dashboard` | `DashboardComponent` | Implemented |
| `/config` | `GenericPageComponent` | Placeholder |
| `/acquisition` | `AcquisitionComponent` | Implemented |
| `/validation` | `GenericPageComponent` | Placeholder |
| `/ingestion` | `GenericPageComponent` | Placeholder |
| `/explorer` | `GenericPageComponent` | Placeholder |
| `/features` | `FeaturesComponent` | Implemented |
| `/diversity` | `GenericPageComponent` | Placeholder |
| `/ml` | `GenericPageComponent` | Placeholder |
| `/optimization` | `GenericPageComponent` | Placeholder |
| `/evaluation` | `GenericPageComponent` | Placeholder |
| `/explainability` | `GenericPageComponent` | Placeholder |
| `/visualizations` | `GenericPageComponent` | Placeholder |
| `/reports` | `GenericPageComponent` | Placeholder |
| `/pipeline` | `PipelineComponent` | Simulated |

---

## API integration

The frontend communicates with the Python server via relative URLs (`/api/*`). The `FloraApiService` (`api.service.ts`) provides typed methods for all endpoints:

```typescript
// Example usage in a component
private api = inject(FloraApiService);

this.api.getStatus().subscribe(data => {
  console.log(data.tables);
});

this.api.download('mgnify', { study_accession: 'MGYS00005116' }).subscribe(result => {
  console.log(result.manifest);
});
```

When running the dev server (`npm run dev`), configure a proxy to the Python backend:

```json
// proxy.conf.json
{
  "/api": {
    "target": "http://localhost:8765",
    "secure": false
  }
}
```

---

## Integration with Python package

The built `dist/` directory is included in the Python wheel via `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/flora/front/dist" = "flora/front/dist"
```

When a user runs `pip install flora-bio`, only the pre-built static files are included. The Angular source, `node_modules/`, and build tools are excluded.

---

## Design system

The frontend uses a dark navy theme with the following tokens:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0a1628` | Page background |
| `--bg-card` | `#111d32` | Card backgrounds |
| `--bg-surface` | `#1a2840` | Surface elements |
| `--accent` | `#22d3ee` | Primary accent (cyan) |
| `--accent-secondary` | `#a78bfa` | Secondary accent (purple) |
| `--text-primary` | `#f1f5f9` | Primary text |
| `--text-secondary` | `#94a3b8` | Secondary text |
| `--success` | `#4ade80` | Success states |
| `--warning` | `#fbbf24` | Warning states |
| `--error` | `#f87171` | Error states |

Fonts: Inter (body), JetBrains Mono (code/data), Playfair Display (headings).

---

## License

MIT. See [LICENSE](../../../LICENSE).
