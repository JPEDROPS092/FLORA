#!/usr/bin/env bash
# Setup script for FLORA presentation environment
# This script prepares the environment for a complete application demonstration

set -euo pipefail

echo "=== Setting up FLORA Presentation Environment ==="

# Set working directory
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# Create presentation directory
PRESENTATION_DIR="$HERE/presentation"
mkdir -p "$PRESENTATION_DIR"

# Copy essential files for presentation
echo "Copying presentation assets..."
cp -r docs/assets/* "$PRESENTATION_DIR/" 2>/dev/null || true
cp README.md "$PRESENTATION_DIR/"
cp LICENSE "$PRESENTATION_DIR/"

# Create a demo data directory
DEMO_DIR="$PRESENTATION_DIR/demo_data"
mkdir -p "$DEMO_DIR"

# Generate synthetic data for demo
echo "Generating synthetic data for presentation..."
flora download synthetic --output-dir "$DEMO_DIR" --samples 50 --features 100 --seed 42

# Ingest the data
echo "Ingesting synthetic data..."
flora ingest "$DEMO_DIR/raw"

# Create a presentation-ready configuration
cat > "$PRESENTATION_DIR/config.yaml" << EOF
# FLORA Presentation Configuration
workdir: "$PRESENTATION_DIR"
ui:
  host: "0.0.0.0"
  port: 8765
  browser: false
EOF

# Create a startup script for the presentation
cat > "$PRESENTATION_DIR/start_presentation.sh" << 'EOF'
#!/bin/bash
# Startup script for FLORA presentation
set -euo pipefail

echo "Starting FLORA presentation environment..."
echo "Working directory: $(pwd)"

# Start the UI in the background
flora ui --workdir "$(pwd)" --host 0.0.0.0 --port 8765 --no-browser &
UI_PID=$!

# Wait for UI to start
sleep 5

echo "FLORA UI is now running on http://localhost:8765"
echo "PID: $UI_PID"
echo ""
echo "To stop the presentation:"
echo "  kill $UI_PID"

# Keep script running
wait $UI_PID
EOF

chmod +x "$PRESENTATION_DIR/start_presentation.sh"

# Create a README for the presentation
cat > "$PRESENTATION_DIR/README.md" << 'EOF'
# FLORA Presentation Environment

This directory contains all necessary files for presenting FLORA.

## Files

- `start_presentation.sh`: Script to start the FLORA UI
- `config.yaml`: Configuration for the presentation
- `demo_data/`: Synthetic data for demonstration

## Getting Started

1. Run the startup script:
   ```bash
   ./start_presentation.sh
   ```

2. Access the UI at http://localhost:8765

3. The presentation includes:
   - Dashboard with sample statistics
   - Pipeline view with QC results
   - Exploration summary with taxonomic trees
   - Differential abundance analysis
   - Machine learning classification results

## Data

The demo uses synthetic data generated with:
- 50 samples
- 100 ASVs (Amplicon Sequence Variants)
- 4 biome categories (Amazon, Atlantic_Forest, Cerrado, Pantanal)
EOF

echo "=== Presentation environment setup complete ==="
echo "To start the presentation:"
echo "  cd $PRESENTATION_DIR"
echo "  ./start_presentation.sh"