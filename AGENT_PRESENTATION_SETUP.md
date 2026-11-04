# FLORA Agent Pipeline Presentation Setup

This directory contains everything needed to create a presentation of FLORA's agent pipelines without loading all real data.

## Features Included

1. **Agent Pipeline Visualization**: Shows agent workflows and processing steps
2. **Minimal Data Requirements**: Only essential data for demonstration
3. **Grouping Functionality**: Demonstrates both standard and enriched grouping
4. **Lightweight Setup**: Quick startup without full data ingestion

## Setup Instructions

### 1. Create Agent Presentation Environment

```bash
./scripts/setup_agent_presentation.sh
```

### 2. Run the Agent Presentation

```bash
cd presentation_agents
./start_agent_presentation.sh
```

## Files Created

- `presentation_agents/`: Complete agent presentation environment with startup script
- `scripts/setup_agent_presentation.sh`: Sets up agent-focused presentation environment
- `demo_data/`: Minimal demonstration data including:
  - metadata.tsv: Sample metadata with grouping columns
  - asv.tsv: Minimal ASV abundance table
  - taxonomy.tsv: Minimal taxonomy mapping

## Presentation Components

The agent presentation includes:

1. **Dashboard View**: Shows minimal sample statistics and agent status
2. **Pipeline View**: Displays agent workflow execution steps
3. **Explore Summary**: Taxonomic trees and diversity analysis
4. **Grouping Analysis**: Different grouping methods (biome, site, etc.)
5. **Agent Workflows**: Visual representation of agent-based processing

All data is minimal so it loads quickly, allowing you to focus on demonstrating the agent pipelines and workflows rather than waiting for data ingestion.