# FLORA Frontend

Angular 21 SPA for the FLORA microbiome analysis platform.

> **Status: AppShell implemented (issue #4).** The application shell builds,
> passes unit tests and lint, and is served by `flora ui` when `dist/` is
> present. Feature pages land with issues #7–#14 on top of the design-system
> decision recorded in
> [ADR 0001](../../../docs/adr/0001-design-system-primeng.md).

---

## Overview

This directory contains the web frontend served by the FLORA Python server. When
built and available at `dist/`, the server (`flora ui`) automatically serves
these static files instead of the fallback HTML interface.

**Tech stack (decided in ADR 0001):**

- Angular 21 — standalone components, lazy-loaded routes, Angular Signals
- PrimeNG 21 + PrimeIcons — component library (peer-compatible with Angular 21 / CDK 21)
- CSS custom properties (`styles/tokens.css`, `themes.css`, `scientific.css`) — no Tailwind, no Material
- TypeScript 5.9 (strict)
- Plotly.js — scientific figures (planned, parity with backend Plotly figures)
- Vitest + jsdom — unit tests

## Current structure

```
src/flora/front/
├── src/
│   ├── index.html            # SPA entry
│   ├── main.ts               # bootstrapApplication
│   ├── styles.css            # imports tokens/themes/scientific
│   ├── styles/
│   │   ├── tokens.css        # FLORA design tokens
│   │   ├── themes.css        # fonts, focus visibility, scrollbars
│   │   └── scientific.css    # data-display utilities
│   └── app/
│       ├── app.ts / app.html / app.config.ts   # root + PrimeNG theme preset
│       ├── app.routes.ts                       # routes (lazy per feature)
│       ├── core/api/flora-api.service.ts       # GET /api/status client
│       ├── layout/shell.*                      # sidebar + topbar layout
│       └── pages/home.page.ts                  # dashboard placeholder (#7)
├── public/favicon.ico        # Static assets
├── angular.json              # Angular CLI config (output: dist/)
├── package.json              # npm dependencies (PrimeNG stack)
├── tsconfig.json             # TypeScript config
├── tsconfig.app.json         # App compilation config
├── tsconfig.spec.json        # Test compilation config
└── eslint.config.js          # angular-eslint flat config
```

## Development

### Prerequisites

- Node.js >= 20
- npm >= 10

### Setup

```bash
cd src/flora/front
npm install
```

> The repository tracks `package-lock.json`; use `npm ci` in CI (as
> `scripts/build_frontend.sh` does).

### Local development server

```bash
npm run dev
# Starts at http://localhost:3000
```

API calls to `/api/*` are proxied to the Python server (`flora ui`, port 8765)
when it runs alongside — add a `proxy.conf.json` if you need proxying during
development.

### Build for production

```bash
# From the project root
./scripts/build_frontend.sh

# Or manually
cd src/flora/front
npm run build
```

The build output is flattened to `dist/` by the script above so the Python
package can serve it.

## Integration with the Python package

The built `dist/` directory is included in the Python wheel via
`pyproject.toml` (`artifacts = ["src/flora/front/dist"]`) and served by
`flora.ui.server`. When `dist/` is absent, the wheel still builds and the
server falls back to the embedded HTML interface.

## Target routes

The route map below is the target for the feature issues (#7–#14); nothing is
implemented yet.

| Route | Feature issue |
|-------|---------------|
| `/dashboard` | #7 |
| `/acquisition`, `/ingestion` | #8 |
| `/explorer` | #9 |
| `/features`, `/diversity`, `/visualizations` | #10, #11 |
| `/machine-learning` | #12 |
| `/pipeline` | #13 |
| `/reports` | #14 |

## License

MIT. See [LICENSE](../../../LICENSE).
