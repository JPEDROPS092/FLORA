# FLORA: Feature Learning and Omics Research Analytics — A Python Library for End-to-End Microbiome Analysis

---

## Abstract

Microbiome studies generate high-dimensional, compositional count data that require specialized preprocessing before standard machine learning methods can be applied. Existing tools either focus on bioinformatics processing (QIIME 2, DADA2) or statistical analysis (phyloseq, vegan), leaving a gap between raw sequence processing and interpretable predictive models. FLORA (Feature Learning and Omics Research Analytics) is an open-source Python library that bridges this gap by providing a unified, production-ready pipeline from raw 16S rRNA amplicon reads to machine learning predictions and interactive HTML reports. FLORA uses DuckDB as an in-process analytical database to handle large feature matrices without loading them into RAM, Polars for high-performance tabular transformations, and scikit-learn and XGBoost for model training with built-in SHAP explainability. Compositionality-aware normalization via Centered Log-Ratio (CLR) transformation is the default, ensuring statistically valid inputs for ML models. The library provides downloaders for MGnify, NCBI SRA, and the Earth Microbiome Project, integrates directly with the QIIME 2 Python SDK, and generates self-contained HTML reports for sharing results without additional infrastructure. FLORA targets data scientists and microbial ecologists working on microbiome classification, diversity prediction, and exploratory clustering tasks.

**Keywords:** microbiome, 16S rRNA, machine learning, DADA2, QIIME 2, DuckDB, feature engineering, CLR normalization, XGBoost, SHAP

---

## 1. Introduction

High-throughput 16S rRNA amplicon sequencing has become the standard approach for characterizing microbial communities in environmental, clinical, and agricultural contexts (Clarridge, 2004). The decreasing cost of Illumina sequencing has produced large repositories of publicly available microbiome data, including the Earth Microbiome Project (Thompson et al., 2017), MGnify (Richardson et al., 2023), and NCBI SRA (Katz et al., 2022). Extracting biological insight from these datasets requires a multi-step computational workflow: sequence quality control, denoising into Amplicon Sequence Variants (ASVs), taxonomic classification, diversity analysis, and finally predictive modeling or hypothesis testing.

Current software ecosystems cover parts of this workflow well. QIIME 2 (Bolyen et al., 2019) provides a comprehensive bioinformatics platform for amplicon processing. DADA2 (Callahan et al., 2016) produces high-resolution ASVs that outperform OTU-based approaches. The R packages phyloseq (McMurdie & Holmes, 2013) and vegan provide rich ecological statistics. However, connecting these tools to modern machine learning workflows in Python requires substantial custom code, and the resulting pipelines are often tied to specific datasets and difficult to reuse.

A fundamental challenge in microbiome machine learning is the compositional nature of the data. Amplicon sequencing yields relative abundances rather than absolute counts, and the observed values are constrained to sum to a constant (Aitchison, 1982). Standard ML methods applied directly to raw counts or total-sum-scaled data can yield spurious correlations induced by the unit-sum constraint (Gloor et al., 2017). The Centered Log-Ratio (CLR) transformation maps compositions to an unconstrained Euclidean space where standard correlation measures and distance metrics are valid.

A second challenge is scalability. Feature matrices for microbiome studies can contain thousands of ASVs across hundreds of samples, and downstream analyses involving cross-validation, hyperparameter tuning, and SHAP explanations multiply the data access patterns. Loading large matrices fully into RAM is wasteful and creates reproducibility issues when data exceeds available memory.

FLORA addresses both challenges. It wraps the QIIME 2 / DADA2 workflow in a Python API, stores all intermediate results in a DuckDB database backed by Parquet files, applies CLR normalization by default, and provides high-level interfaces to scikit-learn, XGBoost, and SHAP. The design targets reproducible, memory-efficient microbiome analysis in Python without requiring expertise in bioinformatics infrastructure.

---

## 2. Design Principles

FLORA was designed around four principles:

**Compositionality by default.** CLR normalization is applied automatically when producing feature matrices for ML. Users must explicitly request TSS or rarefaction to override this default. This prevents a common source of methodological error in microbiome studies (Gloor et al., 2017).

