# FLORA — Technical Project Report

**Version:** 0.1.0 (Alpha)  
**Date:** April 2026  
**License:** MIT

---

## 1. Project Overview

FLORA (Feature Learning and Omics Research Analytics) is a Python library for end-to-end 16S rRNA amplicon microbiome analysis. It integrates sequence processing (QIIME 2 / DADA2), an in-process analytical database (DuckDB), compositionality-aware feature engineering, machine learning (scikit-learn, XGBoost, SHAP), and interactive HTML reporting into a single, installable package.

The project was developed to address the absence of a unified, production-ready Python tool that handles the full pipeline from raw sequencing data to interpretable ML predictions without requiring users to manually integrate multiple bioinformatics and data science libraries.

---

## 2. Objectives

1. Provide a single Python package that covers the complete microbiome ML workflow.
2. Apply compositionality-correct normalization (CLR) by default to avoid statistical artifacts.
3. Use an in-process database (DuckDB + Parquet) to handle datasets that exceed available RAM.
4. Integrate with public data repositories (MGnify, NCBI SRA, EMP) via programmatic downloaders.
5. Support QIIME 2 / DADA2 natively through the QIIME 2 Python SDK.
6. Produce self-contained HTML reports that require no server or internet connection to view.
7. Expose a CLI for non-programmatic use.

---

## 3. Architecture

### 3.1 Layer Overview

```
Layer 1 — Data Acquisition:      MGnify, NCBI SRA, EarthMicrobiome downloaders
Layer 2 — Validation:            FASTQ, manifest, metadata validators
Layer 3 — Sequence Processing:   QIIME 2 / DADA2 (optional)
Layer 4 — Storage:               DuckDB + Parquet (star schema)
Layer 5 — Feature Engineering:   CLR, TSS, rarefaction, PCoA, UMAP, filters
Layer 6 — Machine Learning:      Classifier, Regressor, Clusterer, SHAP, Optuna
Layer 7 — Output:                Plotly visualization, HTML reports, MLflow tracking
```

### 3.2 Key Design Decisions

**DuckDB as central store.** All data passes through DuckDB. Feature matrices are never persisted as CSV or pickled DataFrames. This eliminates file-based state between stages, reduces disk usage through columnar Parquet compression, and allows SQL joins across tables without loading everything into memory simultaneously.

**Polars over pandas.** The feature engineering layer uses Polars for its lazy evaluation, zero-copy Arrow interop with DuckDB, and faster pivot / groupby operations on wide ASV matrices.

**CLR default.** Every call to `get_feature_matrix()` or `db.pivot_asv()` applies CLR by default. Users who want TSS or raw counts must explicitly pass `normalize="tss"` or `normalize="none"`. This mirrors the recommendation in Gloor et al. (2017) and prevents the most common methodological error in microbiome ML studies.

**QIIME 2 as optional dependency.** The `qiime2` extra is optional. The entire DuckDB, ML, visualization, and reporting stack operates on pre-processed TSV / BIOM files. Users without QIIME 2 can still use FLORA with outputs from any other denoising tool (e.g., DADA2 run in R).

---

## 4. Package Structure

```
src/flora/
├── __init__.py               exports FloraError, __version__
├── config/                   FloraConfig, DatabaseConfig (Pydantic)
├── core/                     logging, exceptions
├── db/                       FloraDB, schema DDL, ingestion helpers
├── io/                       MGnifyDownloader, NCBISRADownloader, validators
├── diversity/                alpha (Shannon, Chao1, Faith PD, Simpson, observed)
│                             beta (Bray-Curtis, UniFrac)
├── feature_engineering/      normalization, selection, reduction, encoding
├── ml/
│   ├── classification/       MicrobiomeClassifier
│   ├── clustering/           MicrobiomeClusterer
│   ├── regression/           MicrobiomeRegressor
│   ├── explainability/       SHAPAnalyzer
│   ├── optimization/         HyperparameterTuner
│   └── evaluation/           metrics, bias, cross-validation
├── viz/                      taxonomy, diversity, ML plots (Plotly)
├── reports/                  FLORAReport (HTML generator)
├── pipelines/                FLORAPipeline (high-level orchestration)
└── ui/                       CLI (flora command), HTTP server
```

---

## 5. Modules — Detailed Description

### 5.1 Configuration (`flora.config`)

