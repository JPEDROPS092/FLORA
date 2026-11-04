#!/usr/bin/env bash
# Setup script for FLORA presentation environment showing agent pipelines
# This version focuses on agent workflows without loading all real data

set -euo pipefail

echo "=== Setting up FLORA Agent Pipeline Presentation Environment ==="

# Set working directory
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# Create presentation directory
PRESENTATION_DIR="$HERE/presentation_agents"
mkdir -p "$PRESENTATION_DIR"

# Copy essential files for presentation
echo "Copying presentation assets..."
cp README.md "$PRESENTATION_DIR/"
cp LICENSE "$PRESENTATION_DIR/"

# Create a minimal demo structure for agent demonstration
DEMO_DIR="$PRESENTATION_DIR/demo_data"
mkdir -p "$DEMO_DIR"

# Create a minimal synthetic data structure for agent demonstration
echo "Creating minimal agent demonstration data..."

# Create a simple metadata file for agent demonstration
cat > "$DEMO_DIR/metadata.tsv" << 'EOF'
sample_id	biome	site	depth
S001	Amazon	Site1	10
S002	Amazon	Site1	15
S003	Atlantic_Forest	Site2	12
S004	Atlantic_Forest	Site2	18
S005	Cerrado	Site3	20
S006	Cerrado	Site3	25
EOF

# Create a minimal ASV table for agent demonstration
cat > "$DEMO_DIR/asv.tsv" << 'EOF'
sample_id	f1	f2	f3
S001	100	50	25
S002	120	60	30
S003	80	40	20
S004	90	45	22
S005	110	55	28
S006	130	65	32
EOF

# Create a minimal taxonomy file for agent demonstration
cat > "$DEMO_DIR/taxonomy.tsv" << 'EOF'
feature_id	genus
f1	Bacteria
f2	Archaea
f3	Fungi
EOF

# Create a presentation-ready configuration
cat > "$PRESENTATION_DIR/config.yaml" << EOF
# FLORA Agent Pipeline Presentation Configuration
workdir: "$PRESENTATION_DIR"
ui:
  host: "0.0.0.0"
  port: 8765
  browser: false
EOF

# Create a startup script for the agent presentation
cat > "$PRESENTATION_DIR/start_agent_presentation.sh" << 'EOF'
#!/bin/bash
# Startup script for FLORA agent pipeline presentation
set -euo pipefail

echo "Starting FLORA agent pipeline presentation environment..."
echo "Working directory: $(pwd)"

# Create a simple database structure for agent demonstration
echo "Setting up minimal database structure..."

# Start the UI in the background
flora ui --workdir "$(pwd)" --host 0.0.0.0 --port 8765 --no-browser &
UI_PID=$!

# Wait for UI to start
sleep 5

echo "FLORA UI with agent pipeline view is now running on http://localhost:8765"
echo "PID: $UI_PID"
echo ""
echo "To stop the presentation:"
echo "  kill $UI_PID"

# Keep script running
wait $UI_PID
EOF

chmod +x "$PRESENTATION_DIR/start_agent_presentation.sh"

# Create a README for the agent presentation
cat > "$PRESENTATION_DIR/README.md" << 'EOF'
# FLORA Agent Pipeline Presentation

This directory contains a minimal presentation environment that demonstrates FLORA's agent pipelines and workflows without requiring full data loading.

## Files

- `start_agent_presentation.sh`: Script to start the FLORA UI with agent pipeline view
- `config.yaml`: Configuration for the agent presentation
- `demo_data/`: Minimal data for agent demonstration:
  - `metadata.tsv`: Sample metadata with grouping columns
  - `asv.tsv`: Minimal ASV abundance table
  - `taxonomy.tsv`: Minimal taxonomy mapping

## Getting Started

1. Run the startup script:
   ```bash
   ./start_agent_presentation.sh
   ```

2. Access the UI at http://localhost:8765

3. The presentation includes:
   - Dashboard with minimal sample statistics
   - Pipeline view showing agent workflows
   - Exploration summary with taxonomic trees
   - Grouping analysis with different metadata columns
   - Agent-based processing workflows

## Key Features Demonstrated

- Agent pipeline execution flow
- Metadata-based grouping capabilities
- Workflow visualization without full dataset loading
- Minimal data footprint for quick demonstrations

This setup allows you to showcase FLORA's agent-based processing capabilities without waiting for large data ingestion processes.
EOF

echo "=== Agent pipeline presentation environment setup complete ==="
echo "To start the presentation:"
echo "  cd $PRESENTATION_DIR"
echo "  ./start_agent_presentation.sh"