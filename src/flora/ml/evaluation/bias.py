"""Data quality and bias assessment for ML splits.

Detects class imbalance, potential leakage, and split quality issues before
training starts. Returns a DataQualityReport that summarizes all findings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger("flora.ml.evaluation.bias")


@dataclass
class DataQualityReport:
    """Summary of data quality checks for an ML split.

    Attributes
    ----------
    issues : list of str
        Detected problems that may affect model validity.
    warnings : list of str
        Non-critical observations worth monitoring.
    stats : dict
        Summary statistics from the analysis.
    valid : bool
        True if no critical issues were found.
    """

    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        """Return True if no issues were detected."""
        return len(self.issues) == 0

    def add_issue(self, msg: str) -> None:
        """Append a critical issue."""
        self.issues.append(msg)
        logger.error("Data quality issue: %s", msg)

    def add_warning(self, msg: str) -> None:
        """Append a warning."""
        self.warnings.append(msg)
        logger.warning("Data quality warning: %s", msg)

    def __str__(self) -> str:
        lines = [f"DataQualityReport: {'PASS' if self.valid else 'FAIL'}"]
        for issue in self.issues:
            lines.append(f"  [ISSUE] {issue}")
        for warn in self.warnings:
            lines.append(f"  [WARN]  {warn}")
        if self.stats:
            lines.append("  Stats:")
            for k, v in self.stats.items():
                lines.append(f"    {k}: {v}")
        return "\n".join(lines)


def check_split_quality(
    train_df: pl.DataFrame,
    test_df: pl.DataFrame,
    target_column: str,
    task: str = "classification",
    max_imbalance_ratio: float = 10.0,
    min_test_fraction: float = 0.1,
) -> DataQualityReport:
    """Audit the quality of a train/test split before model training.

    Parameters
    ----------
    train_df : polars.DataFrame
        Training set with target column.
    test_df : polars.DataFrame
        Test set with target column.
    target_column : str
        Name of the target column.
    task : str
        ``"classification"`` or ``"regression"``.
    max_imbalance_ratio : float
        Maximum allowed ratio between the most and least frequent class.
        Applies to classification only.
    min_test_fraction : float
        Minimum fraction of total samples that must be in the test set.

    Returns
    -------
    DataQualityReport
        Identified issues and warnings.
    """
    report = DataQualityReport()
    total = len(train_df) + len(test_df)

    report.stats["n_train"] = len(train_df)
    report.stats["n_test"] = len(test_df)
    report.stats["total"] = total

    if total == 0:
        report.add_issue("Both train and test sets are empty")
        return report

    test_fraction = len(test_df) / total
    report.stats["test_fraction"] = round(test_fraction, 3)
    if test_fraction < min_test_fraction:
        report.add_warning(
            f"Test set is only {test_fraction:.1%} of total data "
            f"(minimum recommended: {min_test_fraction:.1%})"
        )

    if len(train_df) < 10:
        report.add_issue(f"Training set has only {len(train_df)} samples (minimum 10 recommended)")

    if len(test_df) < 5:
        report.add_issue(f"Test set has only {len(test_df)} samples (minimum 5 recommended)")

    if target_column not in train_df.columns:
        report.add_issue(f"Target column '{target_column}' not in train DataFrame")
        return report

    if target_column not in test_df.columns:
        report.add_issue(f"Target column '{target_column}' not in test DataFrame")

    if task == "classification":
        train_counts = (
            train_df.group_by(target_column).len().sort("len", descending=True)
        )
        report.stats["train_class_counts"] = dict(
            zip(train_counts[target_column].to_list(), train_counts["len"].to_list())
        )

        max_count = train_counts["len"][0]
        min_count = train_counts["len"][-1]
        if min_count == 0:
            report.add_issue("At least one class has 0 samples in training set")
        elif max_count / min_count > max_imbalance_ratio:
            report.add_warning(
                f"Class imbalance ratio {max_count/min_count:.1f}x exceeds "
                f"threshold {max_imbalance_ratio}x. Consider SMOTE or class weights."
            )

        train_classes = set(train_df[target_column].drop_nulls().to_list())
        test_classes = set(test_df[target_column].drop_nulls().to_list())
        unseen = test_classes - train_classes
        if unseen:
            report.add_issue(
                f"Test set contains classes not seen in training: {unseen}. "
                "Model cannot generalize to these classes."
            )

    elif task == "regression":
        train_target = train_df[target_column].drop_nulls().to_numpy()
        test_target = test_df[target_column].drop_nulls().to_numpy()

        if len(train_target) > 0:
            report.stats["train_target_mean"] = float(train_target.mean())
            report.stats["train_target_std"] = float(train_target.std())
        if len(test_target) > 0:
            report.stats["test_target_mean"] = float(test_target.mean())
            report.stats["test_target_std"] = float(test_target.std())

        if len(train_target) > 0 and len(test_target) > 0:
            train_range = (train_target.min(), train_target.max())
            test_range = (test_target.min(), test_target.max())
            if test_range[0] < train_range[0] or test_range[1] > train_range[1]:
                report.add_warning(
                    "Test target range exceeds training range. Model may extrapolate "
                    "outside its training distribution."
                )

    train_ids = set(train_df["sample_id"].to_list()) if "sample_id" in train_df.columns else set()
    test_ids = set(test_df["sample_id"].to_list()) if "sample_id" in test_df.columns else set()
    overlap = train_ids & test_ids
    if overlap:
        report.add_issue(
            f"Data leakage detected: {len(overlap)} samples appear in both "
            f"train and test sets: {list(overlap)[:5]}"
        )

    null_train = sum(train_df[c].null_count() for c in train_df.columns)
    if null_train > 0:
        report.add_warning(
            f"Training set has {null_train} null values across all columns"
        )

    return report
