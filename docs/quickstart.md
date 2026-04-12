# Quick Start

## Run the built-in example

No external data required:

```bash
python examples/basic_pipeline.py
```

This generates synthetic microbiome data, runs the complete pipeline in-memory using DuckDB, trains a classifier, and writes an HTML report to `results/report.html`.

---

## Minimal working example

```python
from flora.pipelines import FLORAPipeline
from flora.ml import MicrobiomeClassifier
from flora.reports import FLORAReport

# Initialize pipeline with file-backed DuckDB
pipeline = FLORAPipeline(workdir="results/")

# Ingest pre-processed data
pipeline.ingest_metadata("data/raw/metadata.tsv")
pipeline.ingest_asv_table("data/raw/asv_table.tsv", wide_format=True)
pipeline.ingest_taxonomy("data/raw/taxonomy.tsv")

# Compute alpha and beta diversity
diversity = pipeline.compute_diversity(sampling_depth=10000)

# Build CLR-normalized feature matrix
feature_matrix = pipeline.get_feature_matrix(normalize="clr", min_prevalence=0.1)

# Split by biome label and train classifier
db = pipeline.db
train_df, test_df = db.slice(
    train_filter="biome = 'Amazon'",
    test_filter="biome = 'Cerrado'",
    features="clr",
    target_column="biome",
)

clf = MicrobiomeClassifier(model="random_forest", target_column="biome")
result = clf.fit(train_df, test_df, cv_folds=5)
print(f"Accuracy: {result.accuracy:.4f}  F1-macro: {result.f1_macro:.4f}")

# Generate HTML report
report = FLORAReport(title="Microbiome Analysis")
report.add_metrics("Results", {
    "Samples": len(feature_matrix),
    "ASVs": len(feature_matrix.columns) - 1,
    "Accuracy": f"{result.accuracy:.4f}",
})
report.save("results/report.html")
```

---

## Download a public dataset first

```python
from flora.io import MGnifyDownloader

dl = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")
manifest = dl.fetch("MGYS00005116", output_dir="data/raw", max_samples=80)
print(manifest.head())
```

Then use the downloaded files as input to `FLORAPipeline`.

---

## CLI usage

```bash
# Start local web interface
flora ui --host 127.0.0.1 --port 8765 --workdir results/

# Download from MGnify
flora download mgnify MGYS00005116 --outdir data/raw --max-samples 80

# Download from NCBI SRA
flora download sra SRR12345678 SRR12345679 --outdir data/raw --jobs 4

# Run a pipeline from a YAML config
flora run config.yaml --workdir results/
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
