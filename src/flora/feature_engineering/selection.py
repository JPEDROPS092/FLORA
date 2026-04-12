"""Feature selection for microbiome ML pipelines.

Implements three complementary selection strategies:
1. Variance-based: remove near-constant features
2. Prevalence-based: remove rare features (present in few samples)
3. Importance-based: rank features by Random Forest importance or SHAP

All functions operate on wide-format Polars DataFrames (sample_id + features).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.feature_engineering.selection")


def filter_by_variance(
    df: pl.DataFrame,
    min_variance: float = 0.01,
    relative: bool = True,
) -> pl.DataFrame:
    """Remove features with variance below a threshold.

    Low-variance features carry minimal discriminatory power and inflate
    model complexity without contributing to accuracy.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
    min_variance : float
        Minimum variance threshold. If ``relative=True``, interpreted as
        a fraction of the maximum per-feature variance.
    relative : bool
        If True, threshold is applied relative to the maximum variance
        (features below ``min_variance * max_variance`` are removed).

    Returns
    -------
    polars.DataFrame
        Filtered DataFrame with low-variance features removed.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    X = df.select(feature_cols).to_numpy().astype(np.float64)

    variances = X.var(axis=0)
    if relative:
        threshold = min_variance * variances.max()
    else:
        threshold = min_variance

    keep_mask = variances >= threshold
    kept = [c for c, k in zip(feature_cols, keep_mask) if k]
    n_removed = len(feature_cols) - len(kept)

    logger.info(
        "Variance filter: removed %d features (threshold=%.4f), %d retained",
        n_removed, threshold, len(kept),
    )
    return df.select(["sample_id"] + kept)


def filter_by_prevalence(
    df: pl.DataFrame,
    min_prevalence: float = 0.1,
    abundance_threshold: float = 0.0,
) -> pl.DataFrame:
    """Remove features present in fewer than ``min_prevalence`` fraction of samples.

    Rare features are likely uninformative for cross-sample comparisons and
    can introduce noise in distance-based analyses.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
    min_prevalence : float
        Minimum fraction of samples in which a feature must be present.
        A feature is considered present if its abundance exceeds
        ``abundance_threshold``.
    abundance_threshold : float
        Minimum abundance value to count a sample as having the feature.

    Returns
    -------
    polars.DataFrame
        Filtered DataFrame with rare features removed.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    X = df.select(feature_cols).to_numpy().astype(np.float64)
    n_samples = X.shape[0]

    prevalence = (X > abundance_threshold).mean(axis=0)
    keep_mask = prevalence >= min_prevalence
    kept = [c for c, k in zip(feature_cols, keep_mask) if k]
    n_removed = len(feature_cols) - len(kept)

    logger.info(
        "Prevalence filter: removed %d features (min_prevalence=%.2f), %d retained",
        n_removed, min_prevalence, len(kept),
    )
    return df.select(["sample_id"] + kept)


def select_by_importance(
    df: pl.DataFrame,
    labels: pl.Series | list,
    task: str = "classification",
    n_features: int | None = None,
    top_fraction: float | None = None,
    random_state: int = 42,
    n_estimators: int = 200,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Rank and select features by Random Forest importance.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
    labels : polars.Series or list
        Target labels aligned with ``df`` rows.
    task : str
        ``"classification"`` or ``"regression"``.
    n_features : int, optional
        Number of top features to select. Mutually exclusive with
        ``top_fraction``.
    top_fraction : float, optional
        Fraction of features to select (e.g. 0.2 = top 20%). Mutually
        exclusive with ``n_features``.
    random_state : int
        Random seed for the Random Forest estimator.
    n_estimators : int
        Number of trees in the Random Forest.

    Returns
    -------
    selected_df : polars.DataFrame
        Feature table filtered to selected features.
    importance_df : polars.DataFrame
        DataFrame with ``feature`` and ``importance`` columns, sorted
        descending by importance.

    Raises
    ------
    ValueError
        If both or neither of ``n_features`` and ``top_fraction`` are given.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    if n_features is not None and top_fraction is not None:
        raise ValueError("Specify either n_features or top_fraction, not both")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    X = df.select(feature_cols).to_numpy().astype(np.float64)
    y = list(labels) if hasattr(labels, "__iter__") else labels

    if task == "classification":
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
    elif task == "regression":
        model = RandomForestRegressor(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unknown task '{task}'. Use 'classification' or 'regression'")

    model.fit(X, y)
    importances = model.feature_importances_

    importance_df = pl.DataFrame({
        "feature": feature_cols,
        "importance": importances,
    }).sort("importance", descending=True)

    if n_features is not None:
        k = min(n_features, len(feature_cols))
    elif top_fraction is not None:
        k = max(1, int(len(feature_cols) * top_fraction))
    else:
        k = len(feature_cols) // 5

    top_features = importance_df["feature"][:k].to_list()
    selected_df = df.select(["sample_id"] + top_features)

    logger.info(
        "Importance selection: kept %d/%d features (task=%s)",
        k, len(feature_cols), task,
    )
    return selected_df, importance_df
