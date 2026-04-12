"""Evaluation metrics for FLORA classifiers and regressors."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import polars as pl
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.evaluation")


def evaluate_classification(
    y_true: list | np.ndarray,
    y_pred: list | np.ndarray,
    y_proba: np.ndarray | None = None,
    label_names: list[str] | None = None,
) -> dict[str, Any]:
    """Compute a full classification evaluation report.

    Parameters
    ----------
    y_true : array-like
        True class labels.
    y_pred : array-like
        Predicted class labels.
    y_proba : numpy.ndarray, optional
        Predicted class probabilities for ROC-AUC computation.
    label_names : list of str, optional
        Human-readable class names for the classification report.

    Returns
    -------
    dict
        Keys: accuracy, f1_macro, f1_weighted, roc_auc,
        classification_report, confusion_matrix.
    """
    yt = np.array(y_true)
    yp = np.array(y_pred)

    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(yt, yp)),
        "f1_macro": float(f1_score(yt, yp, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(yt, yp, average="weighted", zero_division=0)),
        "classification_report": classification_report(
            yt, yp, target_names=label_names, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(yt, yp).tolist(),
    }

    if y_proba is not None:
        n_classes = y_proba.shape[1] if y_proba.ndim == 2 else 2
        try:
            if n_classes == 2:
                proba = y_proba[:, 1] if y_proba.ndim == 2 else y_proba
                metrics["roc_auc"] = float(roc_auc_score(yt, proba))
            else:
                metrics["roc_auc"] = float(
                    roc_auc_score(yt, y_proba, multi_class="ovr", average="macro")
                )
        except Exception as exc:
            logger.warning("ROC-AUC computation failed: %s", exc)
            metrics["roc_auc"] = None
    else:
        metrics["roc_auc"] = None

    return metrics


def evaluate_regression(
    y_true: list | np.ndarray,
    y_pred: list | np.ndarray,
) -> dict[str, float]:
    """Compute regression evaluation metrics.

    Parameters
    ----------
    y_true : array-like
        True continuous target values.
    y_pred : array-like
        Predicted values.

    Returns
    -------
    dict
        Keys: rmse, mae, r2, mse.
    """
    yt = np.array(y_true, dtype=np.float64)
    yp = np.array(y_pred, dtype=np.float64)
    return {
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "mse": float(mean_squared_error(yt, yp)),
        "mae": float(mean_absolute_error(yt, yp)),
        "r2": float(r2_score(yt, yp)),
    }
