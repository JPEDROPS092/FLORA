"""Normalization and rarefaction for microbiome feature tables.

All functions operate on Polars DataFrames where the first column is
``sample_id`` and remaining columns are feature (ASV) counts or abundances.

Compositionality note
---------------------
16S rRNA amplicon data are compositional: counts reflect sampling effort,
not absolute abundance. Two standard treatments are implemented here:

- TSS (Total Sum Scaling): divide each sample's counts by its total.
  Simple but sensitive to high-abundance taxa dominating the composition.
- CLR (Centered Log-Ratio, Aitchison 1986): subtract each feature's log
  value from the per-sample geometric mean of logs. Correct for
  Euclidean distance computations and linear models.

A pseudo-count of 0.5 is applied before CLR to handle zeros.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from flora.core.exceptions import ValidationError

if TYPE_CHECKING:
    pass

logger = logging.getLogger("flora.feature_engineering.normalization")


def _extract_feature_matrix(df: pl.DataFrame) -> tuple[pl.DataFrame, np.ndarray, list[str]]:
    """Split a wide DataFrame into sample IDs and a numeric matrix.

    Parameters
    ----------
    df : polars.DataFrame
        Wide format with ``sample_id`` as first column.

    Returns
    -------
    meta : polars.DataFrame
        DataFrame containing non-numeric columns (at minimum ``sample_id``).
    matrix : numpy.ndarray
        2D float64 array of shape (n_samples, n_features).
    feature_cols : list of str
        Column names corresponding to matrix columns.
    """
    feature_cols = [c for c in df.columns if c != "sample_id"]
    matrix = df.select(feature_cols).to_numpy().astype(np.float64)
    meta = df.select("sample_id")
    return meta, matrix, feature_cols


def clr_transform(
    df: pl.DataFrame,
    pseudo_count: float = 0.5,
) -> pl.DataFrame:
    """Apply Centered Log-Ratio (CLR) transformation.

    CLR is the standard transformation for compositional microbiome data.
    A pseudo-count is added before log transformation to handle zero counts.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
        Values should be non-negative counts or abundances.
    pseudo_count : float
        Value added to all counts before log transformation to handle zeros.
        Default 0.5 follows Aitchison (1986) recommendation.

    Returns
    -------
    polars.DataFrame
        CLR-transformed feature table with same shape as input.

    Raises
    ------
    ValidationError
        If ``df`` does not contain ``sample_id`` or has no feature columns.

    Notes
    -----
    For sample i and feature j:
    ``clr(x_ij) = log(x_ij + c) - (1/D) * sum_k log(x_ik + c)``
    where D is the number of features and c is the pseudo-count.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    if not feature_cols:
        raise ValidationError("DataFrame has no feature columns after 'sample_id'")

    meta, X, cols = _extract_feature_matrix(df)
    X_pc = X + pseudo_count
    log_X = np.log(X_pc)
    geometric_mean = log_X.mean(axis=1, keepdims=True)
    clr = log_X - geometric_mean

    result = pl.DataFrame({col: clr[:, i] for i, col in enumerate(cols)})
    return pl.concat([meta, result], how="horizontal")


