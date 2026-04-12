"""Microbiome unsupervised clustering pipeline.

Supports K-Means and HDBSCAN on PCoA/UMAP embeddings or raw feature matrices.
Automatically computes Silhouette and Davies-Bouldin quality metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.clustering")

ClusterMethod = Literal["kmeans", "hdbscan"]


@dataclass
class ClusteringResult:
    """Results from an unsupervised clustering run.

    Attributes
    ----------
    method : str
        Clustering algorithm used.
    n_clusters : int
        Number of clusters found (or specified for K-Means).
    labels : polars.DataFrame
        DataFrame with ``sample_id`` and ``cluster`` columns.
    silhouette : float or None
        Silhouette coefficient (higher is better; range -1 to 1).
    davies_bouldin : float or None
        Davies-Bouldin index (lower is better).
    noise_fraction : float
        Fraction of samples labeled as noise (HDBSCAN only; 0.0 for K-Means).
    """

    method: str
    n_clusters: int
    labels: pl.DataFrame
    silhouette: float | None
    davies_bouldin: float | None
    noise_fraction: float = 0.0


class MicrobiomeClusterer:
    """Unsupervised clustering for microbiome samples.

    Parameters
    ----------
    method : str
        ``"kmeans"`` or ``"hdbscan"``.
    n_clusters : int
        For K-Means: number of clusters. Ignored by HDBSCAN.
    random_state : int
        Reproducibility seed.
    scale : bool
        If True, standardize features before clustering.
    method_params : dict, optional
        Extra parameters forwarded to the clustering estimator.

    Examples
    --------
    >>> clusterer = MicrobiomeClusterer(method="kmeans", n_clusters=4)
    >>> result = clusterer.fit(pcoa_wide_df)
    >>> print(result.silhouette)
    """

    def __init__(
        self,
        method: ClusterMethod = "kmeans",
        n_clusters: int = 4,
        random_state: int = 42,
        scale: bool = True,
        method_params: dict[str, Any] | None = None,
    ) -> None:
        self.method = method
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.scale = scale
        self.method_params = method_params or {}

    def _build_estimator(self) -> Any:
        if self.method == "kmeans":
            return KMeans(
                n_clusters=self.n_clusters,
                random_state=self.random_state,
                n_init=self.method_params.get("n_init", 10),
                max_iter=self.method_params.get("max_iter", 300),
            )
        if self.method == "hdbscan":
            try:
                import hdbscan
            except ImportError as exc:
                raise MLError(
                    "hdbscan package is required. Install with: pip install hdbscan"
                ) from exc
            return hdbscan.HDBSCAN(
                min_cluster_size=self.method_params.get("min_cluster_size", 5),
                min_samples=self.method_params.get("min_samples", None),
                metric=self.method_params.get("metric", "euclidean"),
                core_dist_n_jobs=self.method_params.get("n_jobs", -1),
            )
        raise MLError(f"Unknown clustering method '{self.method}'", model=self.method)

    def fit(self, df: pl.DataFrame) -> ClusteringResult:
        """Fit the clustering model on a feature DataFrame.

        Parameters
        ----------
        df : polars.DataFrame
            Feature matrix with ``sample_id`` as first column. Can be
            PCoA/UMAP coordinates (wide format) or a normalized ASV table.

        Returns
        -------
        ClusteringResult
            Cluster labels and quality metrics.

        Raises
        ------
        MLError
            If clustering fails or the algorithm is not available.
        """
        if "sample_id" not in df.columns:
            raise MLError(
                "DataFrame must have a 'sample_id' column",
                model=self.method,
            )

        feature_cols = [c for c in df.columns if c != "sample_id"]
        sample_ids = df["sample_id"].to_list()
        X = df.select(feature_cols).to_numpy().astype(np.float64)

        if self.scale:
            scaler = StandardScaler()
            X = scaler.fit_transform(X)

        estimator = self._build_estimator()

        try:
            labels_raw = estimator.fit_predict(X)
        except Exception as exc:
            raise MLError(
                f"Clustering failed: {exc}",
                model=self.method,
            ) from exc

        labels_df = pl.DataFrame({
            "sample_id": sample_ids,
            "cluster": labels_raw.astype(int).tolist(),
        })

        n_clusters = len(set(labels_raw) - {-1})
        noise_fraction = float((labels_raw == -1).mean()) if self.method == "hdbscan" else 0.0

        valid_mask = labels_raw != -1
        sil = None
        db = None
        if n_clusters >= 2 and valid_mask.sum() >= n_clusters:
            try:
                sil = float(silhouette_score(X[valid_mask], labels_raw[valid_mask]))
                db = float(davies_bouldin_score(X[valid_mask], labels_raw[valid_mask]))
            except Exception as exc:
                logger.warning("Could not compute clustering metrics: %s", exc)

        logger.info(
            "Clustering [%s]: n_clusters=%d silhouette=%s db=%s noise=%.2f%%",
            self.method,
            n_clusters,
            f"{sil:.4f}" if sil is not None else "N/A",
            f"{db:.4f}" if db is not None else "N/A",
            noise_fraction * 100,
        )

        return ClusteringResult(
            method=self.method,
            n_clusters=n_clusters,
            labels=labels_df,
            silhouette=sil,
            davies_bouldin=db,
            noise_fraction=noise_fraction,
        )

    def sweep_k(
        self,
        df: pl.DataFrame,
        k_range: range = range(2, 11),
    ) -> pl.DataFrame:
        """Run K-Means for multiple values of k and compare quality metrics.

        Parameters
        ----------
        df : polars.DataFrame
            Feature matrix.
        k_range : range
            Range of k values to evaluate.

        Returns
        -------
        polars.DataFrame
            Table with columns: k, silhouette, davies_bouldin.
        """
        if self.method != "kmeans":
            raise MLError("sweep_k is only valid for kmeans clustering", model=self.method)

        rows = []
        for k in k_range:
            self.n_clusters = k
            try:
                result = self.fit(df)
                rows.append({
                    "k": k,
                    "silhouette": result.silhouette,
                    "davies_bouldin": result.davies_bouldin,
                })
            except Exception as exc:
                logger.warning("k=%d failed: %s", k, exc)

        return pl.DataFrame(rows)
