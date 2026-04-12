"""Visualization module for FLORA microbiome analysis."""

from flora.viz.taxonomy_plots import (
    plot_taxonomy_barplot,
    plot_taxonomy_heatmap,
)
from flora.viz.diversity_plots import (
    plot_pcoa,
    plot_rarefaction_curves,
    plot_alpha_diversity,
    plot_beta_diversity_heatmap,
)
from flora.viz.ml_plots import (
    plot_confusion_matrix,
    plot_feature_importance,
    plot_cluster_scatter,
    plot_regression_actual_vs_predicted,
)

__all__ = [
    "plot_taxonomy_barplot",
    "plot_taxonomy_heatmap",
    "plot_pcoa",
    "plot_rarefaction_curves",
    "plot_alpha_diversity",
    "plot_beta_diversity_heatmap",
    "plot_confusion_matrix",
    "plot_feature_importance",
    "plot_cluster_scatter",
    "plot_regression_actual_vs_predicted",
]
