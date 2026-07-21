#!/usr/bin/env bash
# Build the Angular frontend and copy static assets to Python package location.
# Usage: ./scripts/build_frontend.sh [--dev]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONT_DIR="$PROJECT_ROOT/src/flora/front"
DIST_TARGET="$PROJECT_ROOT/src/flora/front/dist"

MODE="${1:---prod}"

echo "==> Building Angular frontend ($MODE)..."

cd "$FRONT_DIR"

if [ ! -d "node_modules" ]; then
  echo "==> Installing npm dependencies..."
  npm ci --no-audit --no-fund
fi

if [ "$MODE" = "--dev" ]; then
  npx ng build --configuration development
else
  npx ng build --configuration production
fi

# The Angular CLI outputs to dist/app/ by default when outputPath is "dist"
# We need to flatten it to dist/ for the Python package
SRC="$FRONT_DIR/dist/app/browser"
if [ ! -d "$SRC" ]; then
  SRC="$FRONT_DIR/dist/app"
fi

if [ -d "$SRC" ]; then
  echo "==> Copying built assets to $DIST_TARGET..."
  rm -rf "$DIST_TARGET"
  mkdir -p "$DIST_TARGET"
  cp -r "$SRC"/* "$DIST_TARGET/"

  # Remove source maps from production builds
  find "$DIST_TARGET" -name "*.map" -delete 2>/dev/null || true

  echo "==> Frontend built successfully. Assets at: $DIST_TARGET"
  du -sh "$DIST_TARGET"
else
  echo "ERROR: Build output not found at $SRC" >&2
  exit 1
fi
