#!/usr/bin/env bash
# Save LLM analyses and results to persistent storage

set -euo pipefail

echo "Saving LLM analyses and results..."

# Create analyses directory
ANALYSES_DIR="analyses"
mkdir -p "$ANALYSES_DIR"

# Save current workspace data to JSON
echo "Saving workspace data..."
flora ui --workdir . --host 0.0.0.0 --port 8766 --no-browser &
UI_PID=$!

# Give UI time to start
sleep 3

# Save dashboard data
curl -s "http://localhost:8766/api/dashboard" > "$ANALYSES_DIR/dashboard.json" 2>/dev/null || echo "Could not save dashboard data"

# Save pipeline data  
curl -s "http://localhost:8766/api/pipeline" > "$ANALYSES_DIR/pipeline.json" 2>/dev/null || echo "Could not save pipeline data"

# Save explore summary data
curl -s "http://localhost:8766/api/explore/summary" > "$ANALYSES_DIR/explore_summary.json" 2>/dev/null || echo "Could not save explore summary data"

# Kill the UI process
kill $UI_PID 2>/dev/null || true

echo "LLM analyses saved to $ANALYSES_DIR/"