# Quick Start

## Earth Microbiome Project data

Local files at `data/raw/emp/`:

```
data/raw/emp/
├── asv_table.tsv        # 96 MB — deblur 150bp OTU table (wide: samples x ASVs)
├── taxonomy.tsv         # 41 MB — Greengenes lineage per feature
├── metadata.tsv         # 77 KB — 89 samples, columns include empo_3, env_biome, ph, latitude
├── emp_deblur_150bp.release1.biom   # source BIOM — keep for re-processing
└── emp_metadata_raw.tsv             # raw QIIME-format metadata
```

Source: Zenodo https://zenodo.org/record/890000 — Thompson et al. (2017), *Nature* 551.

---

## Full ML analysis (recommended starting point)

Runs classification, SHAP, PCoA, alpha diversity, taxonomy plots and generates
a self-contained HTML report. Classification target: `empo_3` (environmental
material type — Plant surface / Soil / Animal proximal gut).

```bash
python examples/emp_analysis.py
# → results/emp_report.html
```

---

## Basic pipeline

```bash
python examples/basic_pipeline.py
# → results/flora_example_report.html
```

---

## CLI pipeline

```bash
flora run config.yaml \
  --metadata  data/raw/emp/metadata.tsv \
  --asv-table data/raw/emp/asv_table.tsv \
  --taxonomy  data/raw/emp/taxonomy.tsv
```

---

## Web interface

```bash
flora ui --host 127.0.0.1 --port 8765 --workdir results/ --log-level INFO
# → http://127.0.0.1:8765
# Logs visible in terminal. /api/logs returns last 100 lines.
```

---

## Python API

```python
import polars as pl
from sklearn.model_selection import train_test_split
from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.db.ingestion import ingest_metadata, ingest_tsv_asv, ingest_taxonomy
from flora.feature_engineering.normalization import clr_transform
from flora.feature_engineering.selection import filter_by_prevalence
from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.reports.html_report import FLORAReport

db = FloraDB.connect("results/flora.duckdb")
initialize_schema(db)
ingest_metadata(db, "data/raw/emp/metadata.tsv", parquet_dir="results/parquet")
ingest_tsv_asv(db, "data/raw/emp/asv_table.tsv", wide_format=True, parquet_dir="results/parquet")
ingest_taxonomy(db, "data/raw/emp/taxonomy.tsv", parquet_dir="results/parquet")
db.create_views()

wide    = db.pivot_asv(normalize=None)
clr     = clr_transform(wide)
clr     = filter_by_prevalence(clr, min_prevalence=0.05)

meta    = db.query("SELECT sample_id, empo_3 FROM samples").to_polars()
labeled = clr.join(meta, on="sample_id", how="inner")
df_pd   = labeled.to_pandas()
train_pd, test_pd = train_test_split(df_pd, test_size=0.25,
                                     stratify=df_pd["empo_3"], random_state=42)

clf    = MicrobiomeClassifier(model="xgboost", target_column="empo_3", mlflow_tracking_uri=None)
result = clf.fit(pl.from_pandas(train_pd), pl.from_pandas(test_pd), cv_folds=3)
print(f"Accuracy: {result.accuracy:.4f}  F1-macro: {result.f1_macro:.4f}")

report = FLORAReport(title="EMP Analysis")
report.add_metrics("Results", {"Accuracy": result.accuracy, "F1-macro": result.f1_macro})
report.save("results/report.html")
```

---

## Download EMP data again

```bash
flora download emp --outdir data/raw/emp --biome forest --max-samples 200
# Files already present are skipped (skip_existing=True).
```

---

## Other sources

```bash
# MGnify pre-computed analyses
flora download mgnify MGYS00005116 --outdir data/raw --analyses --max-samples 20
flora run config.yaml

# NCBI SRA (requires: conda install -c bioconda sra-tools)
flora download sra SRR12345678 SRR12345679 --outdir data/raw --jobs 4
```

### Process a specific MGnify study

If you already have a study accession such as `MGYS00005292`, you can convert it directly into FLORA-ready files and print the next pipeline command:

```bash
python examples/process_mgnify_study.py MGYS00005292 --max-analyses 20 --print-run-command
```

This creates:

- `data/raw/MGYS00005292/metadata.tsv`
- `data/raw/MGYS00005292/asv_table.tsv`
- `data/raw/MGYS00005292/taxonomy.tsv`

Then run:

```bash
flora run config.yaml \
  --workdir results/mgnify_MGYS00005292 \
  --metadata data/raw/MGYS00005292/metadata.tsv \
  --asv-table data/raw/MGYS00005292/asv_table.tsv \
  --taxonomy data/raw/MGYS00005292/taxonomy.tsv
```

---

## Expected input formats

### metadata.tsv

Tab-separated file with a header row. The first column is the sample identifier.

```
sample_id   biome       location    ph
S001        Amazon      Manaus      5.2
S002        Cerrado     Brasilia    6.1
```

### asv_table.tsv (wide format)

Rows are samples, columns are ASV feature identifiers.

```
sample_id   ASV001  ASV002  ASV003
S001        1200    450     0
S002        0       830     310
```

### taxonomy.tsv

```
feature_id  kingdom  phylum          class            order             family             genus
ASV001      Bacteria Proteobacteria  Gammaproteobacteria Pseudomonadales  Pseudomonadaceae   Pseudomonas
```

---

## Output files

After running the pipeline, the `workdir` contains:

```
results/
├── flora.duckdb          # persistent analytical database
├── report.html           # self-contained HTML report (open in any browser)
└── logs/                 # pipeline audit trail
```
