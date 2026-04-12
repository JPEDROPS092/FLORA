"""SHAP-based feature importance and model explanation.

Uses TreeExplainer for tree-based models (RF, XGBoost) and KernelExplainer
as a fallback. Returns Polars DataFrames and optionally generates Plotly
SHAP summary plots.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.explainability")


@dataclass
class SHAPResult:
    """Results from SHAP feature importance analysis.

    Attributes
    ----------
    shap_values : numpy.ndarray
        Raw SHAP values array of shape (n_samples, n_features).
    feature_names : list of str
        Feature names corresponding to SHAP value columns.
    mean_abs_shap : polars.DataFrame
        Table of mean absolute SHAP values per feature, sorted descending.
    explainer_type : str
        Type of SHAP explainer used.
    """

    shap_values: np.ndarray
    feature_names: list[str]
    mean_abs_shap: pl.DataFrame
    explainer_type: str


class SHAPAnalyzer:
    """Compute SHAP values for any fitted FLORA ML model.

    Parameters
    ----------
    model : Any
        Fitted estimator (RandomForest, XGBoost, SVM, etc.).
    feature_names : list of str
        Names of the features used during training.
    task : str
        ``"classification"`` or ``"regression"``.
    n_background_samples : int
        Number of background samples for KernelExplainer. Ignored for
        TreeExplainer.

    Examples
    --------
    >>> analyzer = SHAPAnalyzer(model=clf.model, feature_names=clf.feature_names)
    >>> result = analyzer.explain(X_test_df)
    >>> fig = analyzer.summary_plot(result)
    """

    def __init__(
        self,
        model: Any,
        feature_names: list[str],
        task: str = "classification",
        n_background_samples: int = 100,
    ) -> None:
        try:
            import shap  # noqa: F401
        except ImportError as exc:
            raise MLError("shap package is required. Install with: pip install shap") from exc

        self.model = model
        self.feature_names = feature_names
        self.task = task
        self.n_background_samples = n_background_samples

    def _get_explainer(self, X_background: np.ndarray) -> tuple[Any, str]:
        import shap

        model_type = type(self.model).__name__
        tree_models = {
            "RandomForestClassifier",
            "RandomForestRegressor",
            "XGBClassifier",
            "XGBRegressor",
            "GradientBoostingClassifier",
            "GradientBoostingRegressor",
            "ExtraTreesClassifier",
            "ExtraTreesRegressor",
        }
        if model_type in tree_models:
            return shap.TreeExplainer(self.model), "TreeExplainer"

        background = shap.sample(X_background, min(self.n_background_samples, len(X_background)))
        if hasattr(self.model, "predict_proba"):
            return shap.KernelExplainer(self.model.predict_proba, background), "KernelExplainer"
        return shap.KernelExplainer(self.model.predict, background), "KernelExplainer"

    def explain(
        self,
        df: pl.DataFrame,
        max_samples: int = 500,
    ) -> SHAPResult:
        """Compute SHAP values for the given samples.

        Parameters
        ----------
        df : polars.DataFrame
            Feature matrix. May include ``sample_id`` column (it will be
            excluded from SHAP computation).
        max_samples : int
            Maximum number of samples for KernelExplainer to keep tractable.

        Returns
        -------
        SHAPResult
            SHAP values, feature names, and mean absolute importance table.

        Raises
        ------
        MLError
            If SHAP computation fails.
        """
        feat_cols = [c for c in df.columns if c != "sample_id"]
        X = df.select(feat_cols).to_numpy().astype(np.float64)

        if len(X) > max_samples:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(X), size=max_samples, replace=False)
            X_explain = X[idx]
        else:
            X_explain = X

        explainer, explainer_type = self._get_explainer(X)

        try:
            raw = explainer.shap_values(X_explain)
        except Exception as exc:
            raise MLError(f"SHAP computation failed: {exc}") from exc

        if isinstance(raw, list):
            shap_values = np.array(raw[1]) if self.task == "classification" else np.array(raw[0])
        else:
            shap_values = np.array(raw)

        if shap_values.ndim == 3:
            shap_values = shap_values[:, :, 1]

        mean_abs = np.abs(shap_values).mean(axis=0)
        importance_df = pl.DataFrame({
            "feature": feat_cols,
            "mean_abs_shap": mean_abs.tolist(),
        }).sort("mean_abs_shap", descending=True)

        logger.info(
            "SHAP analysis complete: %d samples, %d features, explainer=%s",
            len(X_explain), len(feat_cols), explainer_type,
        )
        return SHAPResult(
            shap_values=shap_values,
            feature_names=feat_cols,
            mean_abs_shap=importance_df,
            explainer_type=explainer_type,
        )

    def summary_plot(
        self,
        result: SHAPResult,
        max_display: int = 20,
        output_path: str | None = None,
    ) -> Any:
        """Generate a SHAP summary plot using Plotly.

        Parameters
        ----------
        result : SHAPResult
            Output from ``explain()``.
        max_display : int
            Number of top features to display.
        output_path : str, optional
            If provided, save the plot as HTML.

        Returns
        -------
        plotly.graph_objects.Figure
            Interactive SHAP summary bar chart.
        """
        import plotly.graph_objects as go

        top = result.mean_abs_shap.head(max_display)
        fig = go.Figure(go.Bar(
            x=top["mean_abs_shap"].to_list(),
            y=top["feature"].to_list(),
            orientation="h",
        ))
        fig.update_layout(
            title="SHAP Feature Importance (mean |SHAP value|)",
            xaxis_title="Mean |SHAP value|",
            yaxis_title="Feature",
            yaxis={"autorange": "reversed"},
            height=max(400, max_display * 25),
        )

        if output_path:
            fig.write_html(output_path)
            logger.info("SHAP summary plot saved to %s", output_path)

        return fig
