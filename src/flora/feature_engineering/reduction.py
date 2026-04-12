"""Dimensionality reduction for microbiome data.

Implements PCoA (Principal Coordinates Analysis) via scikit-bio and UMAP
(Uniform Manifold Approximation and Projection). Both methods return
Polars DataFrames with (sample_id, component, value) rows that are
stored in the DuckDB ``dim_reduction`` table.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl
from scipy.spatial.distance import pdist, squareform
from sklearn.decomposition import PCA

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.feature_engineering.reduction")


def compute_pcoa(
    df: pl.DataFrame,
    metric: str = "braycurtis",
    n_components: int = 3,
) -> pl.DataFrame:
    """Compute Principal Coordinates Analysis (PCoA).

    PCoA (also called metric MDS) embeds samples into low-dimensional
    space based on a pairwise distance matrix. Standard for microbiome
    beta-diversity visualization.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
        Values should be non-negative (raw counts, TSS, or CLR).
    metric : str
        Distance metric understood by ``scipy.spatial.distance.pdist``.
        Common choices: ``"braycurtis"``, ``"euclidean"``, ``"cosine"``.
    n_components : int
        Number of principal coordinate axes to return.

    Returns
    -------
    polars.DataFrame
        Long-format table with columns: sample_id, method, component, value.
        ``method`` is set to ``"pcoa_{metric}"``.

    Raises
    ------
    ValidationError
        If the input DataFrame is invalid.
    """
    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    sample_ids = df["sample_id"].to_list()
    X = df.select(feature_cols).to_numpy().astype(np.float64)

    dist_vec = pdist(X, metric=metric)
    D = squareform(dist_vec)
    n = D.shape[0]

    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ (D ** 2) @ J
    B = (B + B.T) / 2

    eigenvalues, eigenvectors = np.linalg.eigh(B)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    pos_mask = eigenvalues > 0
    coords = np.zeros((n, min(n_components, n)))
    for k in range(min(n_components, pos_mask.sum())):
        if eigenvalues[k] > 0:
            coords[:, k] = eigenvectors[:, k] * np.sqrt(eigenvalues[k])

    rows = []
    method = f"pcoa_{metric}"
    for i, sid in enumerate(sample_ids):
        for comp in range(coords.shape[1]):
            rows.append({
                "sample_id": sid,
                "method": method,
                "component": comp + 1,
                "value": float(coords[i, comp]),
            })

    logger.info(
        "PCoA computed: %d samples, %d components, metric=%s",
        n, n_components, metric,
    )
    return pl.DataFrame(rows)


def compute_umap(
    df: pl.DataFrame,
    n_components: int = 2,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "euclidean",
    random_state: int = 42,
) -> pl.DataFrame:
    """Compute UMAP embedding for microbiome data visualization.

    UMAP preserves local structure in high-dimensional feature spaces,
    making it useful for visualizing sample clusters after CLR normalization.

    Parameters
    ----------
    df : polars.DataFrame
        Wide-format feature table with ``sample_id`` as first column.
    n_components : int
        Number of UMAP dimensions (typically 2 for visualization, 3 for 3D).
    n_neighbors : int
        UMAP neighborhood size parameter. Smaller values preserve local
        structure; larger values capture global structure.
    min_dist : float
        Minimum distance between embedded points. Smaller = tighter clusters.
    metric : str
        Distance metric for UMAP graph construction.
    random_state : int
        Reproducibility seed.

    Returns
    -------
    polars.DataFrame
        Long-format table with columns: sample_id, method, component, value.

    Raises
    ------
    ImportError
        If ``umap-learn`` is not installed.
    ValidationError
        If input is invalid.
    """
    try:
        import umap
    except ImportError as exc:
        raise ImportError(
            "umap-learn is required for UMAP computation. "
            "Install with: pip install umap-learn"
        ) from exc

    if "sample_id" not in df.columns:
        raise ValidationError("DataFrame must have a 'sample_id' column", field="sample_id")

    feature_cols = [c for c in df.columns if c != "sample_id"]
    sample_ids = df["sample_id"].to_list()
    X = df.select(feature_cols).to_numpy().astype(np.float64)

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=random_state,
    )
    embedding = reducer.fit_transform(X)

    rows = []
    for i, sid in enumerate(sample_ids):
        for comp in range(n_components):
            rows.append({
                "sample_id": sid,
                "method": "umap",
                "component": comp + 1,
                "value": float(embedding[i, comp]),
            })

    logger.info("UMAP computed: %d samples, %d components", len(sample_ids), n_components)
    return pl.DataFrame(rows)
