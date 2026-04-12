# Installation

## Requirements

- Python 3.11 or 3.12
- pip or conda

Optional for QIIME 2 integration:
- QIIME 2 (2023.9+) installed in a separate conda environment
- sra-tools (for NCBI SRA downloads)

---

## Option 1 — pip (recommended)

```bash
pip install flora-bio
```

To install optional extras:

```bash
# HDBSCAN clustering
pip install "flora-bio[hdbscan]"

# SMOTE and imbalanced-learn utilities
pip install "flora-bio[imbalanced]"

# QIIME 2 SDK integration
pip install "flora-bio[qiime2]"

# All optional extras
pip install "flora-bio[hdbscan,imbalanced,qiime2]"
```

---

## Option 2 — conda environment

```bash
git clone https://github.com/flora-bio/flora
cd flora
conda env create -f environment.yml
conda activate flora
```

---

## Option 3 — development install

```bash
git clone https://github.com/flora-bio/flora
cd flora
pip install -e ".[dev]"
```

The `dev` extra includes pytest, ruff, mypy, and mkdocs.

---

## Verify installation

```python
import flora
print(flora.__version__)
# 0.1.0
```

```bash
flora --help
```

---

## QIIME 2 setup (optional)

FLORA integrates with QIIME 2 through its Python SDK. Install QIIME 2 in the same environment:

```bash
conda install -c conda-forge -c bioconda qiime2
```

Or follow the official instructions at https://docs.qiime2.org/2024.2/install/

If QIIME 2 is not installed, FLORA operates entirely on pre-processed BIOM / TSV files exported from any external tool. All DuckDB, ML, visualization, and reporting features remain available without QIIME 2.

---

## sra-tools setup (optional, for NCBI SRA downloads)

```bash
conda install -c bioconda sra-tools
```

Required only if using `NCBISRADownloader`. The MGnify and EarthMicrobiome downloaders work without it.
