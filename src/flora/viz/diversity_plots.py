"""Diversity visualization: PCoA, rarefaction curves, alpha/beta plots."""

from __future__ import annotations

import logging
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import polars as pl

logger = logging.getLogger("flora.viz.diversity")


def plot_pcoa(
    pcoa_df: pl.DataFrame,
    metadata_df: pl.DataFrame | None = None,
    color_by: str | None = None,
    components: tuple[int, int] = (1, 2),
    three_d: bool = False,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Interactive PCoA scatter plot.

    Parameters
    ----------
    pcoa_df : polars.DataFrame
        Long-format PCoA output from ``compute_pcoa()`` with columns:
        sample_id, method, component, value.
    metadata_df : polars.DataFrame, optional
        Metadata with sample_id for coloring/hover.
    color_by : str, optional
        Metadata column to use for color coding.
    components : tuple of int
        Which principal coordinate axes to plot on x and y.
    three_d : bool
        If True, generate a 3D scatter plot (requires 3 components).
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive PCoA plot.
    """
    pc_x, pc_y = components
    method = pcoa_df["method"][0] if "method" in pcoa_df.columns else "pcoa"

    pivot = pcoa_df.pivot(
        index="sample_id", on="component", values="value", aggregate_function="first"
    )
    pivot = pivot.rename({str(c): f"PC{c}" for c in pivot.columns if str(c).isdigit()})

    if metadata_df is not None and color_by:
        if "sample_id" in metadata_df.columns and color_by in metadata_df.columns:
            pivot = pivot.join(
                metadata_df.select(["sample_id", color_by]), on="sample_id", how="left"
            )

    x_col = f"PC{pc_x}"
    y_col = f"PC{pc_y}"
    pdf = pivot.to_pandas()

    if three_d:
        z_col = f"PC{components[0] + 1}"
        if z_col not in pdf.columns:
            three_d = False

    if three_d:
        fig = px.scatter_3d(
            pdf,
            x=x_col,
            y=y_col,
            z=f"PC{components[0] + 1}",
            color=color_by if color_by and color_by in pdf.columns else None,
            hover_name="sample_id",
            title=title or f"PCoA Plot ({method})",
        )
    else:
        fig = px.scatter(
            pdf,
            x=x_col,
            y=y_col,
            color=color_by if color_by and color_by in pdf.columns else None,
            hover_name="sample_id",
            title=title or f"PCoA Plot ({method})",
            labels={x_col: f"PC{pc_x}", y_col: f"PC{pc_y}"},
        )

    fig.update_traces(marker=dict(size=8, opacity=0.8))
    fig.update_layout(plot_bgcolor="white")

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))
        logger.info("PCoA plot saved to %s", output_path)

    return fig


def plot_rarefaction_curves(
    rarefaction_df: pl.DataFrame,
    recommended_depth: int | None = None,
    max_samples_display: int = 20,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Plot rarefaction curves with 95% confidence intervals.

    Parameters
    ----------
    rarefaction_df : polars.DataFrame
        Output from ``rarefaction_curve()`` with columns:
        sample_id, depth, mean_richness, ci_lower, ci_upper.
    recommended_depth : int, optional
        If provided, draw a vertical dashed line at this depth.
    max_samples_display : int
        Maximum samples to show (prevents overplotting).
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive rarefaction curve plot.
    """
    fig = go.Figure()
    samples = rarefaction_df["sample_id"].unique().to_list()[:max_samples_display]

    import numpy as np
    colors = px.colors.qualitative.Set3
    for i, sid in enumerate(samples):
        sub = rarefaction_df.filter(pl.col("sample_id") == sid).sort("depth")
        color = colors[i % len(colors)]

        fig.add_trace(go.Scatter(
            x=sub["depth"].to_list(),
            y=sub["mean_richness"].to_list(),
            mode="lines",
            name=sid,
            line=dict(color=color),
            showlegend=True,
        ))

        ci_x = sub["depth"].to_list() + sub["depth"].to_list()[::-1]
        ci_y = sub["ci_upper"].to_list() + sub["ci_lower"].to_list()[::-1]
        fig.add_trace(go.Scatter(
            x=ci_x,
            y=ci_y,
            fill="toself",
            fillcolor=color,
            opacity=0.15,
            line=dict(color="rgba(255,255,255,0)"),
            showlegend=False,
            hoverinfo="skip",
        ))

    if recommended_depth:
        fig.add_vline(
            x=recommended_depth,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Recommended depth: {recommended_depth:,}",
        )

    fig.update_layout(
        title=title or "Rarefaction Curves",
        xaxis_title="Sequencing Depth",
        yaxis_title="Observed ASV Richness",
        plot_bgcolor="white",
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def plot_alpha_diversity(
    alpha_df: pl.DataFrame,
    metric: str = "shannon",
    group_by: str | None = None,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Box plot of alpha diversity distribution.

    Parameters
    ----------
    alpha_df : polars.DataFrame
        Table with columns: sample_id, metric, value (long format).
        Can also be a wide DataFrame with one column per metric.
    metric : str
        Which alpha diversity metric to plot.
    group_by : str, optional
        Metadata column name for grouping (must be present in alpha_df).
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive box plot.
    """
    if "metric" in alpha_df.columns and "value" in alpha_df.columns:
        sub = alpha_df.filter(pl.col("metric") == metric)
    elif metric in alpha_df.columns:
        sub = alpha_df.select(["sample_id"] + ([group_by] if group_by else []) + [metric])
        sub = sub.rename({metric: "value"})
    else:
        raise ValueError(f"Metric '{metric}' not found in DataFrame")

    pdf = sub.to_pandas()
    x_col = group_by if group_by and group_by in pdf.columns else None

    fig = px.box(
        pdf,
        x=x_col,
        y="value",
        color=x_col,
        points="all",
        title=title or f"Alpha Diversity: {metric.replace('_', ' ').title()}",
        labels={"value": metric.replace("_", " ").title()},
    )
    fig.update_layout(plot_bgcolor="white")

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def plot_beta_diversity_heatmap(
    beta_df: pl.DataFrame,
    metric: str = "bray_curtis",
    cluster: bool = True,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Clustered heatmap of the beta diversity distance matrix.

    Parameters
    ----------
    beta_df : polars.DataFrame
        Long-format distance table with columns: sample_a, sample_b,
        metric, distance. Output from DuckDB ``diversity_beta`` table.
    metric : str
        Which beta diversity metric to display.
    cluster : bool
        If True, apply hierarchical clustering to order samples.
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive distance matrix heatmap.
    """
    import numpy as np
    from scipy.cluster.hierarchy import dendrogram, linkage
    from scipy.spatial.distance import squareform

    sub = beta_df.filter(pl.col("metric") == metric) if "metric" in beta_df.columns else beta_df
    samples = sorted(set(sub["sample_a"].to_list() + sub["sample_b"].to_list()))
    n = len(samples)
    idx = {s: i for i, s in enumerate(samples)}

    D = np.zeros((n, n))
    for row in sub.iter_rows(named=True):
        i = idx.get(row["sample_a"])
        j = idx.get(row["sample_b"])
        if i is not None and j is not None:
            D[i, j] = row["distance"]
            D[j, i] = row["distance"]

    if cluster and n > 2:
        try:
            condensed = squareform(D)
            Z = linkage(condensed, method="average")
            order = dendrogram(Z, no_plot=True)["leaves"]
            samples = [samples[i] for i in order]
            D = D[np.ix_(order, order)]
        except Exception as exc:
            logger.warning("Hierarchical clustering failed: %s. Skipping reordering.", exc)

    fig = go.Figure(go.Heatmap(
        z=D,
        x=samples,
        y=samples,
        colorscale="Blues",
        colorbar=dict(title=f"{metric.replace('_', ' ').title()} Distance"),
    ))
    fig.update_layout(
        title=title or f"Beta Diversity: {metric.replace('_', ' ').title()}",
        xaxis_tickangle=-45,
        height=max(500, n * 12),
        width=max(600, n * 12),
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))
        logger.info("Beta diversity heatmap saved to %s", output_path)

    return fig