Configuration is managed via Pydantic models (`FloraConfig`, `DatabaseConfig`) loaded from a YAML file or environment variables. Validation errors are raised at startup, not at pipeline runtime.

Key parameters:

| Parameter | Default | Description |
|---|---|---|
| `workdir` | `results/` | Directory for DuckDB file and outputs |
| `database.path` | `{workdir}/flora.duckdb` | DuckDB file path |
| `database.memory_limit` | `4GB` | DuckDB memory limit |
| `pipeline.sampling_depth` | `10000` | Rarefaction depth |
| `pipeline.normalization` | `clr` | Default normalization |
| `pipeline.min_prevalence` | `0.1` | Minimum feature prevalence |
| `ml.cv_folds` | `5` | Cross-validation folds |
| `ml.n_trials` | `50` | Optuna hyperparameter trials |

### 5.2 Data Acquisition (`flora.io`)

Three downloaders:

- `MGnifyDownloader.fetch(study_accession, output_dir, max_samples)` — queries the MGnify REST API, filters by biome string, downloads TSV analysis files.
- `NCBISRADownloader.fetch(run_accessions, output_dir, n_jobs)` — calls `prefetch` and `fasterq-dump` in parallel.
- `EarthMicrobiomeDownloader.fetch(study_id, output_dir)` — downloads EMP per-study files.

Three validators:

- `FASTQValidator.validate(path)` — checks phred scores, read length distribution.
- `ManifestValidator.validate(path)` — checks required QIIME 2 manifest columns and path existence.
- `MetadataValidator.validate(path, required_columns)` — checks schema and reports missing or malformed fields.

### 5.3 DuckDB Analytics Core (`flora.db`)

`FloraDB` wraps a DuckDB connection and exposes:

- `ingest_metadata`, `ingest_asv_table`, `ingest_taxonomy` — load TSV/BIOM files into DuckDB tables.
- `query(sql)` — execute raw SQL, returns a result object with `.to_polars()` and `.to_pandas()`.
- `pivot_asv(normalize)` — SQL PIVOT from long to wide feature matrix with optional normalization.
- `aggregate_by_taxon(level, group_by)` — JOIN + GROUP BY query against the taxonomy table.
- `slice(train_filter, test_filter, features, target_column)` — SQL WHERE-based train/test split.

The star schema:

```sql
CREATE TABLE samples (
    sample_id TEXT PRIMARY KEY,
    biome TEXT,
    location TEXT,
    -- additional metadata columns
);

CREATE TABLE asv (
    sample_id TEXT REFERENCES samples(sample_id),
    feature_id TEXT,
    abundance DOUBLE
);

CREATE TABLE taxonomy (
    feature_id TEXT PRIMARY KEY,
    kingdom TEXT, phylum TEXT, class TEXT,
    "order" TEXT, family TEXT, genus TEXT, species TEXT
);

CREATE TABLE diversity_alpha (
    sample_id TEXT REFERENCES samples(sample_id),
    metric TEXT,
    value DOUBLE
);

CREATE TABLE pipeline_log (
    step TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    params JSON
);
```

### 5.4 Feature Engineering (`flora.feature_engineering`)

All functions operate on Polars DataFrames and return Polars DataFrames.

**CLR transform:**

```python
def clr_transform(df: pl.DataFrame, pseudo_count: float = 0.5) -> pl.DataFrame:
    # Adds pseudo_count to all values
    # Computes per-row geometric mean
    # Applies log(x / geometric_mean) elementwise
```

**Rarefaction:**

```python
def rarefy(df: pl.DataFrame, depth: int, seed: int = 42) -> pl.DataFrame:
    # Drops samples with total count < depth
    # For each remaining sample, draws depth counts via multinomial sampling
```

**Prevalence filter:**

```python
def filter_by_prevalence(df: pl.DataFrame, min_prevalence: float = 0.1) -> pl.DataFrame:
    # Keeps features with fraction of non-zero samples >= min_prevalence
```

**PCoA:**

```python
def compute_pcoa(df: pl.DataFrame, metric: str = "braycurtis", n_components: int = 3) -> pl.DataFrame:
    # Computes pairwise distance matrix via scipy.spatial.distance.cdist
    # Eigendecomposition via scikit-bio.stats.ordination.pcoa
    # Returns DataFrame with sample_id and PC1..PCn columns
```

### 5.5 Machine Learning (`flora.ml`)

**MicrobiomeClassifier:**

