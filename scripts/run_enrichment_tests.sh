#!/usr/bin/env bash
# Run all tests related to enrichment and grouping functionality

set -euo pipefail

echo "Running tests for enrichment and grouping functionality..."

# Run the specific tests we created
pytest tests/integration/test_enrichment.py tests/integration/test_grouping.py -v

echo "All enrichment and grouping tests completed."