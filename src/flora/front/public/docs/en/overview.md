# Overview

FLORA takes a 16S amplicon study from the **ASV table to the report** in five steps. Each step records **provenance**: parameters, package versions and seed.

1. **Ingestion** — metadata, ASV table and taxonomy, with per-sample QC.
2. **Normalization** — rarefaction, TSS or CLR.
3. **Exploration** — alpha/beta diversity, PCoA and taxonomy.
4. **Modelling** — Random Forest and XGBoost.
5. **Report** — editable sections, HTML/PDF export.

## Projects

Each project has its **own directory and DuckDB database**, so data never mixes. Create one under *Projects*, install an example (the synthetic one works offline) and activate it: every screen then shows the active project's data.

## Shortcuts

- `Ctrl K` opens the command palette.
- `Ctrl J` opens the copilot.
