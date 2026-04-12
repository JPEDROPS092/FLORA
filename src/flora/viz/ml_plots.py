"""ML result visualization: confusion matrix, feature importance, clustering."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

logger = logging.getLogger("flora.viz.ml")


def plot_confusion_matrix(
    y_true: list | np.ndarray,
    y_pred: list | np.ndarray,
    label_names: list[str] | None = None,
    normalize: bool = True,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Heatmap confusion matrix for classification results.

    Parameters
    ----------
    y_true : array-like
        True class labels.
    y_pred : array-like
        Predicted class labels.
    label_names : list of str, optional
        Human-readable class names.
    normalize : bool
        If True, normalize by true class totals (show proportions).
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive confusion matrix heatmap.
    """
    from sklearn.metrics import confusion_matrix

    cm = confusion_matrix(y_true, y_pred)
    if normalize:
        with np.errstate(invalid="ignore"):
            cm_display = cm.astype(float) / cm.sum(axis=1, keepdims=True)
        cm_display = np.nan_to_num(cm_display)
        fmt_values = [[f"{v:.2f}" for v in row] for row in cm_display]
    else:
        cm_display = cm
        fmt_values = [[str(v) for v in row] for row in cm]

    labels = label_names or [str(i) for i in range(cm.shape[0])]
    fig = go.Figure(go.Heatmap(
        z=cm_display,
        x=labels,
        y=labels,
        text=fmt_values,
        texttemplate="%{text}",
        colorscale="Blues",
        colorbar=dict(title="Proportion" if normalize else "Count"),
    ))
    fig.update_layout(
        title=title or "Confusion Matrix",
        xaxis_title="Predicted",
        yaxis_title="True",
        xaxis_tickangle=-45,
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def plot_feature_importance(
    importance_df: pl.DataFrame,
    top_n: int = 20,
    feature_col: str = "feature",
    importance_col: str = "importance",
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Horizontal bar chart of feature importances.

    Parameters
    ----------
    importance_df : polars.DataFrame
        Table with feature and importance columns, sorted descending.
    top_n : int
        Number of top features to display.
    feature_col : str
        Name of the feature name column.
    importance_col : str
        Name of the importance score column.
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Horizontal bar chart.
    """
    top = importance_df.sort(importance_col, descending=True).head(top_n)
    fig = go.Figure(go.Bar(
        x=top[importance_col].to_list(),
        y=top[feature_col].to_list(),
        orientation="h",
        marker=dict(color="steelblue"),
    ))
    fig.update_layout(
        title=title or f"Top {top_n} Feature Importances",
        xaxis_title="Importance",
        yaxis={"autorange": "reversed"},
        plot_bgcolor="white",
        height=max(400, top_n * 20),
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def plot_cluster_scatter(
    coord_df: pl.DataFrame,
    cluster_labels: pl.DataFrame,
    x_component: int = 1,
    y_component: int = 2,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Scatter plot of PCoA/UMAP coordinates colored by cluster label.

    Parameters
    ----------
    coord_df : polars.DataFrame
        Long-format dimensional reduction output (sample_id, component, value).
    cluster_labels : polars.DataFrame
        Table with sample_id and cluster columns.
    x_component : int
        Component index for x-axis.
    y_component : int
        Component index for y-axis.
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Scatter plot.
    """
    pivot = coord_df.pivot(
        index="sample_id", on="component", values="value", aggregate_function="first"
    )
    pivot = pivot.rename({str(c): f"PC{c}" for c in pivot.columns if str(c).isdigit()})
    merged = pivot.join(cluster_labels, on="sample_id", how="left")

    x_col = f"PC{x_component}"
    y_col = f"PC{y_component}"

    pdf = merged.to_pandas()
    pdf["cluster"] = pdf["cluster"].astype(str)

    fig = px.scatter(
        pdf,
        x=x_col,
        y=y_col,
        color="cluster",
        hover_name="sample_id",
        title=title or "Cluster Scatter Plot",
        labels={x_col: f"PC{x_component}", y_col: f"PC{y_component}"},
    )
    fig.update_traces(marker=dict(size=9, opacity=0.8))
    fig.update_layout(plot_bgcolor="white")

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def plot_regression_actual_vs_predicted(
    y_true: list | np.ndarray,
    y_pred: list | np.ndarray,
    target_name: str = "target",
    output_path: str | Path | None = None,
    title: str | None = None,
) -> go.Figure:
    """Scatter plot of actual vs predicted values for regression.

    Parameters
    ----------
    y_true : array-like
        True values.
    y_pred : array-like
        Predicted values.
    target_name : str
        Name of the target variable for axis labels.
    output_path : str or Path, optional
        Save as HTML.
    title : str, optional
        Plot title.

    Returns
    -------
    plotly.graph_objects.Figure
        Scatter with identity line.
    """
    yt = np.array(y_true, dtype=np.float64)
    yp = np.array(y_pred, dtype=np.float64)

    all_vals = np.concatenate([yt, yp])
    mn, mx = all_vals.min(), all_vals.max()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=yt, y=yp, mode="markers",
        marker=dict(color="steelblue", size=7, opacity=0.7),
        name="samples",
    ))
    fig.add_trace(go.Scatter(
        x=[mn, mx], y=[mn, mx],
        mode="lines",
        line=dict(color="red", dash="dash"),
        name="perfect prediction",
    ))
    from sklearn.metrics import r2_score

    r2 = r2_score(yt, yp)
    fig.update_layout(
        title=title or f"Actual vs Predicted — {target_name} (R²={r2:.3f})",
        xaxis_title=f"Actual {target_name}",
        yaxis_title=f"Predicted {target_name}",
        plot_bgcolor="white",
    )

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig
