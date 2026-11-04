#!/usr/bin/env bash
# Install FLORA's optional engines and connect FLORA to them, all inside this repository.
#
#   scripts/setup_engines.sh                 R + DADA2 + ALDEx2 + ANCOM-BC2 + vegan + VSEARCH + cutadapt + scikit-bio
#   scripts/setup_engines.sh --qiime2        also QIIME 2 (large download, several GB)
#   scripts/setup_engines.sh --system        use the micromamba/mamba/conda already on PATH instead of a local copy
#   scripts/setup_engines.sh --workdir DIR   where FLORA keeps engines.json (default: results)
#   scripts/setup_engines.sh --dry-run       print what would be done, download nothing
#
# By default nothing is installed outside this folder: the package manager and the environments go to ./.engines
# (ignored by git). Delete that folder to remove everything. Downloads come over HTTPS from micro.mamba.pm,
# conda-forge, bioconda and data.qiime2.org.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"  # FLORA looks for ./.engines and ./results relative to the repository
ENGINES_DIR="$HERE/.engines"
QIIME2=0
SYSTEM=0
DRY=0
WORKDIR=results
QIIME2_DIST="${QIIME2_DIST:-amplicon-2024.10}"

while [ $# -gt 0 ]; do
  case "$1" in
    --qiime2) QIIME2=1 ;;
    --system) SYSTEM=1 ;;
    --dry-run) DRY=1 ;;
    --workdir) WORKDIR="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }

platform() {
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) echo linux-64 ;;
    Linux-aarch64|Linux-arm64) echo linux-aarch64 ;;
    Darwin-x86_64) echo osx-64 ;;
    Darwin-arm64) echo osx-arm64 ;;
    *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
  esac
}

# ---- package manager --------------------------------------------------------
if [ "$SYSTEM" = 1 ]; then
  for m in micromamba mamba conda; do
    if command -v "$m" >/dev/null; then MGR="$m"; break; fi
  done
  : "${MGR:?--system needs micromamba, mamba or conda on PATH}"
else
  MGR="$ENGINES_DIR/bin/micromamba"
  export MAMBA_ROOT_PREFIX="$ENGINES_DIR/mamba"
  if [ ! -x "$MGR" ]; then
    P="$(platform)"
    echo "==> downloading micromamba ($P) into $ENGINES_DIR/bin"
    run mkdir -p "$ENGINES_DIR/bin"
    if [ "$DRY" = 1 ]; then
      echo "[dry-run] curl -fsSL https://micro.mamba.pm/api/micromamba/$P/latest | tar -xj -C $ENGINES_DIR bin/micromamba"
    else
      curl -fsSL "https://micro.mamba.pm/api/micromamba/$P/latest" | tar -xj -C "$ENGINES_DIR" bin/micromamba
    fi
  fi
  if [ "$DRY" != 1 ]; then "$MGR" --version; fi
fi

# micromamba spells it "create", conda and mamba "env create"
create() {
  if [ "$(basename "$MGR")" = micromamba ]; then run "$MGR" create -y "$@"; else run "$MGR" env create -y "$@"; fi
}

have_env() {
  [ "$DRY" = 1 ] && return 1
  if [ "$(basename "$MGR")" = micromamba ]; then "$MGR" env list | grep -qw "$1"; else "$MGR" env list | grep -qw "$1"; fi
}

# ---- environments -----------------------------------------------------------
CONNECT=(--r-env flora-engines)
if have_env flora-engines; then
  echo "==> flora-engines already exists, skipping"
else
  echo "==> creating flora-engines (R, DADA2, ALDEx2, ANCOM-BC2, vegan, VSEARCH, cutadapt, scikit-bio)"
  create -f "$HERE/environment-engines.yml"
fi

if [ "$QIIME2" = 1 ]; then
  NAME="qiime2-${QIIME2_DIST}"
  CONNECT+=(--qiime-env "$NAME")
  if have_env "$NAME"; then
    echo "==> $NAME already exists, skipping"
  else
    YML="qiime2-${QIIME2_DIST}-py310-linux-conda.yml"
    URL="https://data.qiime2.org/distro/${QIIME2_DIST%%-*}/${YML}"
    echo "==> creating $NAME from $URL"
    if [ "$DRY" = 1 ]; then
      echo "[dry-run] curl -fsSL $URL -o <tmp>/$YML"
      create -n "$NAME" -f "<tmp>/$YML"
    else
      TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
      curl -fsSL "$URL" -o "$TMP/$YML"
      create -n "$NAME" -f "$TMP/$YML"
    fi
  fi
fi

# ---- connect FLORA ----------------------------------------------------------
echo "==> connecting FLORA"
export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/micromamba}"
run flora engines connect --workdir "$WORKDIR" "${CONNECT[@]}"
run flora engines doctor --workdir "$WORKDIR"
echo "==> done. Real-tool tests:  pytest tests/real_engines -v --no-cov"