**Memory efficiency via DuckDB.** All data (metadata, ASV counts, taxonomy, diversity metrics) is stored in a DuckDB file backed by Parquet. Feature matrices are materialized from SQL queries only when needed, not cached in RAM. This allows FLORA to operate on datasets that exceed available memory with zero special configuration.

**No leakage between pipeline stages.** Each step writes to the database and reads from it. There are no intermediate files outside DuckDB except the raw Parquet exports from QIIME 2 artifacts. This eliminates a common source of reproducibility failures in bioinformatics pipelines.

**Interoperability with standard ML libraries.** FLORA produces Polars DataFrames and NumPy arrays that plug directly into scikit-learn, XGBoost, Optuna, MLflow, and SHAP without wrapper objects or custom data formats.

---

## 3. Architecture

FLORA follows a layered pipeline architecture:

```
[QIIME2 / DADA2 — sequence denoising, taxonomy, phylogeny, diversity]
        |
[Export: BIOM / TSV → Parquet via PyArrow]
        |
[DuckDB + Parquet — central analytical store]
        |
[Feature Engineering: SQL aggregations + CLR/TSS/rarefaction (Python/Polars)]
        |
[ML Pipeline: scikit-learn / XGBoost / SHAP / Optuna / MLflow]
        |
[Visualization: Plotly interactive plots]
        |
[HTML Report: self-contained Jinja2 + embedded Plotly]
```

### 3.1 Data Acquisition

Three downloaders are provided:

