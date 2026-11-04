"""Visualization UI handlers."""

from __future__ import annotations

import json

from flora.core.exceptions import DatabaseError, ValidationError
from flora.ui.http import UiHttpError, json_success
from flora.ui.query_helpers import fetch_sample_taxonomy_profile, fetch_taxonomy_hierarchy


def _plot_payload(fig):
    return json_success(data={"plot": json.loads(fig.to_json())})


def _plot_error(exc: Exception) -> UiHttpError:
    if isinstance(exc, UiHttpError):
        return exc
    if isinstance(exc, (DatabaseError, ValidationError, ValueError, FileNotFoundError)):
        return UiHttpError(str(exc), status=400, code="plot_generation_failed")
    return UiHttpError(str(exc), status=500, code="internal_error")


def viz_taxonomy(state, params: dict):
    from flora.viz.taxonomy_plots import plot_taxonomy_barplot

    level = params.get("level", ["phylum"])[0]
    group_by = params.get("group_by", [None])[0]
    try:
        agg = state.db.aggregate_by_taxon(level=level, group_by=group_by)
        if agg.is_empty():
            raise UiHttpError(
                "Taxonomic composition requires ingested ASV and taxonomy data.",
                status=400,
                code="empty_feature_matrix",
            )
        fig = plot_taxonomy_barplot(agg, level=level, group_by=group_by, top_n=int(params.get("top_n", ["15"])[0]))
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_pcoa(state, params: dict):
    from flora.feature_engineering.reduction import compute_pcoa
    from flora.viz.diversity_plots import plot_pcoa

    normalize = params.get("normalize", ["clr"])[0]
    color_by = params.get("color_by", [None])[0]
    try:
        feature_matrix = state.pipeline.get_feature_matrix(normalize=normalize)
        if len(feature_matrix) < 2:
            raise UiHttpError(
                "PCoA requires at least 2 samples.",
                status=400,
                code="insufficient_samples",
            )
        pcoa_long = compute_pcoa(feature_matrix, metric="braycurtis", n_components=3)
        metadata = state.db.query("SELECT * FROM samples").to_polars()
        fig = plot_pcoa(
            pcoa_long,
            metadata_df=metadata if color_by else None,
            color_by=color_by,
        )
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_alpha(state, params: dict):
    from flora.diversity.alpha import compute_alpha_diversity
    from flora.viz.diversity_plots import plot_alpha_diversity

    metric = params.get("metric", ["shannon"])[0]
    group_by = params.get("group_by", [None])[0]
    try:
        feature_matrix = state.pipeline.get_feature_matrix(normalize=None)
        if feature_matrix.is_empty():
            raise UiHttpError(
                "Alpha diversity requires ingested ASV data.",
                status=400,
                code="empty_feature_matrix",
            )
        alpha = compute_alpha_diversity(feature_matrix, metrics=[metric])
        metadata = state.db.query("SELECT * FROM samples").to_polars()
        if group_by:
            alpha = alpha.join(
                metadata.select(["sample_id", group_by]),
                on="sample_id",
                how="left",
            )
        fig = plot_alpha_diversity(alpha, metric=metric, group_by=group_by)
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_taxonomy_heatmap(state, params: dict):
    from flora.ui.analytics import build_taxonomy_heatmap

    level = params.get("level", ["genus"])[0]
    top_n = int(params.get("top_n", ["25"])[0])
    try:
        sample_taxa = fetch_sample_taxonomy_profile(state.db, level)
        fig = build_taxonomy_heatmap(sample_taxa, level=level, top_n=top_n)
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_beta_heatmap(state, params: dict):
    from flora.diversity.beta import compute_beta_diversity
    from flora.ui.analytics import build_beta_heatmap

    metric = params.get("metric", ["bray_curtis"])[0]
    normalize = params.get("normalize", ["tss"])[0]
    max_samples = int(params.get("max_samples", ["60"])[0])
    try:
        feature_matrix = state.pipeline.get_feature_matrix(
            normalize=None if normalize == "none" else normalize
        )
        if len(feature_matrix) < 2:
            raise UiHttpError(
                "Beta diversity requires at least 2 samples.",
                status=400,
                code="insufficient_samples",
            )
        if max_samples > 0:
            feature_matrix = feature_matrix.head(max_samples)
        beta_df = compute_beta_diversity(feature_matrix, metric=metric)
        state.db.load_dataframe("diversity_beta", beta_df, if_exists="replace")
        fig = build_beta_heatmap(beta_df, metric=metric)
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_krona(state, params: dict):
    from flora.ui.analytics import build_krona_sunburst

    group_by = params.get("group_by", [None])[0]
    top_n = int(params.get("top_n", ["120"])[0])
    try:
        lineage = fetch_taxonomy_hierarchy(state.db, group_by, top_n=top_n)
        fig = build_krona_sunburst(lineage, group_by=group_by)
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_tree(state, params: dict):
    from flora.ui.analytics import build_taxonomy_tree

    group_by = params.get("group_by", [None])[0]
    top_n = int(params.get("top_n", ["120"])[0])
    try:
        lineage = fetch_taxonomy_hierarchy(state.db, group_by, top_n=top_n)
        fig = build_taxonomy_tree(lineage, group_by=group_by)
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc


def viz_network(state, params: dict):
    from flora.ui.analytics import build_correlation_network

    level = params.get("level", ["genus"])[0]
    top_n = int(params.get("top_n", ["18"])[0])
    threshold = float(params.get("threshold", ["0.35"])[0])
    try:
        profile = fetch_sample_taxonomy_profile(state.db, level)
        fig = build_correlation_network(
            profile,
            level=level,
            top_n=top_n,
            threshold=threshold,
        )
        return _plot_payload(fig)
    except Exception as exc:
        raise _plot_error(exc) from exc
