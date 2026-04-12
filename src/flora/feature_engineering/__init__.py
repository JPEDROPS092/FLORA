"""Feature engineering module for microbiome ML pipelines."""

from flora.feature_engineering.normalization import (
    clr_transform,
    tss_transform,
    rarefy,
    rarefaction_curve,
)
from flora.feature_engineering.selection import (
    filter_by_variance,
    filter_by_prevalence,
    select_by_importance,
)
from flora.feature_engineering.encoding import encode_metadata
from flora.feature_engineering.reduction import compute_pcoa, compute_umap

__all__ = [
    "clr_transform",
    "tss_transform",
    "rarefy",
    "rarefaction_curve",
    "filter_by_variance",
    "filter_by_prevalence",
    "select_by_importance",
    "encode_metadata",
    "compute_pcoa",
    "compute_umap",
]
