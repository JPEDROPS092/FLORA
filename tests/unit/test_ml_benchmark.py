"""Tests for benchmark and evaluation utilities."""

import polars as pl

from flora.ml.evaluation.benchmark import (
    map_top_features_to_taxonomy,
    run_classification_benchmark,
)
from flora.ml.evaluation.metrics import evaluate_classification


def make_dataset() -> tuple[pl.DataFrame, pl.DataFrame]:
    samples = [f"S{i:02d}" for i in range(18)]
    labels = ["A"] * 6 + ["B"] * 6 + ["C"] * 6
    rows = {"sample_id": samples}
    for j in range(12):
        values = []
        for label in labels:
            base = 20 if (label == "A" and j < 4) or (label == "B" and 4 <= j < 8) or (label == "C" and j >= 8) else 2
            values.append(float(base))
        rows[f"F{j:02d}"] = values
    return pl.DataFrame(rows), pl.DataFrame({"sample_id": samples, "label": labels})


def test_evaluate_classification_includes_balanced_accuracy():
    result = evaluate_classification(
        y_true=["A", "A", "B", "B"],
        y_pred=["A", "B", "B", "B"],
    )
    assert "balanced_accuracy" in result
    assert 0.0 <= result["balanced_accuracy"] <= 1.0


def test_run_classification_benchmark_returns_summary():
    feature_df, labels_df = make_dataset()
    result = run_classification_benchmark(
        feature_df,
        labels_df,
        dataset_name="toy",
        target_column="label",
        normalizations=["raw", "clr"],
        models=["majority", "random_forest"],
        prevalence_threshold=0.0,
        cv_splits=3,
        cv_repeats=1,
        random_state=42,
    )
    assert len(result.summary) == 4
    assert "balanced_accuracy_mean" in result.summary.columns
    assert any(k.startswith("toy:raw:majority") for k in result.confusion_matrices)


def test_map_top_features_to_taxonomy():
    importance_df = pl.DataFrame({"feature": ["F1", "F2"], "importance": [0.9, 0.2]})
    taxonomy_df = pl.DataFrame({
        "feature_id": ["F1", "F2"],
        "phylum": ["Firmicutes", "Proteobacteria"],
        "genus": ["G1", "G2"],
    })
    mapped = map_top_features_to_taxonomy(importance_df, taxonomy_df, top_n=2)
    assert "phylum" in mapped.columns
    assert mapped["phylum"][0] == "Firmicutes"