- `MGnifyDownloader`: queries the EMBL-EBI MGnify REST API (https://www.ebi.ac.uk/metagenomics/api/v1/), filters by biome, and downloads pre-computed taxonomic analyses.
- `NCBISRADownloader`: wraps `prefetch` and `fasterq-dump` from NCBI sra-tools for parallel raw FASTQ download.
- `EarthMicrobiomeDownloader`: downloads per-study feature tables and metadata from the EMP portal.

Input validators check FASTQ quality, QIIME 2 manifest format, and metadata schema before the pipeline starts.

### 3.2 DuckDB Analytics Core

`FloraDB` is a singleton connection wrapper around DuckDB. The schema uses a normalized star model:

- `samples`: dimension table of sample metadata.
- `asv`: fact table in long format (sample_id, feature_id, abundance).
- `taxonomy`: lineage per feature (kingdom through species).
- `diversity_alpha`: per-sample alpha diversity metrics.
- `diversity_beta`: pairwise distance matrices.
- `dim_reduction`: PCoA and UMAP coordinates.
- `pipeline_log`: audit trail with timestamps and checksums.

Three high-level helpers expose common access patterns:

- `pivot_asv(normalize)`: long-to-wide pivot with optional normalization, executed as a DuckDB SQL PIVOT statement.
- `aggregate_by_taxon(level, group_by)`: SQL aggregation with JOIN to the taxonomy table.
- `slice(train_filter, test_filter, features, target_column)`: train/test split via WHERE clauses.

Direct SQL access is available for ad-hoc queries, returning Polars DataFrames.

### 3.3 Feature Engineering

The `feature_engineering` module provides:

- **CLR transform** (`clr_transform`): adds a configurable pseudo-count, computes per-sample geometric means, and applies the log-ratio transform. Vectorized with NumPy.
- **TSS transform** (`tss_transform`): row-wise division by sample total.
- **Rarefaction** (`rarefy`): random subsampling to a fixed depth using NumPy multinomial sampling.
- **Rarefaction curves** (`rarefaction_curve`): bootstrap resampling at multiple depths with 95% CI.
- **Prevalence filter** (`filter_by_prevalence`): removes features below a prevalence threshold.
- **Importance-based selection** (`select_by_importance`): trains a fast Random Forest and keeps the top-N features.
- **PCoA** (`compute_pcoa`): scikit-bio eigendecomposition on distance matrices.
- **UMAP** (`compute_umap`): wraps `umap-learn` with configurable neighbors and minimum distance.

### 3.4 Machine Learning

Three estimator classes provide a consistent interface:

- `MicrobiomeClassifier`: stratified k-fold cross-validation, accuracy, F1-macro, ROC-AUC, and classification report.
- `MicrobiomeRegressor`: k-fold cross-validation, R², MAE, RMSE.
- `MicrobiomeClusterer`: k-means or HDBSCAN with silhouette score.

All estimators accept a `model` argument (`"random_forest"`, `"svm"`, `"xgboost"`) and optional `model_params`. Results carry the fitted model, feature importances, and evaluation metrics.

`SHAPAnalyzer` wraps the `shap` library and returns ranked feature contributions and local sample explanations as Plotly figures.

`HyperparameterTuner` uses Optuna with TPE sampling. The search space is defined per model type and can be extended via a configuration dictionary.

MLflow integration is opt-in: pass `mlflow_run=True` to any estimator to log parameters, metrics, and the serialized model automatically.

### 3.5 Visualization

All plots use Plotly and return `Figure` objects:

- `plot_taxonomy_barplot`: stacked bar chart of taxonomic composition grouped by metadata variable.
- `plot_pcoa`: scatter plot of PCoA axes with metadata color-coding and variance-explained labels.
- `plot_alpha_diversity`: box plots or violin plots of alpha diversity distributions by group.
- `plot_rarefaction_curve`: multi-sample curves with shaded 95% CI.
- `plot_roc_curve`, `plot_confusion_matrix`, `plot_feature_importance`: standard ML diagnostics.

### 3.6 HTML Report

`FLORAReport` generates self-contained HTML files using Jinja2 templates with embedded Plotly figures as JSON. Reports contain:

- Summary metrics cards
- Free-text sections
- Interactive Plotly plots (fully functional without a server)
- Sortable and searchable data tables

---

## 4. Implementation

FLORA is implemented in Python 3.11+. The package is structured as `src/flora/` with domain-specific subpackages for `db`, `io`, `feature_engineering`, `ml`, `viz`, `reports`, `pipelines`, `config`, `core`, and `ui`.

Core dependencies:
- DuckDB 0.10+ — in-process analytical SQL engine
- Polars 0.20+ — high-performance DataFrame library
- PyArrow 14+ — columnar format and Parquet I/O
- scikit-learn 1.4+ — classical ML algorithms and preprocessing
- XGBoost 2.0+ — gradient boosted trees
- SHAP 0.44+ — model interpretability
- Optuna 3.5+ — hyperparameter optimization
- Plotly 5.18+ — interactive visualization
- Pydantic 2.5+ — configuration validation
- MLflow 2.10+ — experiment tracking

The test suite uses pytest with DuckDB in-memory databases. No external files, QIIME 2 installations, or network access are required to run the tests. A minimum coverage threshold of 70% is enforced on every CI run.

The CLI entry point (`flora`) is registered via `pyproject.toml` and provides `ui`, `download`, and `run` subcommands.

---

## 5. Usage Example

The following example demonstrates a complete workflow on the MGYS00005116 Amazonian forest dataset. The pipeline downloads data, runs denoising and taxonomy through QIIME 2, stores results in DuckDB, trains an XGBoost classifier with CLR normalization, and generates an HTML report.

```python
from flora.io import MGnifyDownloader
from flora.pipelines import FLORAPipeline
from flora.ml import MicrobiomeClassifier, SHAPAnalyzer
from flora.viz import plot_pcoa, plot_taxonomy_barplot
from flora.reports import FLORAReport

# 1. Download
dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")
dl.fetch("MGYS00005116", output_dir="data/raw", max_samples=80)

# 2. Build pipeline
pipeline = FLORAPipeline(workdir="results/")
pipeline.ingest_metadata("data/raw/metadata.tsv")
pipeline.ingest_asv_table("data/raw/asv_table.tsv", wide_format=True)
pipeline.ingest_taxonomy("data/raw/taxonomy.tsv")
pipeline.compute_diversity(sampling_depth=10000)

# 3. Feature matrix
db = pipeline.db
train_df, test_df = db.slice(
    train_filter="biome = 'Amazon'",
    test_filter="biome = 'Cerrado'",
    features="clr",
    target_column="biome",
)

# 4. Classification
clf = MicrobiomeClassifier(model="xgboost", target_column="biome")
result = clf.fit(train_df, test_df, cv_folds=5)

# 5. Explainability
shap = SHAPAnalyzer(model=result.model, feature_names=result.feature_names)
shap_result = shap.explain(test_df)

# 6. Visualize
taxon_agg = db.aggregate_by_taxon(level="phylum", group_by="biome")
pcoa_df = db.query("SELECT * FROM dim_reduction WHERE method = 'pcoa'").to_polars()
fig_taxa = plot_taxonomy_barplot(taxon_agg, level="phylum", group_by="biome")
fig_pcoa = plot_pcoa(pcoa_df, color_by="biome")

# 7. Report
report = FLORAReport(title="Amazonian Microbiome — MGYS00005116")
report.add_metrics("Results", {
    "Accuracy": f"{result.accuracy:.4f}",
    "F1-macro": f"{result.f1_macro:.4f}",
    "ROC-AUC": f"{result.roc_auc:.4f}",
})
report.add_plot("Taxonomic Composition", fig_taxa)
report.add_plot("PCoA — Bray-Curtis", fig_pcoa)
report.add_plot("SHAP Feature Importance", shap.summary_plot(shap_result))
report.save("results/report.html")
```

---

## 6. Comparison with Related Tools

| Feature | FLORA | QIIME 2 | phyloseq | MicrobiomeAnalyst |
|---|---|---|---|---|
| Language | Python | Python/R | R | Web |
| ASV denoising (DADA2) | via SDK | native | post-import | post-import |
| Analytical DB (DuckDB) | yes | no | no | no |
| CLR normalization | default | available | available | available |
| Random Forest / XGBoost | native | plugin | R packages | limited |
| SHAP explainability | native | no | no | no |
| Hyperparameter tuning (Optuna) | native | no | no | no |
| Public dataset downloaders | 3 sources | no | no | limited |
| HTML report export | native | native | rmarkdown | native |
| Python API | yes | yes | R only | REST |
| Memory-efficient (out-of-core) | DuckDB | limited | no | server-side |

---

## 7. Conclusion

FLORA provides a unified Python library for end-to-end 16S rRNA amplicon microbiome analysis with a focus on machine learning readiness, statistical correctness, and memory efficiency. By centralizing data in DuckDB and applying CLR normalization by default, FLORA reduces two common sources of error in microbiome ML workflows. The library integrates directly with the scientific Python ecosystem and the QIIME 2 SDK, and produces self-contained HTML reports that require no additional infrastructure to view.

---

## References

Aitchison, J. (1982). The statistical analysis of compositional data. *Journal of the Royal Statistical Society: Series B*, 44(2), 139-160. https://doi.org/10.1111/j.2517-6161.1982.tb01195.x

Akiba, T., et al. (2019). Optuna: A Next-generation Hyperparameter Optimization Framework. *Proceedings of KDD 2019*, 2623-2631. https://doi.org/10.1145/3292500.3330701

Bokulich, N. A., et al. (2018). Optimizing taxonomic classification of marker-gene amplicon sequences with QIIME 2's q2-feature-classifier. *Microbiome*, 6, 90. https://doi.org/10.1186/s40168-018-0470-z

Bolyen, E., et al. (2019). Reproducible, interactive, scalable and extensible microbiome data science using QIIME 2. *Nature Biotechnology*, 37, 852-857. https://doi.org/10.1038/s41587-019-0209-9

Breiman, L. (2001). Random forests. *Machine Learning*, 45, 5-32. https://doi.org/10.1023/A:1010933404324

Callahan, B. J., et al. (2016). DADA2: High-resolution sample inference from Illumina amplicon data. *Nature Methods*, 13, 581-583. https://doi.org/10.1038/nmeth.3869

Campello, R. J. G. B., et al. (2013). Density-Based Clustering Based on Hierarchical Density Estimates. *PAKDD 2013*, 160-172. https://doi.org/10.1007/978-3-642-37456-2_14

Chao, A. (1984). Nonparametric estimation of the number of classes in a population. *Scandinavian Journal of Statistics*, 11(4), 265-270.

Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *KDD 2016*, 785-794. https://doi.org/10.1145/2939672.2939785

Clarridge, J. E. (2004). Impact of 16S rRNA gene sequence analysis for identification of bacteria on clinical microbiology and infectious diseases. *Clinical Microbiology Reviews*, 17(4), 840-862. https://doi.org/10.1128/CMR.17.4.840-862.2004

Cortes, C., & Vapnik, V. (1995). Support-vector networks. *Machine Learning*, 20, 273-297. https://doi.org/10.1007/BF00994018

Faith, D. P. (1992). Conservation evaluation and phylogenetic diversity. *Biological Conservation*, 61(1), 1-10. https://doi.org/10.1016/0006-3207(92)91201-3

Gloor, G. B., et al. (2017). Microbiome Datasets Are Compositional: And This Is Not Optional. *Frontiers in Microbiology*, 8, 2224. https://doi.org/10.3389/fmicb.2017.02224

Katoh, K., & Standley, D. M. (2013). MAFFT multiple sequence alignment software version 7: improvements in performance and usability. *Molecular Biology and Evolution*, 30(4), 772-780. https://doi.org/10.1093/molbev/mst010

Katz, K., et al. (2022). The Sequence Read Archive: a decade more of explosive growth and new challenges. *Nucleic Acids Research*, 50(D1), D387-D390. https://doi.org/10.1093/nar/gkab1053

Lozupone, C., & Knight, R. (2005). UniFrac: a new phylogenetic method for comparing microbial communities. *Applied and Environmental Microbiology*, 71(12), 8228-8235. https://doi.org/10.1128/AEM.71.12.8228-8235.2005

Lundberg, S. M., & Lee, S.-I. (2017). A Unified Approach to Interpreting Model Predictions. *NeurIPS 2017*. https://proceedings.neurips.cc/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html

McInnes, L., et al. (2018). UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction. *arXiv*, 1802.03426. https://arxiv.org/abs/1802.03426

McMurdie, P. J., & Holmes, S. (2013). phyloseq: An R Package for Reproducible Interactive Analysis and Graphics of Microbiome Census Data. *PLOS ONE*, 8(4), e61217. https://doi.org/10.1371/journal.pone.0061217

McDonald, D., et al. (2012). The Biological Observation Matrix (BIOM) format. *GigaScience*, 1(1), 7. https://doi.org/10.1186/2047-217X-1-7

McDonald, D., et al. (2023). Greengenes2 unifies microbial data in a single reference tree. *Nature Biotechnology*, 41, 1330-1332. https://doi.org/10.1038/s41587-023-01845-1

Price, M. N., et al. (2010). FastTree 2 — Approximately Maximum-Likelihood Trees for Large Alignments. *PLOS ONE*, 5(3), e9490. https://doi.org/10.1371/journal.pone.0009490

Quast, C., et al. (2013). The SILVA ribosomal RNA gene database project: improved data processing and web-based tools. *Nucleic Acids Research*, 41(D1), D590-D596. https://doi.org/10.1093/nar/gks1219

Raasveldt, M., & Muehleisen, H. (2019). DuckDB: an embeddable analytical database. *SIGMOD 2019*, 1981-1984. https://doi.org/10.1145/3299869.3320212

Richardson, L., et al. (2023). MGnify: the microbiome sequence data analysis resource in 2023. *Nucleic Acids Research*, 51(D1), D753-D759. https://doi.org/10.1093/nar/gkac1080

Rousseeuw, P. J. (1987). Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53-65. https://doi.org/10.1016/0377-0427(87)90125-7

Shannon, C. E. (1948). A mathematical theory of communication. *Bell System Technical Journal*, 27(3), 379-423.

Simpson, E. H. (1949). Measurement of diversity. *Nature*, 163, 688. https://doi.org/10.1038/163688a0

Thompson, L. R., et al. (2017). A communal catalogue reveals Earth's multiscale microbial diversity. *Nature*, 551, 457-463. https://doi.org/10.1038/nature24621

Weiss, S., et al. (2017). Normalization and microbial differential abundance strategies depend upon data characteristics. *Microbiome*, 5, 27. https://doi.org/10.1186/s40168-017-0237-y
