# FLORA Application Presentation Setup

This directory contains everything needed to create a complete presentation of the FLORA application with saved analyses and grouping functionality.

## Features Included

1. **Saved LLM Analyses**: All analysis results are persisted to JSON files
2. **Complete Grouping Support**: Both standard and enriched grouping functionality
3. **Presentation Environment**: Ready-to-use setup for demonstrations

## Setup Instructions

### 1. Create Presentation Environment

```bash
./scripts/setup_presentation.sh
```

### 2. Run Tests for Enrichment and Grouping

```bash
./scripts/run_enrichment_tests.sh
```

### 3. Save Analyses for Presentation

```bash
./scripts/save_analyses.sh
```

## Files Created

- `presentation/`: Complete presentation environment with startup script
- `tests/integration/test_enrichment.py`: Tests for enrichment functionality
- `tests/integration/test_grouping.py`: Tests for grouping functionality
- `scripts/setup_presentation.sh`: Sets up complete presentation environment
- `scripts/run_enrichment_tests.sh`: Runs all enrichment and grouping tests
- `scripts/save_analyses.sh`: Saves LLM analyses to persistent storage

## Presentation Components

The presentation includes:

1. **Dashboard View**: Sample statistics and quality control
2. **Pipeline View**: Data ingestion and processing steps
3. **Explore Summary**: Taxonomic trees and diversity analysis
4. **Grouping Analysis**: Different grouping methods (biome, site, etc.)
5. **Enrichment Results**: Enhanced analysis with additional metadata

All data is saved persistently so it can be viewed offline or shared with others.