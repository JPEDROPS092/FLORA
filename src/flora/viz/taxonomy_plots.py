"""Taxonomy visualization functions.

All plots are powered by DuckDB queries and rendered with Plotly, producing
interactive HTML by default with optional static export.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import polars as pl

logger = logging.getLogger("flora.viz.taxonomy")


def plot_taxonomy_barplot(
    df: pl.DataFrame,
    level: str = "phylum",
    group_by: str | None = None,
    top_n: int = 15,
    normalize: bool = True,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Stacked bar chart of taxonomic composition.

    Parameters
    ----------
    df : polars.DataFrame
        Long-format table with columns: ``sample_id``, the taxonomic level
        column (e.g. ``phylum``), and ``mean_abundance`` (or abundance).
        Typically the output of ``FloraDB.aggregate_by_taxon()``.
    level : str
        Taxonomic level column name.
    group_by : str, optional
        If provided, group the x-axis by this column (e.g. ``biome``).
    top_n : int
        Show only the top N most abundant taxa; remainder aggregated as
        ``"Other"``.
    normalize : bool
        If True, normalize abundances to relative proportions per group.
    output_path : str or Path, optional
        Save the figure as HTML to this path.
    title : str, optional
        Plot title. Defaults to a descriptive auto-title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive stacked bar chart.
    """
    if level not in df.columns:
        raise ValueError(f"Column '{level}' not found in DataFrame. Available: {df.columns}")

    abundance_col = "mean_abundance" if "mean_abundance" in df.columns else "abundance"
    if abundance_col not in df.columns:
        raise ValueError(f"Expected abundance column '{abundance_col}' not found")

    top_taxa = (
        df.group_by(level)
        .agg(pl.col(abundance_col).sum().alias("total"))
        .sort("total", descending=True)
        .head(top_n)[level]
        .to_list()
    )

    df = df.with_columns(
        pl.when(pl.col(level).is_in(top_taxa))
        .then(pl.col(level))
        .otherwise(pl.lit("Other"))
        .alias(level)
    )

    x_col = group_by if group_by and group_by in df.columns else "sample_id"

    agg_df = (
        df.group_by([x_col, level])
        .agg(pl.col(abundance_col).sum().alias("abundance"))
    )

    if normalize:
        total_per_x = agg_df.group_by(x_col).agg(pl.col("abundance").sum().alias("total"))
        agg_df = agg_df.join(total_per_x, on=x_col).with_columns(
            (pl.col("abundance") / pl.col("total")).alias("abundance")
        ).drop("total")

    fig = px.bar(
        agg_df.to_pandas(),
        x=x_col,
        y="abundance",
        color=level,
        title=title or f"Taxonomic Composition by {level.capitalize()}",
        labels={"abundance": "Relative Abundance" if normalize else "Abundance", x_col: x_col},
        barmode="stack",
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        legend_title_text=level.capitalize(),
        plot_bgcolor="white",
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))
        logger.info("Taxonomy barplot saved to %s", output_path)

    return fig


def plot_taxonomy_heatmap(
    df: pl.DataFrame,
    level: str = "genus",
    top_n: int = 30,
    normalize: bool = True,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Heatmap of taxonomic abundances (samples x taxa).

    Parameters
    ----------
    df : polars.DataFrame
        Long-format abundance table with sample_id and taxonomic level columns.
    level : str
        Taxonomic column to use as columns in the heatmap.
    top_n : int
        Number of top taxa to display.
    normalize : bool
        Normalize abundances to relative proportions per sample.
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive heatmap.
    """
    abundance_col = "mean_abundance" if "mean_abundance" in df.columns else "abundance"

    top_taxa = (
        df.group_by(level)
        .agg(pl.col(abundance_col).sum())
        .sort(abundance_col, descending=True)
        .head(top_n)[level]
        .to_list()
    )

    filtered = df.filter(pl.col(level).is_in(top_taxa))

    pivot = (
        filtered.group_by(["sample_id", level])
        .agg(pl.col(abundance_col).sum())
        .pivot(index="sample_id", on=level, values=abundance_col, aggregate_function="sum")
        .fill_null(0.0)
    )

    sample_ids = pivot["sample_id"].to_list()
    taxa_cols = [c for c in pivot.columns if c != "sample_id"]
    Z = pivot.select(taxa_cols).to_numpy()

    if normalize:
        row_sums = Z.sum(axis=1, keepdims=True)
        Z = Z / (row_sums + 1e-12)

    fig = go.Figure(go.Heatmap(
        z=Z,
        x=taxa_cols,
        y=sample_ids,
        colorscale="YlOrRd",
        colorbar=dict(title="Relative Abundance" if normalize else "Abundance"),
    ))

    fig.update_layout(
        title=title or f"Taxonomic Abundance Heatmap ({level})",
        xaxis_title=level.capitalize(),
        yaxis_title="Sample",
        xaxis_tickangle=-45,
        height=max(400, len(sample_ids) * 15),
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))
        logger.info("Taxonomy heatmap saved to %s", output_path)

    return fig