```python
clf = MicrobiomeClassifier(model="xgboost", target_column="biome")
result = clf.fit(train_df, test_df, cv_folds=5)
# result.accuracy, result.f1_macro, result.roc_auc
# result.model (fitted estimator)
# result.feature_names, result.feature_importances
# result.classification_report (string)
```

Internal workflow:
1. Separates features from target column.
2. Runs `StratifiedKFold` cross-validation on train_df.
3. Fits final model on all of train_df.
4. Evaluates on test_df.

**SHAPAnalyzer:**

```python
shap_analyzer = SHAPAnalyzer(model=result.model, feature_names=result.feature_names)
shap_result = shap_analyzer.explain(test_df)
# shap_result.global_importance (DataFrame ranked by mean |SHAP|)
# shap_result.shap_values (NumPy array)
fig = shap_analyzer.summary_plot(shap_result)
```

**HyperparameterTuner:**

Uses Optuna TPE sampler. Search spaces:

- `random_forest`: `n_estimators` [50,500], `max_depth` [3,20], `min_samples_split` [2,10], `max_features` ["sqrt","log2"]
- `xgboost`: `n_estimators` [50,500], `max_depth` [3,10], `learning_rate` [1e-3,0.3], `subsample` [0.5,1.0], `colsample_bytree` [0.5,1.0]
- `svm`: `C` [1e-3,100], `kernel` ["linear","rbf"], `gamma` ["scale","auto"]

### 5.6 Visualization (`flora.viz`)

All functions return `plotly.graph_objects.Figure`. Figures can be written to HTML with `.write_html()`, to PNG with `.write_image()` (requires kaleido), or embedded in `FLORAReport`.

### 5.7 HTML Reports (`flora.reports`)

`FLORAReport` uses Jinja2 with an internal template. Plotly figures are serialized to JSON with `plotly.io.to_json()` and embedded inline. The resulting HTML file is fully self-contained (no CDN dependencies) and works offline.

Report sections:
- `add_metrics(title, dict)` — renders a metrics card grid.
- `add_text(title, str)` — renders a paragraph section.
- `add_plot(title, fig)` — embeds a Plotly figure.
- `add_table(title, df)` — renders a sortable HTML table.

---

## 6. Testing

Tests are located in `tests/` and split into unit and integration suites.

```
tests/
├── conftest.py               shared fixtures (in-memory DB, synthetic ASV data)
├── unit/
│   ├── test_config.py        FloraConfig loading and validation
│   ├── test_exceptions.py    exception hierarchy
│   ├── test_diversity.py     alpha/beta diversity functions
│   ├── test_normalization.py CLR, TSS, rarefaction
│   └── test_validators.py    FASTQ, manifest, metadata validators
└── integration/
    ├── test_db_pipeline.py   DuckDB ingestion, queries, pivot, slice
    └── test_full_pipeline.py FLORAPipeline end-to-end with synthetic data
```

Run with:

```bash
pytest tests/ -v --cov=flora --cov-report=html
```

All tests use `FloraDB.connect(":memory:")` and synthetically generated DataFrames. No external files or network access required. Minimum coverage: 70% (enforced in CI via `--cov-fail-under=70`).

---

## 7. Running the Project

### 7.1 Install

```bash
# From PyPI
pip install flora-bio

# Development
git clone https://github.com/flora-bio/flora
cd flora
pip install -e ".[dev]"

# Conda
conda env create -f environment.yml
conda activate flora
```

### 7.2 Run built-in example (no external data)

```bash
python examples/basic_pipeline.py
```

Produces `results/report.html` using in-memory synthetic data.

### 7.3 Download public data and run pipeline

```bash
# Step 1: download
flora download mgnify MGYS00005116 --outdir data/raw --max-samples 80

# Step 2: run pipeline from config
flora run config.yaml --workdir results/
```

### 7.4 Start web interface

```bash
flora ui --host 127.0.0.1 --port 8765 --workdir results/
# Open http://127.0.0.1:8765 in browser
```

### 7.5 Run tests

```bash
pytest tests/ -v --cov=flora --cov-report=html
# Coverage report in htmlcov/index.html
```

### 7.6 Build documentation

```bash
mkdocs serve   # local preview at http://127.0.0.1:8000
mkdocs build   # static site in site/
```

### 7.7 Lint and type-check

```bash
ruff check src/
mypy src/flora/
```

---

