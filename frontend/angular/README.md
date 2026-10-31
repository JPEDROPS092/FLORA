# Angular Frontend Plan

This directory contains the modular Angular SPA used by `flora ui`.

## Build Contract

The Angular production build should emit files into:

```text
../../src/flora/ui/static/app
```

Once the production build exists there, `flora ui` automatically serves the compiled SPA.
If it does not exist, the backend returns an explicit build-missing page.

## Recommended Feature Areas

- `overview`
- `ingestion`
- `downloads`
- `diversity`
- `feature-engineering`
- `machine-learning`
- `reports`

## Commands

```bash
cd frontend/angular
npm install
npm run build
```

## API Contract Rule

All frontend requests should use same-origin relative paths such as:

```text
/api/status
/api/diversity
/api/ml/classify
```

Do not hardcode `127.0.0.1` in the application code. The Python CLI remains the source of truth for host and port.
