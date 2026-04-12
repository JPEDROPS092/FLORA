"""Alpha diversity computation for microbiome samples.

All metrics operate on a wide-format count table (samples x features) and
return a DataFrame with one column per metric. Rarefaction is applied
before computation when a sampling_depth is specified.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import polars as pl

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.diversity.alpha")

AlphaMetric = Literal["shannon", "observed_features", "chao1", "simpson", "faith_pd"]


def compute_alpha_diversity(
    df: pl.DataFrame,
    metrics: list[str] | None = None,
    sampling_depth: int | None = None,
) -> pl.DataFrame:
    """Compute alpha diversity metrics for all samples.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format count table with ``sample_id`` as first column.
    metrics : list of str, optional
        Metrics to compute. Defaults to: shannon, observed_features, chao1.
        Supported: shannon, observed_features, chao1, simpson.
    sampling_depth : int, optional
        If provided, rarefy before computing diversity.

    Returns
    -------
    polars.DataFrame
        Table with ``sample_id`` and one column per diversity metric.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    selected = metrics or ["shannon", "observed_features", "chao1"]
    supported = {"shannon", "observed_features", "chao1", "simpson"}
    unknown = set(selected) - supported
    if unknown:
        raise ValidationError(f"Unknown diversity metrics: {unknown}")

    if sampling_depth is not None:
        from flora.feature_engineering.normalization import rarefy

        df = rarefy(df, depth=sampling_depth)

    feature_cols = [c for c in df.columns if c != "sample_id"]
    sample_ids = df["sample_id"].to_list()
    X = df.select(feature_cols).to_numpy().astype(np.float64)

    result = {"sample_id": sample_ids}

    for metric in selected:
        if metric == "shannon":
            result["shannon"] = _shannon(X).tolist()
        elif metric == "observed_features":
            result["observed_features"] = (X > 0).sum(axis=1).astype(float).tolist()
        elif metric == "chao1":
            result["chao1"] = _chao1(X).tolist()
        elif metric == "simpson":
            result["simpson"] = _simpson(X).tolist()

    return pl.DataFrame(result)


def _shannon(X: np.ndarray) -> np.ndarray:
    """Shannon entropy H = -sum(p * log(p)) for each sample."""
    row_sums = X.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.where(row_sums > 0, X / row_sums, 0.0)
        log_p = np.where(p > 0, np.log(p), 0.0)
    return -(p * log_p).sum(axis=1)


def _chao1(X: np.ndarray) -> np.ndarray:
    """Chao1 richness estimator: S_obs + f1^2 / (2 * f2 + 1)."""
    s_obs = (X > 0).sum(axis=1).astype(float)
    f1 = (X == 1).sum(axis=1).astype(float)
    f2 = (X == 2).sum(axis=1).astype(float)
    chao1 = s_obs + (f1 ** 2) / (2.0 * f2 + 1.0)
    return chao1


def _simpson(X: np.ndarray) -> np.ndarray:
    """Simpson diversity D = 1 - sum(n*(n-1)) / (N*(N-1))."""
    n = X.astype(np.float64)
    N = n.sum(axis=1)
    numerator = (n * (n - 1)).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(N > 1, 1.0 - numerator / (N * (N - 1)), 0.0)
    return result