## 8. Dependencies Summary

| Package | Version | Role |
|---|---|---|
| duckdb | >=0.10.0 | In-process SQL analytics |
| polars | >=0.20.0 | High-performance DataFrames |
| pyarrow | >=14.0.0 | Parquet I/O, Arrow format |
| pandas | >=2.1.0 | Compatibility layer |
| numpy | >=1.26.0 | Numerical computing |
| scipy | >=1.11.0 | Statistical functions |
| scikit-learn | >=1.4.0 | ML algorithms and evaluation |
| xgboost | >=2.0.0 | Gradient boosted trees |
| shap | >=0.44.0 | Model explainability |
| optuna | >=3.5.0 | Hyperparameter optimization |
| mlflow | >=2.10.0 | Experiment tracking |
| umap-learn | >=0.5.5 | UMAP dimensionality reduction |
| plotly | >=5.18.0 | Interactive visualization |
| kaleido | >=0.2.1 | Static image export |
| jinja2 | >=3.1.0 | HTML report templating |
| pydantic | >=2.5.0 | Configuration validation |
| rich | >=13.7.0 | Terminal output formatting |
| requests | >=2.31.0 | HTTP downloads |
| tqdm | >=4.66.0 | Progress bars |
| biom-format | >=2.1.0 | BIOM file I/O |
| scikit-bio | >=0.5.0 | Biological sequence processing |
| hdbscan | >=0.8.33 | Density-based clustering (optional) |
| imbalanced-learn | >=0.11.0 | SMOTE and resampling (optional) |
| qiime2 | any | QIIME 2 SDK (optional) |

---

## 9. Backlog Status

All 50 user stories across 8 epics are marked complete:

| Epic | Title | Stories |
|---|---|---|
| EP-01 | Infrastructure and Foundation | 6 / 6 |
| EP-02 | Data Acquisition and Validation | 6 / 6 |
| EP-03 | QIIME 2 / DADA2 Pipeline | 8 / 8 |
| EP-04 | DuckDB Analytics Layer | 7 / 7 |
| EP-05 | Feature Engineering for ML | 6 / 6 |
| EP-06 | Machine Learning Module | 9 / 9 |
| EP-07 | Visualization and Reports | 5 / 5 |
| EP-08 | Testing, Documentation, Publication | 3 / 3 |

---

## 10. Known Limitations

- **QIIME 2 compatibility**: QIIME 2 releases new versions quarterly and sometimes introduces breaking changes to the SDK. FLORA's QIIME 2 integration has been tested against version 2023.9.
- **Rarefaction discards samples**: samples below the chosen depth are dropped. On datasets with uneven coverage, this can significantly reduce sample count. Use rarefaction curves to choose a depth that retains enough samples.
- **SHAP for SVM**: TreeSHAP is not available for SVM. FLORA falls back to KernelSHAP, which is slower and approximate.
- **HDBSCAN is optional**: install with `pip install "flora-bio[hdbscan]"`.
- **Windows support**: sra-tools and QIIME 2 have limited Windows support. All other FLORA functionality works on Windows.

---

## 11. Future Work

- Differential abundance testing (DESeq2-equivalent in Python, ANCOM-BC port).
- Metagenome-assembled genome (MAG) workflow integration.
- Multi-omics integration (16S + metabolomics feature fusion).
- Jupyter notebook tutorials with real datasets.
- GPU-accelerated UMAP and HDBSCAN via RAPIDS cuML.
- REST API server for remote pipeline execution.
- Docker image for reproducible deployment.

---

## 12. References

See [methods.md](methods.md) and [article.md](article.md) for the full reference list.

Key references for this report:

- Bolyen et al. (2019). QIIME 2. *Nature Biotechnology*, 37, 852-857. https://doi.org/10.1038/s41587-019-0209-9
- Callahan et al. (2016). DADA2. *Nature Methods*, 13, 581-583. https://doi.org/10.1038/nmeth.3869
- Gloor et al. (2017). Microbiome Datasets Are Compositional. *Frontiers in Microbiology*, 8, 2224. https://doi.org/10.3389/fmicb.2017.02224
- Raasveldt & Muehleisen (2019). DuckDB. *SIGMOD 2019*. https://doi.org/10.1145/3299869.3320212
- Thompson et al. (2017). Earth Microbiome Project. *Nature*, 551, 457-463. https://doi.org/10.1038/nature24621
