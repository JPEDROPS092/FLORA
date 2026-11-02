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

# Angular 21's application builder outputs to dist/browser when outputPath
# is "dist" (older CLIs used dist/app or dist/app/browser). Flatten whatever
# exists into dist/ so the Python package can serve it.
SRC=""
for candidate in "$FRONT_DIR/dist/browser" "$FRONT_DIR/dist/app/browser" "$FRONT_DIR/dist/app"; do
  if [ -d "$candidate" ]; then
    SRC="$candidate"
    break
  fi
done

if [ -n "$SRC" ]; then
  echo "==> Copying built assets to $DIST_TARGET..."
  # The build output lives inside DIST_TARGET itself; stage it in a temp dir
  # first so we can replace dist/ without deleting the source mid-copy.
  TMP_DIR="$(mktemp -d)"
  cp -r "$SRC"/* "$TMP_DIR/"
  rm -rf "$DIST_TARGET"
  mkdir -p "$DIST_TARGET"
  cp -r "$TMP_DIR"/* "$DIST_TARGET/"
  rm -rf "$TMP_DIR"

  # Remove source maps from production builds
  find "$DIST_TARGET" -name "*.map" -delete 2>/dev/null || true

  echo "==> Frontend built successfully. Assets at: $DIST_TARGET"
  du -sh "$DIST_TARGET"
else
  echo "ERROR: Build output not found (checked dist/browser, dist/app/browser, dist/app)" >&2
  exit 1
fi
