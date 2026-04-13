"""Experimental benchmarking utilities for FLORA classification studies."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from math import sqrt
from typing import Any

import numpy as np
import polars as pl
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

from flora.feature_engineering.normalization import clr_transform, rarefy, tss_transform
from flora.feature_engineering.selection import filter_by_prevalence
from flora.ml.evaluation.metrics import evaluate_classification
from flora.ml.optimization.tuner import HyperparameterTuner

logger = logging.getLogger("flora.ml.evaluation.benchmark")


@dataclass
class BenchmarkResult:
    """Structured result for benchmark execution."""

    summary: pl.DataFrame
    fold_metrics: pl.DataFrame
    confusion_matrices: dict[str, list[list[int]]]
    tuned_params: dict[str, dict[str, Any]]


def run_classification_benchmark(
    feature_df: pl.DataFrame,
    labels_df: pl.DataFrame,
    *,
    dataset_name: str,
    target_column: str,
    normalizations: list[str] | None = None,
    models: list[str] | None = None,
    prevalence_threshold: float = 0.05,
    cv_splits: int = 5,
    cv_repeats: int = 3,
    random_state: int = 42,
    tune_models: list[str] | None = None,
    tuning_trials: int = 15,
) -> BenchmarkResult:
    """Benchmark models and normalizations with repeated stratified CV."""
    normalizations = normalizations or ["raw", "tss", "clr"]
    models = models or ["majority", "random_forest", "xgboost", "svm"]
    tune_models = tune_models or []

    labeled_base = labels_df.select(["sample_id", target_column]).drop_nulls()
    fold_rows: list[dict[str, Any]] = []
    confusion_matrices: dict[str, list[list[int]]] = {}
    tuned_params: dict[str, dict[str, Any]] = {}

    for normalization in normalizations:
        logger.info(
            "Preparing dataset=%s normalization=%s prevalence=%.3f",
            dataset_name,
            normalization,
            prevalence_threshold,
        )
        prepared = prepare_feature_table(
            feature_df,
            labeled_base,
            target_column=target_column,
            normalization=normalization,
            prevalence_threshold=prevalence_threshold,
        )
        X, y, sample_ids, feature_cols = _extract_xy(prepared, target_column)
        label_encoder = LabelEncoder()
        y_enc = label_encoder.fit_transform(y)
        splitter = RepeatedStratifiedKFold(
            n_splits=cv_splits,
            n_repeats=cv_repeats,
            random_state=random_state,
        )

        tuned_by_model: dict[str, dict[str, Any]] = {}
        if tune_models:
            tune_df = prepared
            for model_name in tune_models:
                if model_name not in models or model_name == "majority":
                    continue
                logger.info(
                    "Tuning model=%s dataset=%s normalization=%s trials=%d",
                    model_name,
                    dataset_name,
                    normalization,
                    tuning_trials,
                )
                tuner = HyperparameterTuner(
                    model_type=model_name,
                    task="classification",
                    target_column=target_column,
                    n_trials=tuning_trials,
                    cv_folds=min(cv_splits, 4),
                    random_state=random_state,
                    n_jobs=1,
                )
                tuned = tuner.tune(tune_df, study_name=f"{dataset_name}_{normalization}_{model_name}")
                tuned_by_model[model_name] = tuned.best_params
                tuned_params[f"{dataset_name}:{normalization}:{model_name}"] = tuned.best_params

        for model_name in models:
            logger.info(
                "Benchmarking model=%s dataset=%s normalization=%s splits=%d repeats=%d",
                model_name,
                dataset_name,
                normalization,
                cv_splits,
                cv_repeats,
            )
            predictions: list[str] = []
            truths: list[str] = []
            split_index = 0
            params = tuned_by_model.get(model_name, {})
            for train_idx, test_idx in splitter.split(X, y_enc):
                estimator = build_classifier(model_name, random_state=random_state, model_params=params)
                estimator.fit(X[train_idx], y_enc[train_idx])
                y_pred_enc = estimator.predict(X[test_idx])
                y_pred = label_encoder.inverse_transform(y_pred_enc)
                y_true = label_encoder.inverse_transform(y_enc[test_idx])
                y_proba = estimator.predict_proba(X[test_idx]) if hasattr(estimator, "predict_proba") else None

                metrics = evaluate_classification(
                    y_true=y_true,
                    y_pred=y_pred,
                    y_proba=y_proba,
                    label_names=list(label_encoder.classes_),
                )
                repeat_idx = split_index // cv_splits
                fold_idx = split_index % cv_splits
                fold_rows.append(
                    {
                        "dataset": dataset_name,
                        "normalization": normalization,
                        "model": model_name,
                        "repeat": repeat_idx,
                        "fold": fold_idx,
                        "n_samples": len(sample_ids),
                        "n_features": len(feature_cols),
                        "accuracy": metrics["accuracy"],
                        "balanced_accuracy": metrics["balanced_accuracy"],
                        "f1_macro": metrics["f1_macro"],
                        "roc_auc": metrics["roc_auc"],
                    }
                )
                truths.extend(y_true.tolist())
                predictions.extend(y_pred.tolist())
                split_index += 1

            key = f"{dataset_name}:{normalization}:{model_name}"
            labels = list(label_encoder.classes_)
            confusion_matrices[key] = confusion_matrix(truths, predictions, labels=labels).tolist()

    fold_df = pl.DataFrame(fold_rows)
    summary = summarize_benchmark(fold_df)
    return BenchmarkResult(
        summary=summary,
        fold_metrics=fold_df,
        confusion_matrices=confusion_matrices,
        tuned_params=tuned_params,
    )


def prepare_feature_table(
    feature_df: pl.DataFrame,
    labels_df: pl.DataFrame,
    *,
    target_column: str,
    normalization: str,
    prevalence_threshold: float,
) -> pl.DataFrame:
    """Apply normalization and prevalence filter, then join labels."""
    if normalization == "raw":
        transformed = feature_df
    elif normalization == "tss":
        transformed = tss_transform(feature_df)
    elif normalization == "clr":
        transformed = clr_transform(feature_df)
    else:
        raise ValueError(f"Unsupported normalization '{normalization}'")

    filtered = filter_by_prevalence(transformed, min_prevalence=prevalence_threshold)
    return filtered.join(labels_df, on="sample_id", how="inner").drop_nulls()


def run_rarefaction_sensitivity(
    feature_df: pl.DataFrame,
    labels_df: pl.DataFrame,
    *,
    dataset_name: str,
    target_column: str,
    depths: list[int],
    normalization: str = "clr",
    model: str = "xgboost",
    prevalence_threshold: float = 0.05,
    cv_splits: int = 5,
    cv_repeats: int = 2,
    random_state: int = 42,
) -> pl.DataFrame:
    """Evaluate model sensitivity to rarefaction depth."""
    rows: list[dict[str, Any]] = []
    for depth in depths:
        rarefied = rarefy(feature_df, depth=depth, random_state=random_state)
        result = run_classification_benchmark(
            rarefied,
            labels_df,
            dataset_name=dataset_name,
            target_column=target_column,
            normalizations=[normalization],
            models=[model],
            prevalence_threshold=prevalence_threshold,
            cv_splits=cv_splits,
            cv_repeats=cv_repeats,
            random_state=random_state,
        )
        row = result.summary.row(0, named=True)
        row["sampling_depth"] = depth
        rows.append(row)
    return pl.DataFrame(rows).sort("sampling_depth")


def run_prevalence_sensitivity(
    feature_df: pl.DataFrame,
    labels_df: pl.DataFrame,
    *,
    dataset_name: str,
    target_column: str,
    thresholds: list[float],
    normalization: str = "clr",
    model: str = "xgboost",
    cv_splits: int = 5,
    cv_repeats: int = 2,
    random_state: int = 42,
) -> pl.DataFrame:
    """Evaluate model sensitivity to prevalence filtering."""
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        result = run_classification_benchmark(
            feature_df,
            labels_df,
            dataset_name=dataset_name,
            target_column=target_column,
            normalizations=[normalization],
            models=[model],
            prevalence_threshold=threshold,
            cv_splits=cv_splits,
            cv_repeats=cv_repeats,
            random_state=random_state,
        )
        row = result.summary.row(0, named=True)
        row["prevalence_threshold"] = threshold
        rows.append(row)
    return pl.DataFrame(rows).sort("prevalence_threshold")


def map_top_features_to_taxonomy(
    importance_df: pl.DataFrame,
    taxonomy_df: pl.DataFrame,
    *,
    feature_col: str = "feature",
    top_n: int = 20,
) -> pl.DataFrame:
    """Map top discriminant features back to taxonomy."""
    top = importance_df.head(top_n).rename({feature_col: "feature_id"})
    taxonomy = taxonomy_df.rename({"feature_id": "feature_id"})
    return top.join(taxonomy, on="feature_id", how="left")


def summarize_taxonomic_signal(mapped_df: pl.DataFrame, level: str = "phylum") -> pl.DataFrame:
    """Summarize the dominant taxonomic levels among top-ranked features."""
    if level not in mapped_df.columns:
        raise ValueError(f"Taxonomic level '{level}' not found")
    score_col = "mean_abs_shap" if "mean_abs_shap" in mapped_df.columns else "importance"
    return (
        mapped_df
        .with_columns(pl.col(level).fill_null("Unclassified"))
        .group_by(level)
        .agg(
            pl.len().alias("n_features"),
            pl.col(score_col).sum().alias("total_score"),
        )
        .sort("total_score", descending=True)
    )


def build_classifier(model_name: str, *, random_state: int, model_params: dict[str, Any] | None = None) -> Any:
    """Factory for benchmark classifiers."""
    params = model_params or {}
    if model_name == "majority":
        return DummyClassifier(strategy="prior")
    if model_name == "random_forest":
        return RandomForestClassifier(
            n_estimators=params.get("n_estimators", 300),
            max_depth=params.get("max_depth"),
            min_samples_split=params.get("min_samples_split", 2),
            max_features=params.get("max_features", "sqrt"),
            random_state=random_state,
            n_jobs=-1,
        )
    if model_name == "svm":
        return SVC(
            C=params.get("C", 1.0),
            kernel=params.get("kernel", "rbf"),
            gamma=params.get("gamma", "scale"),
            probability=True,
            random_state=random_state,
        )
    if model_name == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=params.get("n_estimators", 300),
            max_depth=params.get("max_depth", 6),
            learning_rate=params.get("learning_rate", 0.1),
            subsample=params.get("subsample", 0.8),
            colsample_bytree=params.get("colsample_bytree", 0.8),
            eval_metric="logloss",
            random_state=random_state,
            n_jobs=1,
        )
    raise ValueError(f"Unsupported model '{model_name}'")


def summarize_benchmark(fold_df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate repeated-CV metrics with mean, std and 95% CI."""
    rows: list[dict[str, Any]] = []
    metrics = ["accuracy", "balanced_accuracy", "f1_macro", "roc_auc"]
    for group in fold_df.partition_by(["dataset", "normalization", "model"], as_dict=True).values():
        row = {
            "dataset": group["dataset"][0],
            "normalization": group["normalization"][0],
            "model": group["model"][0],
            "n_samples": int(group["n_samples"][0]),
            "n_features": int(group["n_features"][0]),
        }
        n = len(group)
        for metric in metrics:
            values = [v for v in group[metric].to_list() if v is not None]
            arr = np.array(values, dtype=float)
            mean = float(arr.mean()) if len(arr) else None
            std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0 if len(arr) == 1 else None
            ci = (1.96 * std / sqrt(len(arr))) if len(arr) > 1 and std is not None else 0.0 if len(arr) == 1 else None
            row[f"{metric}_mean"] = mean
            row[f"{metric}_std"] = std
            row[f"{metric}_ci_low"] = None if mean is None or ci is None else mean - ci
            row[f"{metric}_ci_high"] = None if mean is None or ci is None else mean + ci
        rows.append(row)
    return pl.DataFrame(rows).sort(["dataset", "normalization", "f1_macro_mean"], descending=[False, False, True])


def _extract_xy(df: pl.DataFrame, target_column: str) -> tuple[np.ndarray, list[str], list[str], list[str]]:
    feature_cols = [c for c in df.columns if c not in ("sample_id", target_column)]
    X = df.select(feature_cols).to_numpy().astype(np.float64)
    y = df[target_column].to_list()
    sample_ids = df["sample_id"].to_list()
    return X, y, sample_ids, feature_cols
