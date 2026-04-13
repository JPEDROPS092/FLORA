"""FLORA basic pipeline — Earth Microbiome Project data.

Runs the complete pipeline using EMP Release 1 data from data/raw/emp/.

Usage:
    python examples/basic_pipeline.py

Data must be present at data/raw/emp/ (run `flora download emp` first).
Output: results/flora_example_report.html
"""

from pathlib import Path
import sys

DATA_DIR  = Path("data/raw/emp")
RESULTS   = Path("results")
METADATA  = DATA_DIR / "metadata.tsv"
ASV_TABLE = DATA_DIR / "asv_table.tsv"
TAXONOMY  = DATA_DIR / "taxonomy.tsv"

for f in (METADATA, ASV_TABLE, TAXONOMY):
    if not f.exists():
        print(f"Missing: {f}")
        print("Run: flora download emp --outdir data/raw/emp --biome forest --max-samples 200")
        sys.exit(1)

import polars as pl
from sklearn.model_selection import train_test_split

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.db.ingestion import ingest_metadata, ingest_tsv_asv, ingest_taxonomy
from flora.diversity.alpha import compute_alpha_diversity
from flora.feature_engineering.normalization import clr_transform
from flora.feature_engineering.reduction import compute_pcoa
from flora.feature_engineering.selection import filter_by_prevalence
from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.clustering.clusterer import MicrobiomeClusterer
from flora.ml.evaluation.bias import check_split_quality
from flora.reports.html_report import FLORAReport
from flora.viz.diversity_plots import plot_pcoa, plot_alpha_diversity
from flora.viz.taxonomy_plots import plot_taxonomy_barplot

TARGET_COL   = "empo_3"
KEEP_CLASSES = {"Plant surface", "Soil (non-saline)", "Animal proximal gut"}
RANDOM_STATE = 42


def main():
    print("FLORA — EMP Pipeline")
    print("=" * 40)

    RESULTS.mkdir(parents=True, exist_ok=True)

    db = FloraDB.connect(":memory:")
    initialize_schema(db)

    n_samples = ingest_metadata(db, METADATA, parquet_dir=RESULTS / "parquet")
    n_obs     = ingest_tsv_asv(db, ASV_TABLE, wide_format=True, parquet_dir=RESULTS / "parquet")
    n_tax     = ingest_taxonomy(db, TAXONOMY, parquet_dir=RESULTS / "parquet")
    db.create_views()
    print(f"Loaded: {n_samples} samples, {n_obs} ASV observations, {n_tax} taxonomy rows")

    wide    = db.pivot_asv(normalize=None)
    clr     = clr_transform(wide)
    clr     = filter_by_prevalence(clr, min_prevalence=0.05)
    print(f"Feature matrix: {len(clr)} samples x {len(clr.columns) - 1} features")

    alpha = compute_alpha_diversity(wide, metrics=["shannon", "observed_features", "chao1"])

    meta = db.query(f"""
        SELECT s.sample_id, m.value AS {TARGET_COL}
        FROM samples s
        LEFT JOIN sample_metadata m
               ON s.sample_id = m.sample_id AND m.key = '{TARGET_COL}'
    """).to_polars()
    meta_sub = meta.filter(pl.col(TARGET_COL).is_in(list(KEEP_CLASSES)))

    labeled = clr.join(meta_sub.select(["sample_id", TARGET_COL]), on="sample_id", how="inner")
    df_pd   = labeled.to_pandas()
    train_pd, test_pd = train_test_split(
        df_pd, test_size=0.25, stratify=df_pd[TARGET_COL], random_state=RANDOM_STATE
    )
    train_df = pl.from_pandas(train_pd)
    test_df  = pl.from_pandas(test_pd)

    quality = check_split_quality(train_df, test_df, target_column=TARGET_COL)
    print(f"Split quality: {'OK' if quality.valid else 'ISSUES FOUND'}")

    clf = MicrobiomeClassifier(
        model="random_forest",
        target_column=TARGET_COL,
        random_state=RANDOM_STATE,
        mlflow_tracking_uri=None,
    )
    result = clf.fit(train_df, test_df, cv_folds=3)
    print(f"Classification: accuracy={result.accuracy:.4f}, f1_macro={result.f1_macro:.4f}")

    pcoa_long = compute_pcoa(clr, metric="braycurtis", n_components=2)
    pcoa_meta = pcoa_long.join(meta_sub.select(["sample_id", TARGET_COL]), on="sample_id", how="left")

    clusterer = MicrobiomeClusterer(method="kmeans", n_clusters=3, random_state=RANDOM_STATE)
    pcoa_wide = pcoa_long.pivot(
        index="sample_id", on="component", values="value", aggregate_function="first"
    ).rename({"1": "PC1", "2": "PC2"})
    clusters = clusterer.fit(pcoa_wide)
    print(f"Clustering: {clusters.n_clusters} clusters, silhouette={clusters.silhouette:.4f}")

    taxon_agg = db.aggregate_by_taxon(level="phylum", group_by=TARGET_COL)

    report = FLORAReport(title="FLORA EMP Pipeline Report")
    report.add_metrics("Summary", {
        "Samples":          n_samples,
        "ASVs (filtered)":  len(clr.columns) - 1,
        "Train":            len(train_df),
        "Test":             len(test_df),
        "Accuracy":         result.accuracy,
        "F1-macro":         result.f1_macro,
        "Clusters":         clusters.n_clusters,
        "Silhouette":       clusters.silhouette,
    })
    report.add_table("Alpha Diversity", alpha.join(
        meta_sub.select(["sample_id", TARGET_COL]), on="sample_id", how="left"
    ))
    report.add_plot("Taxonomic Composition", plot_taxonomy_barplot(taxon_agg, level="phylum", group_by=TARGET_COL))
    report.add_plot("PCoA — Bray-Curtis", plot_pcoa(pcoa_meta, metadata_df=pcoa_meta, color_by=TARGET_COL))
    report.add_plot("Shannon Diversity", plot_alpha_diversity(
        alpha.join(meta_sub.select(["sample_id", TARGET_COL]), on="sample_id", how="left"),
        metric="shannon", group_by=TARGET_COL,
    ))
    if result.feature_importances is not None:
        from flora.viz.ml_plots import plot_feature_importance
        report.add_plot("Feature Importance", plot_feature_importance(result, top_n=15))
    report.add_text("Classification Report", result.classification_report_str)

    out = report.save("results/flora_example_report.html")
    print(f"Report saved: {out}")
    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
