"""Microbiome regression pipeline for diversity index prediction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_validate
from sklearn.svm import SVR

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.regression")

RegressorType = Literal["random_forest", "ridge", "svr", "xgboost"]


@dataclass
class RegressionResult:
    """Results from a regression training run.

    Attributes
    ----------
    model_type : str
        Regressor name.
    rmse : float
        Root mean squared error on the test set.
    r2 : float
        R-squared on the test set.
    cv_scores : dict
        Cross-validation RMSE and R2 arrays.
    model : Any
        Fitted estimator.
    feature_names : list of str
        Feature column names used during training.
    """

    model_type: str
    rmse: float
    r2: float
    cv_scores: dict[str, list[float]]
    model: Any
    feature_names: list[str]


class MicrobiomeRegressor:
    """Regressor for microbiome diversity index prediction.

    Parameters
    ----------
    model : str
        ``"random_forest"``, ``"ridge"``, ``"svr"``, or ``"xgboost"``.
    target_column : str
        Name of the continuous target column.
    random_state : int
        Reproducibility seed.
    n_jobs : int
        Parallelism.
    model_params : dict, optional
        Extra parameters for the estimator.

    Examples
    --------
    >>> reg = MicrobiomeRegressor(model="random_forest", target_column="shannon")
    >>> result = reg.fit(train_df, test_df)
    >>> print(result.r2)
    """

    def __init__(
        self,
        model: RegressorType = "random_forest",
        target_column: str = "shannon",
        random_state: int = 42,
        n_jobs: int = -1,
        model_params: dict[str, Any] | None = None,
    ) -> None:
        self.model_type = model
        self.target_column = target_column
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.model_params = model_params or {}
        self._estimator: Any = None
        self._feature_names: list[str] = []

    def _build_estimator(self) -> Any:
        p = self.model_params
        if self.model_type == "random_forest":
            return RandomForestRegressor(
                n_estimators=p.get("n_estimators", 300),
                max_depth=p.get("max_depth", None),
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
        if self.model_type == "ridge":
            return Ridge(alpha=p.get("alpha", 1.0))
        if self.model_type == "svr":
            return SVR(
                C=p.get("C", 1.0),
                kernel=p.get("kernel", "rbf"),
                gamma=p.get("gamma", "scale"),
            )
        if self.model_type == "xgboost":
            try:
                from xgboost import XGBRegressor
            except ImportError as exc:
                raise MLError("xgboost is required for XGBoost regressor") from exc
            return XGBRegressor(
                n_estimators=p.get("n_estimators", 300),
                max_depth=p.get("max_depth", 6),
                learning_rate=p.get("learning_rate", 0.1),
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
        raise MLError(f"Unknown regressor '{self.model_type}'", model=self.model_type)

    def _split_xy(self, df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
        if self.target_column not in df.columns:
            raise MLError(
                f"Target column '{self.target_column}' not found",
                model=self.model_type,
            )
        feat_cols = [
            c for c in df.columns
            if c not in ("sample_id", self.target_column)
        ]
        X = df.select(feat_cols).to_numpy().astype(np.float64)
        y = df[self.target_column].to_numpy().astype(np.float64)
        return X, y, feat_cols

    def fit(
        self,
        train_df: pl.DataFrame,
        test_df: pl.DataFrame,
        cv_folds: int = 5,
    ) -> RegressionResult:
        """Train and evaluate the regressor.

        Parameters
        ----------
        train_df : polars.DataFrame
            Training data including the target column.
        test_df : polars.DataFrame
            Hold-out test data.
        cv_folds : int
            Number of KFold cross-validation splits.

        Returns
        -------
        RegressionResult
            RMSE, R2, CV scores, and fitted model.
        """
        X_train, y_train, feat_cols = self._split_xy(train_df)
        X_test, y_test, _ = self._split_xy(test_df)
        self._feature_names = feat_cols

        estimator = self._build_estimator()
        cv = KFold(n_splits=cv_folds, shuffle=True, random_state=self.random_state)

        cv_results = cross_validate(
            estimator,
            X_train,
            y_train,
            cv=cv,
            scoring=["r2", "neg_root_mean_squared_error"],
            n_jobs=self.n_jobs,
        )

        estimator.fit(X_train, y_train)
        self._estimator = estimator

        y_pred = estimator.predict(X_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = float(r2_score(y_test, y_pred))

        logger.info(
            "Regression [%s | %s]: RMSE=%.4f R2=%.4f",
            self.model_type, self.target_column, rmse, r2,
        )

        return RegressionResult(
            model_type=self.model_type,
            rmse=rmse,
            r2=r2,
            cv_scores={
                "r2": cv_results["test_r2"].tolist(),
                "rmse": (-cv_results["test_neg_root_mean_squared_error"]).tolist(),
            },
            model=estimator,
            feature_names=feat_cols,
        )
