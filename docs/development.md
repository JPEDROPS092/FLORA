# Development Guide

## Local Setup

```bash
git clone https://github.com/flora-bio/flora
cd flora
pip install -e ".[dev]"
```

Optional Conda workflow:

```bash
conda env create -f environment.yml
conda activate flora
pip install -e ".[dev]"
```

## Backend Commands

Run tests:

```bash
pytest
```

Run a focused UI smoke test:

```bash
pytest tests/integration/test_ui_server.py -v
```

Run linting:

```bash
ruff check src tests
```

## UI Command

The compatibility command remains:

```bash
flora ui --host 127.0.0.1 --port 8765 --workdir results/ --log-level INFO
```

Useful variants:

```bash
flora ui --no-browser
flora ui --config config.yaml --workdir results/
```

## Angular Workflow

The Angular workspace now lives in:

```text
frontend/angular/
```

The backend serves the compiled SPA from:

```text
src/flora/ui/static/app/
```

Frontend commands:

```bash
cd frontend/angular
npm install
npm run build
```

Recommended workflow:

1. Keep API calls relative to the same origin, for example `/api/status`
2. Rebuild the SPA after frontend changes with `npm run build`
3. Use `flora ui` to validate the integrated runtime
4. Treat a missing build as an operational error; there is no embedded UI fallback anymore

## Recommended Daily Flow

1. Run Python tests before changing API behavior
2. Keep handler logic thin and move orchestration into reusable services
3. Preserve the CLI contract when modifying UI bootstrap behavior
4. Treat `src/flora/ui/webapp.py` as legacy code; the server requires the Angular build
