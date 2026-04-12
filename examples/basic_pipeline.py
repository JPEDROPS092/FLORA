"""Basic FLORA pipeline example with synthetic data.

Demonstrates the complete workflow from data ingestion to ML results
without external dependencies. Runs fully with in-memory DuckDB.

Usage:
    python examples/basic_pipeline.py
"""

import numpy as np
import polars as pl

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.diversity.alpha import compute_alpha_diversity
from flora.diversity.beta import compute_beta_diversity
from flora.feature_engineering.normalization import clr_transform
from flora.feature_engineering.reduction import compute_pcoa
from flora.feature_engineering.selection import filter_by_prevalence
from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.clustering.clusterer import MicrobiomeClusterer
from flora.ml.evaluation.bias import check_split_quality
from flora.reports.html_report import FLORAReport
from flora.viz.diversity_plots import plot_pcoa, plot_alpha_diversity
from flora.viz.taxonomy_plots import plot_taxonomy_barplot


def generate_synthetic_data(n_samples=40, n_features=80, seed=42):
    rng = np.random.default_rng(seed)
    counts = rng.negative_binomial(n=5, p=0.3, size=(n_samples, n_features)).astype(float)
    sids = [f"S{i:03d}" for i in range(n_samples)]
    fids = [f"ASV_{j:04d}" for j in range(n_features)]
    biomes = ["Amazon", "Cerrado", "Atlantic_Forest", "Pantanal"] * (n_samples // 4)

    metadata = pl.DataFrame({
        "sample_id": sids,
        "biome": biomes,
        "location": ["Brazil"] * n_samples,
        "latitude": [-3.0 + i * 0.15 for i in range(n_samples)],
        "longitude": [-60.0 + i * 0.15 for i in range(n_samples)],
        "sequencing_depth": [10000 + i * 500 for i in range(n_samples)],
    })

    phyla = ["Proteobacteria", "Firmicutes", "Bacteroidetes", "Actinobacteria", "Chloroflexi"]
    taxonomy = pl.DataFrame({
        "feature_id": fids,
        "kingdom": ["Bacteria"] * n_features,
        "phylum": [phyla[j % len(phyla)] for j in range(n_features)],
        "class": [f"Class_{j % 6}" for j in range(n_features)],
        "order": [None] * n_features,
        "family": [f"Family_{j % 8}" for j in range(n_features)],
        "genus": [f"Genus_{j % 15}" for j in range(n_features)],
        "species": [None] * n_features,
        "confidence": [0.85 + (j % 3) * 0.05 for j in range(n_features)],
    })

    data = {"sample_id": sids}
    data.update({f: counts[:, i].tolist() for i, f in enumerate(fids)})
    wide = pl.DataFrame(data)
    long = wide.unpivot(
        index="sample_id", on=fids, variable_name="feature_id", value_name="abundance"
    ).filter(pl.col("abundance") > 0)

    return metadata, taxonomy, wide, long


def main():
    print("FLORA — Synthetic Pipeline Example")
    print("=" * 40)

    metadata, taxonomy, wide, long = generate_synthetic_data()

    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    db.load_dataframe("samples", metadata)
    db.load_dataframe("asv", long)
    db.load_dataframe("taxonomy", taxonomy)
    db.create_views()
    print(f"Loaded: {len(metadata)} samples, {len(long)} ASV observations")

    feature_matrix = db.pivot_asv()
    print(f"Feature matrix: {feature_matrix.shape}")

    alpha = compute_alpha_diversity(feature_matrix, metrics=["shannon", "observed_features", "chao1"])
    print(f"Alpha diversity (first 5 rows):")
    print(alpha.head(5))

    beta = compute_beta_diversity(feature_matrix.head(10), metric="bray_curtis")
    print(f"Beta diversity: {len(beta)} pairwise distances")

    clr_df = clr_transform(feature_matrix)
    filtered = filter_by_prevalence(clr_df, min_prevalence=0.2)
    print(f"Features after prevalence filter: {len(filtered.columns) - 1}")

    labeled = filtered.join(metadata.select(["sample_id", "biome"]), on="sample_id")
    n = len(labeled)
    train = labeled.head(int(n * 0.75))
    test = labeled.tail(n - int(n * 0.75))

    quality = check_split_quality(train, test, target_column="biome")
    print(f"Split quality: {'OK' if quality.valid else 'ISSUES FOUND'}")
    for w in quality.warnings:
        print(f"  WARNING: {w}")

    clf = MicrobiomeClassifier(
        model="random_forest",
        target_column="biome",
        random_state=42,
        mlflow_tracking_uri=None,
    )
    result = clf.fit(train, test, cv_folds=3)
    print(f"Classification: accuracy={result.accuracy:.4f}, f1_macro={result.f1_macro:.4f}")

    pcoa_long = compute_pcoa(clr_df, metric="braycurtis", n_components=2)
    pcoa_wide = pcoa_long.pivot(
        index="sample_id", on="component", values="value", aggregate_function="first"
    ).rename({"1": "PC1", "2": "PC2"})

    clusterer = MicrobiomeClusterer(method="kmeans", n_clusters=4, random_state=42)
    clusters = clusterer.fit(pcoa_wide)
    print(f"Clustering: {clusters.n_clusters} clusters, silhouette={clusters.silhouette:.4f}")

    taxon_agg = db.aggregate_by_taxon(level="phylum", group_by="biome")

    report = FLORAReport(title="FLORA Synthetic Pipeline Report")
    report.add_metrics("Pipeline Summary", {
        "Samples": len(metadata),
        "ASVs (filtered)": len(filtered.columns) - 1,
        "Train samples": len(train),
        "Test samples": len(test),
        "Accuracy": result.accuracy,
        "F1-macro": result.f1_macro,
        "Clusters (k=4)": clusters.n_clusters,
        "Silhouette": clusters.silhouette,
    })
    report.add_table("Alpha Diversity", alpha)

    if result.feature_importances is not None:
        report.add_table("Top Feature Importances", result.feature_importances.head(15))

    taxon_fig = plot_taxonomy_barplot(taxon_agg, level="phylum", group_by="biome")
    report.add_plot("Taxonomic Composition by Biome", taxon_fig)

    pcoa_meta_joined = pcoa_long.join(metadata.select(["sample_id", "biome"]), on="sample_id")

    alpha_fig = plot_alpha_diversity(
        alpha.join(metadata.select(["sample_id", "biome"]), on="sample_id"),
        metric="shannon",
        group_by="biome",
    )
    report.add_plot("Alpha Diversity by Biome", alpha_fig)

    report.add_text("Classification Report", result.classification_report_str)

    out = report.save("results/flora_example_report.html")
    print(f"Report saved: {out}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
