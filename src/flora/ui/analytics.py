"""Reusable Plotly builders for the FLORA web interface."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from flora.viz.diversity_plots import plot_beta_diversity_heatmap
from flora.viz.taxonomy_plots import plot_taxonomy_heatmap

UI_COLORS = {
    "paper": "#f5f1e8",
    "panel": "#fffdf8",
    "text": "#1f2937",
    "muted": "#5b6472",
    "border": "rgba(31, 41, 55, 0.12)",
    "accent": "#0f766e",
    "accent_2": "#dc6b2f",
    "accent_3": "#285943",
}


def apply_ui_layout(fig: go.Figure, *, height: int = 560) -> go.Figure:
    """Apply the FLORA web UI theme to a figure."""
    fig.update_layout(
        template="plotly_white",
        height=height,
        paper_bgcolor=UI_COLORS["panel"],
        plot_bgcolor=UI_COLORS["panel"],
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=13, color=UI_COLORS["text"]),
        margin=dict(l=54, r=36, t=72, b=52),
        title=dict(x=0.02, xanchor="left"),
        legend=dict(
            bgcolor="rgba(255,253,248,0.82)",
            bordercolor=UI_COLORS["border"],
            borderwidth=1,
        ),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(15, 23, 42, 0.08)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(15, 23, 42, 0.08)", zeroline=False)
    return fig


def build_taxonomy_heatmap(
    abundance_df: pl.DataFrame,
    *,
    level: str = "genus",
    top_n: int = 25,
    title: str | None = None,
) -> go.Figure:
    """Build a taxonomic heatmap from sample-level abundance data."""
    fig = plot_taxonomy_heatmap(
        abundance_df,
        level=level,
        top_n=top_n,
        normalize=True,
        title=title or f"Interactive {level.title()} Heatmap",
    )
    return apply_ui_layout(fig, height=max(520, min(1100, 340 + len(abundance_df["sample_id"].unique()) * 12)))


def build_beta_heatmap(
    beta_df: pl.DataFrame,
    *,
    metric: str = "bray_curtis",
    title: str | None = None,
) -> go.Figure:
    """Build a beta-diversity heatmap."""
    fig = plot_beta_diversity_heatmap(
        beta_df,
        metric=metric,
        title=title or f"Beta Diversity Heatmap ({metric.replace('_', ' ').title()})",
    )
    return apply_ui_layout(fig, height=fig.layout.height or 620)


def _prepare_hierarchy_frame(
    df: pl.DataFrame,
    *,
    group_by: str | None = None,
) -> "object":
    path = [group_by] if group_by and group_by in df.columns else []
    path.extend([c for c in ("kingdom", "phylum", "class", "order", "family", "genus", "species") if c in df.columns])

    cleaned = df
    for col in path:
        cleaned = cleaned.with_columns(
            pl.col(col).fill_null("Unassigned").replace("", "Unassigned")
        )

    return cleaned.to_pandas(), path


def build_krona_sunburst(
    df: pl.DataFrame,
    *,
    group_by: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Build a Krona-like circular taxonomy plot using Plotly sunburst."""
    pdf, path = _prepare_hierarchy_frame(df, group_by=group_by)
    fig = px.sunburst(
        pdf,
        path=path,
        values="abundance",
        color="abundance",
        color_continuous_scale="Brwnyl",
        title=title or "Krona-style Taxonomy Overview",
    )
    fig.update_traces(insidetextorientation="radial", hovertemplate="%{label}<br>Abundance=%{value:.4f}<extra></extra>")
    return apply_ui_layout(fig, height=700)


