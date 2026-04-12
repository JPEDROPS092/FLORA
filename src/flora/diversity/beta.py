"""Beta diversity computation for microbiome samples."""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import polars as pl
from scipy.spatial.distance import braycurtis, pdist, squareform

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.diversity.beta")

BetaMetric = Literal["bray_curtis", "jaccard", "euclidean", "cosine"]


def compute_beta_diversity(
    df: pl.DataFrame,
    metric: BetaMetric = "bray_curtis",
) -> pl.DataFrame:
    """Compute pairwise beta diversity distance matrix.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format count table with ``sample_id`` as first column.
    metric : str
        Distance metric. Supported: bray_curtis, jaccard, euclidean, cosine.

    Returns
    -------
    polars.DataFrame
        Long-format distance table with columns: sample_a, sample_b, metric,
        distance. Compatible with the DuckDB ``diversity_beta`` table schema.

    Raises
    ------
    ValidationError
        If input is invalid or metric is unsupported.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    supported = {"bray_curtis", "jaccard", "euclidean", "cosine"}
    if metric not in supported:
        raise ValidationError(f"Unsupported beta diversity metric '{metric}'")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    sample_ids = df["sample_id"].to_list()
    X = df.select(feature_cols).to_numpy().astype(np.float64)

    scipy_metric = "braycurtis" if metric == "bray_curtis" else metric
    dist_vec = pdist(X, metric=scipy_metric)
    D = squareform(dist_vec)

    rows: list[dict] = []
    n = len(sample_ids)
    for i in range(n):
        for j in range(i + 1, n):
            rows.append({
                "sample_a": sample_ids[i],
                "sample_b": sample_ids[j],
                "metric": metric,
                "distance": float(D[i, j]),
            })

    logger.info(
        "Beta diversity computed: metric=%s, %d samples, %d pairwise distances",
        metric, n, len(rows),
    )
    return pl.DataFrame(rows)
