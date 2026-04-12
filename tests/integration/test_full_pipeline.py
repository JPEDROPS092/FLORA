"""Integration test: full FLORA pipeline from ingestion to ML output.

Uses in-memory DuckDB and synthetic data. Simulates the complete workflow
without any external dependencies (no QIIME2, no downloads).
"""

import numpy as np
import polars as pl
import pytest
import tempfile
from pathlib import Path

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.diversity.alpha import compute_alpha_diversity
from flora.diversity.beta import compute_beta_diversity
from flora.feature_engineering.normalization import clr_transform, tss_transform
from flora.feature_engineering.selection import filter_by_prevalence, filter_by_variance
from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.clustering.clusterer import MicrobiomeClusterer
from flora.ml.evaluation.bias import check_split_quality
from flora.reports.html_report import FLORAReport


@pytest.fixture
def full_db():
    """Fully populated DB for pipeline integration tests."""
    rng = np.random.default_rng(99)
    n_samples = 30
    n_features = 60

    counts = rng.negative_binomial(5, 0.3, size=(n_samples, n_features)).astype(float)
    sids = [f"S{i:03d}" for i in range(n_samples)]
    fids = [f"ASV_{j:04d}" for j in range(n_features)]

    biomes = ["Amazon", "Cerrado", "Atlantic_Forest"] * 10
    meta = pl.DataFrame({
        "sample_id": sids,
        "biome": biomes,
        "location": ["Brazil"] * n_samples,
        "latitude": [-3.0 + i * 0.1 for i in range(n_samples)],
        "longitude": [-60.0 + i * 0.1 for i in range(n_samples)],
        "sequencing_depth": [12000 + i * 300 for i in range(n_samples)],
    })

    phyla = ["Proteobacteria", "Firmicutes", "Bacteroidetes", "Actinobacteria"]
    taxonomy = pl.DataFrame({
        "feature_id": fids,
        "kingdom": ["Bacteria"] * n_features,
        "phylum": [phyla[j % len(phyla)] for j in range(n_features)],
        "class": [f"Class_{j % 6}" for j in range(n_features)],
        "order": [None] * n_features,
        "family": [f"Family_{j % 8}" for j in range(n_features)],
        "genus": [f"Genus_{j % 12}" for j in range(n_features)],
        "species": [None] * n_features,
        "confidence": [0.85] * n_features,
    })

    data = {"sample_id": sids}
    data.update({f: counts[:, i].tolist() for i, f in enumerate(fids)})
    wide = pl.DataFrame(data)

    long_df = wide.unpivot(
        index="sample_id",
        on=fids,
        variable_name="feature_id",
        value_name="abundance",
    ).filter(pl.col("abundance") > 0)

    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    db.load_dataframe("samples", meta)
    db.load_dataframe("asv", long_df)
    db.load_dataframe("taxonomy", taxonomy)
    db.create_views()
    yield db, meta, wide
    db.close()


def test_pivot_and_clr(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv()
    clr_df = clr_transform(feature_matrix)
    assert "sample_id" in clr_df.columns
    assert len(clr_df) == 30


def test_alpha_diversity_pipeline(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv()
    alpha = compute_alpha_diversity(
        feature_matrix,
        metrics=["shannon", "observed_features"],
        sampling_depth=None,
    )
    assert "shannon" in alpha.columns
    assert len(alpha) == 30


def test_beta_diversity_pipeline(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv(normalize="tss")
    beta = compute_beta_diversity(feature_matrix.head(10), metric="bray_curtis")
    assert len(beta) == 10 * 9 // 2


def test_classification_pipeline(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv(normalize="clr")
    labeled = feature_matrix.join(meta.select(["sample_id", "biome"]), on="sample_id")

    n = len(labeled)
    train = labeled.head(int(n * 0.7))
    test = labeled.tail(n - int(n * 0.7))

    clf = MicrobiomeClassifier(
        model="random_forest",
        target_column="biome",
        random_state=42,
        mlflow_tracking_uri=None,
    )
    result = clf.fit(train, test, cv_folds=3)

    assert result.accuracy >= 0.0
    assert result.f1_macro >= 0.0
    assert result.model is not None


def test_clustering_pipeline(full_db):
    db, meta, wide = full_db
    from flora.feature_engineering.reduction import compute_pcoa

    tss_df = db.pivot_asv(normalize="tss")
    pcoa_long = compute_pcoa(tss_df, metric="braycurtis", n_components=2)
    pcoa_wide = pcoa_long.pivot(
        index="sample_id", on="component", values="value", aggregate_function="first"
    ).rename({"1": "PC1", "2": "PC2"})

    clusterer = MicrobiomeClusterer(method="kmeans", n_clusters=3, random_state=42)
    result = clusterer.fit(pcoa_wide)

    assert result.n_clusters == 3
    assert len(result.labels) == 30


def test_data_quality_check(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv(normalize="clr")
    labeled = feature_matrix.join(meta.select(["sample_id", "biome"]), on="sample_id")

    n = len(labeled)
    train = labeled.head(int(n * 0.7))
    test = labeled.tail(n - int(n * 0.7))

    report = check_split_quality(train, test, target_column="biome")
    assert report.stats["n_train"] > 0
    assert report.stats["n_test"] > 0


def test_html_report_generation(full_db, tmp_path):
    db, meta, wide = full_db
    report = FLORAReport(title="Integration Test Report")
    report.add_metrics("Summary", {"Samples": 30, "ASVs": 60, "Biomes": 3})

    alpha = compute_alpha_diversity(db.pivot_asv(), metrics=["shannon"])
    report.add_table("Alpha Diversity", alpha, max_rows=10)

    out = tmp_path / "test_report.html"
    saved = report.save(out)
    assert saved.exists()
    content = saved.read_text()
    assert "Integration Test Report" in content
    assert "FLORA" in content


def test_aggregate_by_taxon_pipeline(full_db):
    db, meta, wide = full_db
    agg = db.aggregate_by_taxon(level="phylum", group_by="biome", metric="mean")
    assert "phylum" in agg.columns
    assert "biome" in agg.columns
    assert len(agg) > 0


def test_feature_selection_pipeline(full_db):
    db, meta, wide = full_db
    feature_matrix = db.pivot_asv(normalize="clr")
    filtered = filter_by_prevalence(feature_matrix, min_prevalence=0.5)
    assert len(filtered.columns) <= len(feature_matrix.columns)
    assert "sample_id" in filtered.columns
