"""Microbiome classification pipeline.

Supports Random Forest, SVM, and XGBoost classifiers with stratified
cross-validation and MLflow tracking. The interface is consistent with
MicrobiomeRegressor to allow swapping estimators without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.classification")

ModelType = Literal["random_forest", "svm", "xgboost"]


@dataclass
class ClassificationResult:
    """Results from a classification training run.

    Attributes
    ----------
    model_type : str
        Name of the classifier used.
    accuracy : float
        Mean cross-validated accuracy.
    f1_macro : float
        Mean cross-validated macro-averaged F1.
    roc_auc : float or None
        Mean cross-validated ROC-AUC (None for multiclass without probability).
    cv_scores : dict
        Raw cross-validation score arrays per metric.
    classification_report : str
        Full sklearn classification report on the held-out test set.
    feature_importances : polars.DataFrame or None
        Feature importance table (available for tree-based models).
    model : Any
        Fitted estimator.
    label_encoder : LabelEncoder
        Fitted label encoder used during training.
    """

    model_type: str
    accuracy: float
    f1_macro: float
    roc_auc: float | None
    cv_scores: dict[str, list[float]]
    classification_report_str: str
    feature_importances: pl.DataFrame | None
    model: Any
    label_encoder: LabelEncoder
    feature_names: list[str] = field(default_factory=list)


class MicrobiomeClassifier:
    """Microbiome sample classifier with cross-validation and MLflow tracking.

    Parameters
    ----------
    model : str
        Estimator type: ``"random_forest"``, ``"svm"``, or ``"xgboost"``.
    target_column : str
        Name of the label column in the feature DataFrames.
    test_size : float
        Fraction of samples to reserve as hold-out test set.
    stratify : bool
        Use stratified splitting.
    random_state : int
        Global random seed.
    n_jobs : int
        Parallelism for training and cross-validation.
    mlflow_tracking_uri : str or None
        MLflow tracking URI. If None, MLflow tracking is disabled.
    model_params : dict, optional
        Additional keyword arguments forwarded to the estimator constructor.

    Examples
    --------
    >>> clf = MicrobiomeClassifier(model="random_forest", target_column="biome")
    >>> result = clf.fit(train_df, test_df, cv_folds=5)
    >>> print(result.f1_macro)
    """

    def __init__(
        self,
        model: ModelType = "random_forest",
        target_column: str = "label",
        stratify: bool = True,
        random_state: int = 42,
        n_jobs: int = -1,
        mlflow_tracking_uri: str | None = None,
        model_params: dict[str, Any] | None = None,
    ) -> None:
        self.model_type = model
        self.target_column = target_column
        self.stratify = stratify
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.mlflow_tracking_uri = mlflow_tracking_uri
        self.model_params = model_params or {}
        self._estimator: Any = None
        self._label_encoder = LabelEncoder()
        self._feature_names: list[str] = []

    def _build_estimator(self) -> Any:
        params = self.model_params
        if self.model_type == "random_forest":
            return RandomForestClassifier(
                n_estimators=params.get("n_estimators", 300),
                max_depth=params.get("max_depth", None),
                min_samples_split=params.get("min_samples_split", 2),
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
        if self.model_type == "svm":
            return SVC(
                C=params.get("C", 1.0),
                kernel=params.get("kernel", "rbf"),
                gamma=params.get("gamma", "scale"),
                probability=True,
                random_state=self.random_state,
            )
        if self.model_type == "xgboost":
            try:
                from xgboost import XGBClassifier
            except ImportError as exc:
                raise MLError("xgboost must be installed for XGBoost classifier") from exc
            return XGBClassifier(
                n_estimators=params.get("n_estimators", 300),
                max_depth=params.get("max_depth", 6),
                learning_rate=params.get("learning_rate", 0.1),
                subsample=params.get("subsample", 0.8),
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
        raise MLError(
            f"Unknown model type '{self.model_type}'",
            model=self.model_type,
        )

    def _split_xy(
        self, df: pl.DataFrame
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        if self.target_column not in df.columns:
            raise MLError(
                f"Target column '{self.target_column}' not found in DataFrame",
                model=self.model_type,
            )
        feature_cols = [
            c for c in df.columns
            if c not in ("sample_id", self.target_column)
        ]
        X = df.select(feature_cols).to_numpy().astype(np.float64)
        y_raw = df[self.target_column].to_list()
        return X, y_raw, feature_cols

    def fit(
        self,
        train_df: pl.DataFrame,
        test_df: pl.DataFrame,
        cv_folds: int = 5,
        run_name: str | None = None,
    ) -> ClassificationResult:
        """Train the classifier with cross-validation.

        Parameters
        ----------
        train_df : polars.DataFrame
            Training data. Must contain the target column.
        test_df : polars.DataFrame
            Hold-out test data.
        cv_folds : int
            Number of stratified cross-validation folds.
        run_name : str, optional
            MLflow run name.

        Returns
        -------
        ClassificationResult
            Contains metrics, model, and feature importances.

        Raises
        ------
        MLError
            If training fails.
        """
        X_train, y_train_raw, feature_cols = self._split_xy(train_df)
        X_test, y_test_raw, _ = self._split_xy(test_df)

        all_labels = y_train_raw + y_test_raw
        self._label_encoder.fit(all_labels)
        y_train = self._label_encoder.transform(y_train_raw)
        y_test = self._label_encoder.transform(y_test_raw)
        self._feature_names = feature_cols

        estimator = self._build_estimator()

        cv = StratifiedKFold(
            n_splits=cv_folds,
            shuffle=True,
            random_state=self.random_state,
        )
        scoring = ["accuracy", "f1_macro"]
        try:
            cv_results = cross_validate(
                estimator,
                X_train,
                y_train,
                cv=cv,
                scoring=scoring,
                n_jobs=self.n_jobs,
            )
        except Exception as exc:
            raise MLError(
                f"Cross-validation failed: {exc}",
                model=self.model_type,
            ) from exc

        estimator.fit(X_train, y_train)
        self._estimator = estimator

        y_pred = estimator.predict(X_test)
        test_accuracy = float(accuracy_score(y_test, y_pred))
        test_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))

        roc_auc = None
        if hasattr(estimator, "predict_proba"):
            try:
                y_proba = estimator.predict_proba(X_test)
                n_classes = len(self._label_encoder.classes_)
                if n_classes == 2:
                    roc_auc = float(roc_auc_score(y_test, y_proba[:, 1]))
                else:
                    roc_auc = float(
                        roc_auc_score(y_test, y_proba, multi_class="ovr", average="macro")
                    )
            except Exception:
                pass

        report_str = classification_report(
            y_test,
            y_pred,
            target_names=self._label_encoder.classes_,
            zero_division=0,
        )

        importances_df = self._extract_importances()

        cv_scores = {
            "accuracy": cv_results["test_accuracy"].tolist(),
            "f1_macro": cv_results["test_f1_macro"].tolist(),
        }

        result = ClassificationResult(
            model_type=self.model_type,
            accuracy=test_accuracy,
            f1_macro=test_f1,
            roc_auc=roc_auc,
            cv_scores=cv_scores,
            classification_report_str=report_str,
            feature_importances=importances_df,
            model=estimator,
            label_encoder=self._label_encoder,
            feature_names=feature_cols,
        )

        self._maybe_log_mlflow(result, run_name)

        logger.info(
            "Classification [%s]: accuracy=%.4f f1_macro=%.4f roc_auc=%s",
            self.model_type,
            test_accuracy,
            test_f1,
            f"{roc_auc:.4f}" if roc_auc else "N/A",
        )
        return result

    def predict(self, df: pl.DataFrame) -> np.ndarray:
        """Predict class labels for new samples.

        Parameters
        ----------
        df : polars.DataFrame
            Feature matrix. Column order must match training data.

        Returns
        -------
        numpy.ndarray
            Decoded class label array.
        """
        if self._estimator is None:
            raise MLError("Model has not been fitted. Call fit() first.", model=self.model_type)
        feature_cols = [c for c in df.columns if c not in ("sample_id", self.target_column)]
        X = df.select(feature_cols).to_numpy().astype(np.float64)
        encoded = self._estimator.predict(X)
        return self._label_encoder.inverse_transform(encoded)

    def _extract_importances(self) -> pl.DataFrame | None:
        if self._estimator is None:
            return None
        if not hasattr(self._estimator, "feature_importances_"):
            return None
        return pl.DataFrame({
            "feature": self._feature_names,
            "importance": self._estimator.feature_importances_.tolist(),
        }).sort("importance", descending=True)

    def _maybe_log_mlflow(
        self, result: ClassificationResult, run_name: str | None
    ) -> None:
        if self.mlflow_tracking_uri is None:
            return
        try:
            import mlflow

            mlflow.set_tracking_uri(self.mlflow_tracking_uri)
            with mlflow.start_run(run_name=run_name or f"flora_{self.model_type}"):
                mlflow.log_params({
                    "model_type": self.model_type,
                    "random_state": self.random_state,
                    **self.model_params,
                })
                mlflow.log_metrics({
                    "accuracy": result.accuracy,
                    "f1_macro": result.f1_macro,
                    "roc_auc": result.roc_auc or 0.0,
                    "cv_accuracy_mean": float(np.mean(result.cv_scores["accuracy"])),
                    "cv_f1_macro_mean": float(np.mean(result.cv_scores["f1_macro"])),
                })
                mlflow.sklearn.log_model(result.model, "model")
        except Exception as exc:
            logger.warning("MLflow logging failed: %s", exc)