def build_taxonomy_tree(
    df: pl.DataFrame,
    *,
    group_by: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Build a taxonomic lineage tree as an icicle plot."""
    pdf, path = _prepare_hierarchy_frame(df, group_by=group_by)
    fig = px.icicle(
        pdf,
        path=path,
        values="abundance",
        color="abundance",
        color_continuous_scale="Tealgrn",
        title=title or "Taxonomic Lineage Tree",
    )
    fig.update_traces(root_color="#efe5d1")
    return apply_ui_layout(fig, height=740)


def _coerce_profile_matrix(profile_df: pl.DataFrame, level: str) -> tuple[list[str], list[str], np.ndarray]:
    pivot = (
        profile_df.group_by(["sample_id", level])
        .agg(pl.col("abundance").sum().alias("abundance"))
        .pivot(index="sample_id", on=level, values="abundance", aggregate_function="sum")
        .fill_null(0.0)
    )
    taxa = [c for c in pivot.columns if c != "sample_id"]
    matrix = pivot.select(taxa).to_numpy().astype(float) if taxa else np.empty((0, 0))
    return pivot["sample_id"].to_list(), taxa, matrix


def build_correlation_network(
    profile_df: pl.DataFrame,
    *,
    level: str = "genus",
    top_n: int = 18,
    threshold: float = 0.35,
    title: str | None = None,
) -> go.Figure:
    """Build a co-abundance correlation network for the top taxa."""
    _, taxa, matrix = _coerce_profile_matrix(profile_df, level)
    if matrix.size == 0 or len(taxa) < 2:
        fig = go.Figure()
        fig.add_annotation(text="Not enough taxa to build a network.", showarrow=False)
        return apply_ui_layout(fig, height=520)

    totals = matrix.sum(axis=0)
    order = np.argsort(totals)[::-1][:top_n]
    taxa = [taxa[i] for i in order]
    matrix = matrix[:, order]

    matrix = matrix / (matrix.sum(axis=1, keepdims=True) + 1e-12)
    corr = np.corrcoef(matrix, rowvar=False)
    abundance = matrix.mean(axis=0)

    angles = np.linspace(0, 2 * math.pi, len(taxa), endpoint=False)
    radius = 1.0
    xs = radius * np.cos(angles)
    ys = radius * np.sin(angles)

    fig = go.Figure()
    for i in range(len(taxa)):
        for j in range(i + 1, len(taxa)):
            weight = corr[i, j]
            if np.isnan(weight) or abs(weight) < threshold:
                continue
            fig.add_trace(go.Scatter(
                x=[xs[i], xs[j]],
                y=[ys[i], ys[j]],
                mode="lines",
                hoverinfo="text",
                text=[f"{taxa[i]} ↔ {taxa[j]}<br>corr={weight:.3f}"] * 2,
                line=dict(
                    color="rgba(15,118,110,0.65)" if weight > 0 else "rgba(220,107,47,0.55)",
                    width=1.2 + abs(weight) * 5,
                ),
                showlegend=False,
            ))

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=taxa,
        textposition="top center",
        hovertemplate="%{text}<br>mean relative abundance=%{marker.size:.3f}<extra></extra>",
        marker=dict(
            size=np.clip(12 + abundance * 180, 14, 34),
            color=abundance,
            colorscale="Tealgrn",
            line=dict(color="#fffdf8", width=1.5),
            showscale=True,
            colorbar=dict(title="Mean abundance"),
        ),
        showlegend=False,
    ))

    fig.update_layout(
        title=title or f"{level.title()} Co-abundance Network",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
    )
    return apply_ui_layout(fig, height=620)


def build_publication_checklist(tables: dict[str, int]) -> list[dict[str, str | bool]]:
    """Return checklist items for publication-grade microbiome analysis coverage."""
    return [
        {"label": "Alpha diversity: Shannon / Chao1", "done": bool(tables.get("diversity_alpha"))},
        {"label": "Beta diversity: Bray-Curtis", "done": bool(tables.get("diversity_beta"))},
        {"label": "Structure: PCoA / PCA / NMDS-ready", "done": bool(tables.get("asv")) and bool(tables.get("samples"))},
        {"label": "Taxonomy: barplot + heatmap", "done": bool(tables.get("taxonomy"))},
        {"label": "Statistics / ML overlays", "done": bool(tables.get("samples")) and bool(tables.get("asv"))},
    ]
