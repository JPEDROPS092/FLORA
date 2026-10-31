# Architecture

## Executive Summary

FLORA already has useful domain capabilities, but the current implementation mixes concerns that should evolve independently:

- CLI bootstrapping, HTTP transport, application state, and HTML rendering live inside `src/flora/ui/server.py`
- The frontend is embedded in Python, which makes versioning, testing, and modular growth harder
- The pipeline orchestrator currently acts as both application service and infrastructure coordinator
- Contracts between UI and backend are implicit JSON payloads spread across handler methods

The recommended target architecture preserves `flora ui --host ... --port ... --workdir ... --log-level ...` while separating:

- domain and analytics logic
- application use cases
- infrastructure adapters
- presentation layers for CLI, HTTP API, and SPA

## Current-State Diagnosis

### Strengths

- The project is already split into meaningful technical packages such as `db`, `diversity`, `feature_engineering`, `ml`, `reports`, and `viz`
- Configuration is centralized through Pydantic models
- There is existing unit and integration test coverage
- The CLI contract is simple and practical

### Main Risks

- `src/flora/ui/server.py` is a large god-module with routing, request parsing, state management, report generation, download orchestration, and frontend delivery
- `src/flora/ui/webapp.py` hardcodes the full UI as a Python string builder, which prevents normal frontend build/test workflows
- API request and response payloads are not modeled explicitly, so regressions can slip in unnoticed
- Logging is configured in more than one entry point, but request correlation and per-use-case context are still limited
- `FLORAPipeline` directly coordinates ingestion, database lifecycle, and step logging; this is convenient but hard to isolate in tests
- `create_app()` advertises one return contract and actually returns another, which is a maintenance smell

## Target Architecture

### Backend Layers

```text
flora/
  core/            # cross-cutting types, errors, logging, utilities
  config/          # validated configuration and settings loaders
  domain/          # business entities, value objects, pure rules
  application/     # use cases, DTOs, service contracts
  infrastructure/  # DuckDB, downloaders, filesystem, external adapters
  presentation/
    cli/           # argparse / command entrypoints
    http/          # HTTP server, routing, serializers, handlers
    ui/            # frontend asset integration contract
```

### Frontend Target

```text
frontend/angular/
  src/app/
    core/          # API client, interceptors, environment
    features/      # dashboard, ingest, downloads, diversity, ML, reports
    shared/        # reusable UI components
```

Angular compiles to `src/flora/ui/static/app/`, and the Python server serves:

- built SPA assets
- client-side route fallback to the SPA index
- explicit `503` guidance when the SPA has not been built

## Recommended Folder Structure

```text
src/flora/
  application/
    dto/
    services/
    use_cases/
  core/
  config/
  domain/
    datasets/
    diversity/
    ml/
    reports/
  infrastructure/
    db/
    downloads/
    filesystem/
  presentation/
    cli/
    http/
      handlers/
      schemas/
      server.py
    ui/
      frontend.py
      static/
```

## API Contract Direction

Introduce explicit request and response models for endpoints such as:

- `POST /api/ingest/metadata`
- `POST /api/ingest/asv`
- `POST /api/ingest/taxonomy`
- `POST /api/diversity`
- `POST /api/ml/classify`
- `POST /api/report`

Each handler should delegate to a use case and serialize a well-defined response DTO. This avoids transport logic leaking into business rules.

## Angular Integration Strategy

The repository is now prepared for a compiled SPA through `src/flora/ui/frontend.py`.

Serving order:

1. If `src/flora/ui/static/app/index.html` exists, serve the compiled SPA
2. Otherwise, serve the existing embedded UI from `flora.ui.webapp`

This now gives a cleaner operational model:

- Angular is the source of truth for the web interface
- the backend remains responsible for serving the compiled assets and API
- missing builds fail explicitly instead of hiding the problem with a legacy UI

The repository now already contains the Angular workspace in `frontend/angular/`
and a backend integration layer in `src/flora/ui/frontend.py`.

## Migration Plan

### Phase 1

- isolate frontend delivery from the server
- add smoke coverage for `/` and `/api/status`
- document backend and UI contracts

### Phase 2

- extract HTTP handlers into dedicated modules by feature
- introduce request and response schemas
- move orchestration logic from handlers into application services

### Phase 3

- scaffold Angular workspace
- mirror current pages as Angular feature modules or standalone feature areas
- add frontend unit tests and API integration tests

### Phase 4

- deprecate embedded UI
- tighten type checking and API versioning
- add CI for Python + Angular pipelines

## Acceptance Criteria

- `flora ui --host 127.0.0.1 --port 8765 --workdir results/ --log-level INFO` still starts the UI
- host, port, workdir, and log level remain configurable
- the server can serve either embedded HTML or a built SPA
- smoke tests cover `/` and `/api/status`
- the architecture and migration path are documented
