# User Guide

Complete reference for all FLORA modules.

---

## Table of Contents

1. [Configuration](#1-configuration)
2. [Data Acquisition](#2-data-acquisition)
3. [Data Validation](#3-data-validation)
4. [QIIME 2 / DADA2 Pipeline](#4-qiime-2--dada2-pipeline)
5. [DuckDB Analytics Core](#5-duckdb-analytics-core)
6. [Feature Engineering](#6-feature-engineering)
7. [Machine Learning](#7-machine-learning)
8. [Visualization](#8-visualization)
9. [HTML Reports](#9-html-reports)
10. [Pipeline Orchestration](#10-pipeline-orchestration)
11. [CLI Reference](#11-cli-reference)
12. [Logging and Exceptions](#12-logging-and-exceptions)

---

## 1. Configuration

FLORA is configured via a YAML file or programmatically via `FloraConfig`.

### YAML configuration

```yaml
# config.yaml
workdir: results/
database:
  path: results/flora.duckdb
  memory_limit: "4GB"
pipeline:
  sampling_depth: 10000
  normalization: clr
  min_prevalence: 0.1
ml:
  model: xgboost
  cv_folds: 5
  n_trials: 50
logging:
  level: INFO
```

### Programmatic configuration

```python
from flora.config import FloraConfig, DatabaseConfig

config = FloraConfig(
    workdir="results/",
    database=DatabaseConfig(path="results/flora.duckdb", memory_limit="4GB"),
)
```

### Environment variables

Any config key can be set via environment variable with the prefix `FLORA_`:

```bash
export FLORA_WORKDIR=results/
export FLORA_DATABASE_MEMORY_LIMIT=8GB
```

---

## 2. Data Acquisition

### MGnify

Downloads analysis results from the EMBL-EBI MGnify API (https://www.ebi.ac.uk/metagenomics/).

```python
from flora.io import MGnifyDownloader

dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")

# Fetch by study accession
manifest = dl.fetch(
    study_accession="MGYS00005116",
    output_dir="data/raw",
    max_samples=80,
)
```

The downloader retrieves:
- Sample metadata (TSV)
- Taxonomic assignments (TSV, OTU table format)
- Analysis summary statistics

### NCBI SRA

Downloads raw FASTQ files using `prefetch` and `fasterq-dump` from sra-tools.

```python
from flora.io import NCBISRADownloader

sra = NCBISRADownloader(n_jobs=4)
manifest = sra.fetch(
    run_accessions=["SRR12345678", "SRR12345679"],
    output_dir="data/raw",
)
```

Requires sra-tools installed and accessible on PATH.

### Earth Microbiome Project

```python
from flora.io import EarthMicrobiomeDownloader

emp = EarthMicrobiomeDownloader()
manifest = emp.fetch(study_id="EMP_2017", output_dir="data/raw")
```

---

## 3. Data Validation

### FASTQ validation

```python
from flora.io import FASTQValidator

validator = FASTQValidator()
report = validator.validate("data/raw/sample_R1.fastq.gz")
print(report.is_valid, report.n_reads, report.mean_quality)
```

### QIIME 2 manifest validation

```python
from flora.io import ManifestValidator

mv = ManifestValidator()
result = mv.validate("data/raw/manifest.tsv")
# Raises ValidationError if required columns are missing or paths do not exist
```

### Metadata validation

```python
from flora.io import MetadataValidator

mv = MetadataValidator(required_columns=["sample_id", "biome"])
result = mv.validate("data/raw/metadata.tsv")
print(result.warnings)
```

---

## 4. QIIME 2 / DADA2 Pipeline

Requires `qiime2` installed (`pip install "flora-bio[qiime2]"`).

```python
from flora.pipelines import FLORAPipeline

pipeline = FLORAPipeline(workdir="results/")

# Import FASTQ files using a paired-end manifest
pipeline.import_fastq(manifest_path="data/raw/manifest.tsv", input_format="PairedEndFastqManifestPhred33V2")

# Denoise with DADA2
pipeline.denoise_dada2(
    trim_left_f=0,
    trim_left_r=0,
    trunc_len_f=250,
    trunc_len_r=200,
)

# Classify taxonomy against SILVA 138
pipeline.classify_taxonomy(classifier_path="classifiers/silva-138-99-nb-classifier.qza")

# Build phylogenetic tree
pipeline.build_phylogeny()

# Compute alpha diversity
pipeline.compute_diversity(sampling_depth=10000)
```

Results are automatically exported to Parquet and ingested into DuckDB.

---

## 5. DuckDB Analytics Core

`FloraDB` is the central data access object. All analytical queries run via SQL inside DuckDB.

### Connect

```python
from flora.db import FloraDB

# File-backed (persistent)
db = FloraDB.connect("results/flora.duckdb")

# In-memory (ephemeral, for testing)
db = FloraDB.connect(":memory:")
```

### Ingest data

```python
db.ingest_metadata("data/raw/metadata.tsv")
db.ingest_asv_table("data/raw/asv_table.tsv", wide_format=True)
db.ingest_taxonomy("data/raw/taxonomy.tsv")
```

### Ad-hoc SQL

```python
df = db.query("""
    SELECT t.phylum, AVG(a.abundance) AS mean_abundance
    FROM asv a
    JOIN taxonomy t USING(feature_id)
    JOIN samples s USING(sample_id)
    WHERE s.biome = 'Amazon'
    GROUP BY t.phylum
    ORDER BY mean_abundance DESC
""").to_polars()
```

### High-level helpers

```python
# Wide feature matrix (samples x ASVs)
wide = db.pivot_asv(normalize="clr")

# Taxonomic roll-up
taxon = db.aggregate_by_taxon(level="phylum", group_by="biome")

# Train/test split
train_df, test_df = db.slice(
    train_filter="biome = 'Amazon'",
    test_filter="biome = 'Cerrado'",
    features="clr",
    target_column="biome",
)
```

### Schema

| Table | Description |
|---|---|
| `samples` | Sample metadata (sample_id, biome, location, pH, ...) |
| `asv` | Feature table in long format (sample_id, feature_id, abundance) |
| `taxonomy` | Taxonomic lineage per feature (kingdom → species) |
| `diversity_alpha` | Alpha diversity metrics per sample |
| `diversity_beta` | Beta diversity distance matrices |
| `dim_reduction` | PCoA / UMAP coordinates |
| `pipeline_log` | Audit trail of pipeline steps |

---

## 6. Feature Engineering

### Normalization

```python
from flora.feature_engineering import clr_transform, tss_transform, rarefy

# Centered Log-Ratio (recommended for ML)
clr_df = clr_transform(wide_asv_df)

# Total Sum Scaling
tss_df = tss_transform(wide_asv_df)

# Rarefaction (randomly subsample to uniform depth)
rarefied = rarefy(wide_asv_df, depth=10000)
```

CLR is the recommended normalization for machine learning. It handles the compositional nature of microbiome data by transforming relative abundances to a log-ratio space that is free of the unit-sum constraint.

### Rarefaction curves

```python
from flora.feature_engineering import rarefaction_curve

curve = rarefaction_curve(wide_asv_df, max_depth=50000, steps=10, n_resamples=20)
# Returns DataFrame with depth, mean_richness, ci_lower, ci_upper per sample
```

### Feature selection

```python
from flora.feature_engineering import filter_by_prevalence, select_by_importance

# Keep features present in at least 10% of samples
filtered = filter_by_prevalence(clr_df, min_prevalence=0.1)

# Keep top-N features by Random Forest importance
selected = select_by_importance(clr_df, target_series, top_n=100)
```

### Dimensionality reduction

```python
from flora.feature_engineering import compute_pcoa, compute_umap

# PCoA on Bray-Curtis distance matrix
pcoa_df = compute_pcoa(tss_df, metric="braycurtis", n_components=3)

# UMAP on CLR-normalized data
umap_df = compute_umap(clr_df, n_components=2, n_neighbors=15, min_dist=0.1)
```

### Metadata encoding

```python
from flora.feature_engineering import encode_metadata

# One-hot or label encoding for categorical metadata columns
encoded = encode_metadata(metadata_df, columns=["biome", "location"], method="onehot")
```

---

## 7. Machine Learning

### Classification

```python
from flora.ml import MicrobiomeClassifier

clf = MicrobiomeClassifier(model="xgboost", target_column="biome")
result = clf.fit(train_df, test_df, cv_folds=5)

print(result.accuracy)
print(result.f1_macro)
print(result.roc_auc)
print(result.classification_report)
print(result.feature_importances)
```

Available models: `"random_forest"`, `"svm"`, `"xgboost"`.

### Regression

Predict continuous variables such as diversity indices.

```python
from flora.ml import MicrobiomeRegressor

reg = MicrobiomeRegressor(model="random_forest", target_column="shannon")
result = reg.fit(train_df, test_df)

print(result.r2)
print(result.mae)
print(result.rmse)
```

### Clustering

```python
from flora.ml import MicrobiomeClusterer

# K-Means
clusterer = MicrobiomeClusterer(method="kmeans", n_clusters=4)
clusters = clusterer.fit(pcoa_df)

# HDBSCAN (requires flora-bio[hdbscan])
clusterer = MicrobiomeClusterer(method="hdbscan", min_cluster_size=5)
clusters = clusterer.fit(pcoa_df)

print(clusters.silhouette_score)
print(clusters.labels)
```

### SHAP explainability

```python
from flora.ml import SHAPAnalyzer

shap = SHAPAnalyzer(model=result.model, feature_names=result.feature_names)
shap_result = shap.explain(test_df)

print(shap_result.global_importance)   # ranked feature contributions
fig = shap.summary_plot(shap_result)   # Plotly figure
```

### Hyperparameter optimization

```python
from flora.ml import HyperparameterTuner

tuner = HyperparameterTuner(
    model="random_forest",
    task="classification",
    n_trials=50,
)
best = tuner.tune(train_df, target_column="biome")
print(best.best_params)
print(best.best_score)

# Use best params in a new classifier
clf = MicrobiomeClassifier(model="random_forest", model_params=best.best_params)
```

### Cross-validation

```python
from flora.ml.evaluation import cross_validate_pipeline

scores = cross_validate_pipeline(
    feature_matrix=clr_df,
    target_column="biome",
    model="xgboost",
    cv_folds=5,
    scoring=["accuracy", "f1_macro", "roc_auc"],
)
```

### Data quality checks

```python
from flora.ml.evaluation import check_split_quality, DataQualityReport

report = check_split_quality(train_df, test_df, target_column="biome")
print(report.class_imbalance)
print(report.warnings)
```

### MLflow tracking

```python
import mlflow

with mlflow.start_run():
    clf = MicrobiomeClassifier(model="xgboost", target_column="biome")
    result = clf.fit(train_df, test_df, cv_folds=5)
    mlflow.log_metrics({"accuracy": result.accuracy, "f1_macro": result.f1_macro})
    mlflow.sklearn.log_model(result.model, "model")
```

---

## 8. Visualization

All plots return Plotly `Figure` objects and can be shown interactively or saved as PNG/HTML.

### Taxonomic composition

```python
from flora.viz import plot_taxonomy_barplot

taxon_agg = db.aggregate_by_taxon(level="phylum", group_by="biome")
fig = plot_taxonomy_barplot(taxon_agg, level="phylum", group_by="biome")
fig.show()
fig.write_html("results/taxonomy_barplot.html")
```

### PCoA ordination

```python
from flora.viz import plot_pcoa

fig = plot_pcoa(pcoa_df, color_by="biome", title="Bray-Curtis PCoA")
fig.show()
```

### Alpha diversity

```python
from flora.viz import plot_alpha_diversity

fig = plot_alpha_diversity(diversity_df, metric="shannon", group_by="biome")
fig.show()
```

### Rarefaction curves

```python
from flora.viz import plot_rarefaction_curve

fig = plot_rarefaction_curve(curve_df)
fig.show()
```

### ML diagnostics

```python
from flora.viz import plot_roc_curve, plot_confusion_matrix, plot_feature_importance

fig_roc = plot_roc_curve(result)
fig_cm = plot_confusion_matrix(result)
fig_fi = plot_feature_importance(result, top_n=20)
```

---

## 9. HTML Reports

`FLORAReport` builds a self-contained single-file HTML report. No internet connection needed to open it.

```python
from flora.reports import FLORAReport

report = FLORAReport(title="Amazonian Microbiome Analysis — 2024")

# Metrics card
report.add_metrics("Pipeline Summary", {
    "Samples": 240,
    "ASVs after filtering": 1842,
    "Sampling depth": 10000,
    "Normalization": "CLR",
})

# Section with text
report.add_text("Methods", """
    Reads were denoised with DADA2. Taxonomic classification used the
    SILVA 138 reference database. Features were normalized with CLR
    before ML training.
""")

# Add plots
report.add_plot("Taxonomic Composition", fig_taxonomy)
report.add_plot("Bray-Curtis PCoA", fig_pcoa)
report.add_plot("ROC Curve", fig_roc)

# Add data table
report.add_table("Classification Results", result_df)

# Write file
report.save("results/report.html")
```

---

## 10. Pipeline Orchestration

`FLORAPipeline` combines all modules into a single high-level interface.

```python
from flora.pipelines import FLORAPipeline

pipeline = FLORAPipeline(workdir="results/", config_path="config.yaml")

# Ingest
pipeline.ingest_metadata("data/raw/metadata.tsv")
pipeline.ingest_asv_table("data/raw/asv_table.tsv", wide_format=True)
pipeline.ingest_taxonomy("data/raw/taxonomy.tsv")

# Process
diversity = pipeline.compute_diversity(sampling_depth=10000)
feature_matrix = pipeline.get_feature_matrix(normalize="clr", min_prevalence=0.1)

# Access underlying DB
db = pipeline.db
```

All steps are recorded in the `pipeline_log` table in DuckDB for reproducibility.

---

## 11. CLI Reference

```
flora --help

Commands:
  ui        Start the local web interface
  download  Download public microbiome datasets
  run       Run a pipeline from a YAML config file

flora ui [OPTIONS]
  --host TEXT       Bind host (default: 127.0.0.1)
  --port INTEGER    Bind port (default: 8765)
  --workdir PATH    Working directory

flora download mgnify ACCESSION [OPTIONS]
  --outdir PATH     Output directory
  --max-samples INT Maximum samples to download
  --biome TEXT      Biome filter string

flora download sra RUN_ACCESSIONS... [OPTIONS]
  --outdir PATH     Output directory
  --jobs INTEGER    Parallel download jobs (default: 1)

flora run CONFIG_PATH [OPTIONS]
  --workdir PATH    Override workdir from config
```

---

## 12. Logging and Exceptions

### Logging

```python
from flora.core import get_logger

log = get_logger(__name__)
log.info("Starting pipeline")
log.warning("Low coverage in sample S042")
log.error("File not found: data/raw/asv_table.tsv")
```

Log level is set in config (`logging.level: DEBUG | INFO | WARNING | ERROR`).

### Exception hierarchy

```
FloraError
├── PipelineError     — raised by FLORAPipeline when a step fails
├── ValidationError   — raised by validators when input is malformed
├── DatabaseError     — raised by FloraDB on SQL or connection failures
└── DownloadError     — raised by downloaders on network or API failures
```

All exceptions carry a `message` and optional `context` dict for debugging.

```python
from flora.core.exceptions import ValidationError

try:
    db.ingest_metadata("bad_file.tsv")
except ValidationError as exc:
    print(exc.message)
    print(exc.context)
```