def tss_transform(df: pl.DataFrame) -> pl.DataFrame:
    """Apply Total Sum Scaling (TSS / relative abundance) transformation.

    Divides each sample's feature vector by its total count sum, producing
    relative abundances that sum to 1.0 per sample.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.

    Returns
    -------
    polars.DataFrame
        Relative abundance table with same shape as input.

    Raises
    ------
    ValidationError
        If ``df`` does not contain ``sample_id``.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    meta, X, cols = _extract_feature_matrix(df)
    row_sums = X.sum(axis=1, keepdims=True)
    zero_mask = row_sums == 0
    if zero_mask.any():
        logger.warning(
            "%d samples have total abundance = 0; TSS will produce NaN for those samples",
            zero_mask.sum(),
        )
    tss = np.where(row_sums > 0, X / row_sums, 0.0)

    result = pl.DataFrame({col: tss[:, i] for i, col in enumerate(cols)})
    return pl.concat([meta, result], how="horizontal")


def rarefy(
    df: pl.DataFrame,
    depth: int | None = None,
    random_state: int = 42,
) -> pl.DataFrame:
    """Rarefy a feature table to a fixed sequencing depth.

    Rarefaction subsamples each sample's reads to a common depth without
    replacement, removing samples that have fewer reads than the target depth.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format count table with ``sample_id`` as first column.
        Values must be non-negative integers (counts, not fractions).
    depth : int, optional
        Target sampling depth. If None, uses the minimum sample depth that
        retains at least 95% of samples (``suggest_rarefaction_depth``).
    random_state : int
        Seed for the random number generator.

    Returns
    -------
    polars.DataFrame
        Rarefied count table. Samples with fewer reads than ``depth`` are
        excluded. Columns with zero total after rarefaction are retained
        (they may be 0 for some samples).

    Raises
    ------
    ValidationError
        If ``depth`` exceeds the read count of all samples.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    meta, X, cols = _extract_feature_matrix(df)
    X_int = X.astype(np.int64)
    sample_totals = X_int.sum(axis=1)

    if depth is None:
        depth = suggest_rarefaction_depth(df)
        logger.info("Auto-selected rarefaction depth: %d", depth)

    keep_mask = sample_totals >= depth
    n_dropped = (~keep_mask).sum()
    if n_dropped > 0:
        logger.warning(
            "Dropping %d samples with depth < %d (%.1f%% of total)",
            n_dropped,
            depth,
            100.0 * n_dropped / len(X_int),
        )

    if not keep_mask.any():
        raise ValidationError(
            f"No samples have depth >= {depth}. "
            f"Maximum sample depth is {sample_totals.max()}.",
        )

    rng = np.random.default_rng(random_state)
    X_keep = X_int[keep_mask]
    sample_ids_keep = [meta["sample_id"][i] for i in range(len(meta)) if keep_mask[i]]

    rarefied = np.zeros_like(X_keep)
    for i, row in enumerate(X_keep):
        total = row.sum()
        flat = np.repeat(np.arange(len(row)), row)
        chosen = rng.choice(flat, size=depth, replace=False)
        counts = np.bincount(chosen, minlength=len(row))
        rarefied[i] = counts

    result = pl.DataFrame({col: rarefied[:, j] for j, col in enumerate(cols)})
    meta_keep = pl.DataFrame({"sample_id": sample_ids_keep})
    return pl.concat([meta_keep, result], how="horizontal")


def suggest_rarefaction_depth(
    df: pl.DataFrame,
    target_retention: float = 0.95,
) -> int:
    """Suggest an optimal rarefaction depth.

    Returns the maximum depth that retains at least ``target_retention``
    fraction of samples.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format count table with ``sample_id`` as first column.
    target_retention : float
        Fraction of samples to retain (default 0.95 = retain 95% of samples).

    Returns
    -------
    int
        Suggested rarefaction depth.
    """
    feature_cols = [c for c in df.columns if c != "sample_id"]
    totals = df.select(feature_cols).sum_horizontal().sort()
    n = len(totals)
    cutoff_idx = int(n * (1.0 - target_retention))
    depth = int(totals[cutoff_idx])
    logger.debug(
        "Suggested rarefaction depth %d retains %.0f%% of %d samples",
        depth, target_retention * 100, n,
    )
    return max(depth, 1)


def rarefaction_curve(
    df: pl.DataFrame,
    depths: list[int] | None = None,
    n_iterations: int = 10,
    random_state: int = 42,
) -> pl.DataFrame:
    """Compute rarefaction curves for all samples.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format count table with ``sample_id`` as first column.
    depths : list of int, optional
        Sampling depths to evaluate. If None, generates 20 evenly-spaced
        points from 100 to the minimum sample depth.
    n_iterations : int
        Number of random subsampling iterations per depth (for CI estimation).
    random_state : int
        Seed for the random number generator.

    Returns
    -------
    polars.DataFrame
        Long-format table with columns: sample_id, depth, mean_richness,
        ci_lower, ci_upper.
    """
    feature_cols = [c for c in df.columns if c != "sample_id"]
    meta, X, cols = _extract_feature_matrix(df)
    X_int = X.astype(np.int64)
    sample_totals = X_int.sum(axis=1)

    if depths is None:
        max_depth = int(sample_totals.min())
        depths = [int(d) for d in np.linspace(100, max_depth, 20).astype(int)]

    rng = np.random.default_rng(random_state)
    rows = []
    sample_ids = df["sample_id"].to_list()

    for i, (row, sid) in enumerate(zip(X_int, sample_ids)):
        total = row.sum()
        flat = np.repeat(np.arange(len(row)), row)
        for depth in depths:
            if depth > total:
                continue
            richness_vals = []
            for _ in range(n_iterations):
                chosen = rng.choice(flat, size=depth, replace=False)
                counts = np.bincount(chosen, minlength=len(row))
                richness_vals.append((counts > 0).sum())
            arr = np.array(richness_vals, dtype=np.float64)
            rows.append({
                "sample_id": sid,
                "depth": depth,
                "mean_richness": float(arr.mean()),
                "ci_lower": float(np.percentile(arr, 2.5)),
                "ci_upper": float(np.percentile(arr, 97.5)),
            })

    return pl.DataFrame(rows)
