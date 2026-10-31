# Contributing Guide

## Principles

- Preserve the `flora` CLI contract unless a change is explicitly versioned
- Prefer explicit contracts over implicit JSON structures
- Keep domain logic out of HTTP handlers
- Add tests for every bug fix or behavioral change

## Backend Standards

- Use type hints on public functions and methods
- Raise FLORA-specific exceptions from `flora.core.exceptions`
- Validate external input at the boundary layer
- Keep modules cohesive and small enough to reason about in isolation

## Frontend Standards

- Keep API calls centralized in one Angular service layer
- Organize screens by feature, not by widget type
- Reuse shared UI primitives for tables, cards, alerts, and charts
- Do not hardcode backend URLs; use same-origin relative requests

## Pull Request Checklist

- Tests added or updated
- Documentation updated when behavior changes
- CLI compatibility preserved
- No unrelated file reverts
- Logging remains useful for operators
