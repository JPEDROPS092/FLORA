"""Hyperparameter optimization using Optuna (TPE sampler).

Provides a consistent interface for tuning any FLORA classifier or regressor.
Optimal hyperparameters are persisted as JSON and can be passed directly to
model constructors via model_params.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np
import polars as pl
from sklearn.model_selection import StratifiedKFold, cross_val_score

from flora.core.exceptions import MLError

logger = logging.getLogger("flora.ml.optimization")

Task = Literal["classification", "regression"]


@dataclass
class TuningResult:
    """Results from a hyperparameter search.

    Attributes
    ----------
    best_params : dict
        Best hyperparameter combination found.
    best_score : float
        Best cross-validated score (accuracy for classification, R2 for regression).
    n_trials : int
        Number of Optuna trials completed.
    study_name : str
        Optuna study identifier.
    """

    best_params: dict[str, Any]
    best_score: float
    n_trials: int
    study_name: str


class HyperparameterTuner:
    """Optuna-based hyperparameter search for FLORA ML models.

    Parameters
    ----------
    model_type : str
        Model to tune: ``"random_forest"``, ``"xgboost"``, ``"svm"``, or
        ``"ridge"``.
    task : str
        ``"classification"`` or ``"regression"``.
    target_column : str
        Name of the target column in feature DataFrames.
    n_trials : int
        Number of Optuna optimization trials.
    cv_folds : int
        Number of cross-validation folds.
    random_state : int
        Seed for reproducibility.
    output_dir : str or Path, optional
        If provided, save best_params JSON to this directory.

    Examples
    --------
    >>> tuner = HyperparameterTuner("random_forest", task="classification")
    >>> result = tuner.tune(train_df, n_trials=50)
    >>> clf = MicrobiomeClassifier(model_params=result.best_params)
    """

    def __init__(
        self,
        model_type: str = "random_forest",
        task: Task = "classification",
        target_column: str = "label",
        n_trials: int = 50,
        cv_folds: int = 5,
        random_state: int = 42,
        output_dir: str | Path | None = None,
    ) -> None:
        self.model_type = model_type
        self.task = task
        self.target_column = target_column
        self.n_trials = n_trials
        self.cv_folds = cv_folds
        self.random_state = random_state
        self.output_dir = Path(output_dir) if output_dir else None

    def _objective(
        self, trial: Any, X: np.ndarray, y: np.ndarray
    ) -> float:
        params = self._suggest_params(trial)

        estimator = self._build(params)
        if self.task == "classification":
            cv = StratifiedKFold(
                n_splits=self.cv_folds, shuffle=True, random_state=self.random_state
            )
            scores = cross_val_score(estimator, X, y, cv=cv, scoring="f1_macro", n_jobs=-1)
        else:
            from sklearn.model_selection import KFold

            cv = KFold(n_splits=self.cv_folds, shuffle=True, random_state=self.random_state)
            scores = cross_val_score(estimator, X, y, cv=cv, scoring="r2", n_jobs=-1)

        return float(np.mean(scores))

    def _suggest_params(self, trial: Any) -> dict[str, Any]:
        if self.model_type == "random_forest":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 30, log=True),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "max_features": trial.suggest_float("max_features", 0.1, 1.0),
            }
        if self.model_type == "xgboost":
            return {
                "n_estimators": trial.suggest_int("n_estimators", 50, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 12),
                "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.5, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            }
        if self.model_type == "svm":
            return {
                "C": trial.suggest_float("C", 1e-3, 1e3, log=True),
                "gamma": trial.suggest_categorical("gamma", ["scale", "auto"]),
                "kernel": trial.suggest_categorical("kernel", ["rbf", "linear", "poly"]),
            }
        if self.model_type == "ridge":
            return {"alpha": trial.suggest_float("alpha", 1e-3, 1e4, log=True)}
        raise MLError(f"No search space defined for '{self.model_type}'", model=self.model_type)

    def _build(self, params: dict[str, Any]) -> Any:
        if self.model_type == "random_forest":
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

            cls = RandomForestClassifier if self.task == "classification" else RandomForestRegressor
            return cls(random_state=self.random_state, n_jobs=-1, **params)
        if self.model_type == "xgboost":
            try:
                from xgboost import XGBClassifier, XGBRegressor
            except ImportError as exc:
                raise MLError("xgboost required") from exc
            cls = XGBClassifier if self.task == "classification" else XGBRegressor
            extra = {"use_label_encoder": False, "eval_metric": "logloss"} if self.task == "classification" else {}
            return cls(random_state=self.random_state, n_jobs=-1, **params, **extra)
        if self.model_type == "svm":
            from sklearn.svm import SVC, SVR

            cls = SVC if self.task == "classification" else SVR
            prob = {"probability": True} if self.task == "classification" else {}
            p = {k: v for k, v in params.items() if k != "kernel" or cls != SVR}
            return cls(**p, **prob)
        if self.model_type == "ridge":
            from sklearn.linear_model import Ridge

            return Ridge(**params)
        raise MLError(f"Cannot build '{self.model_type}'", model=self.model_type)

    def tune(
        self,
        train_df: pl.DataFrame,
        study_name: str | None = None,
    ) -> TuningResult:
        """Run hyperparameter search.

        Parameters
        ----------
        train_df : polars.DataFrame
            Training data with target column.
        study_name : str, optional
            Optuna study name. Defaults to ``"{model_type}_{task}"``.

        Returns
        -------
        TuningResult
            Best hyperparameters and score.

        Raises
        ------
        ImportError
            If Optuna is not installed.
        MLError
            If tuning fails.
        """
        try:
            import optuna
        except ImportError as exc:
            raise MLError("optuna is required. Install with: pip install optuna") from exc

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        if self.target_column not in train_df.columns:
            raise MLError(
                f"Target column '{self.target_column}' not in DataFrame",
                model=self.model_type,
            )

        feat_cols = [c for c in train_df.columns if c not in ("sample_id", self.target_column)]
        X = train_df.select(feat_cols).to_numpy().astype(np.float64)
        y_raw = train_df[self.target_column].to_list()

        if self.task == "classification":
            from sklearn.preprocessing import LabelEncoder

            le = LabelEncoder()
            y = le.fit_transform(y_raw)
        else:
            y = np.array(y_raw, dtype=np.float64)

        name = study_name or f"{self.model_type}_{self.task}"
        sampler = optuna.samplers.TPESampler(seed=self.random_state)
        study = optuna.create_study(
            study_name=name,
            direction="maximize",
            sampler=sampler,
        )
        study.optimize(
            lambda trial: self._objective(trial, X, y),
            n_trials=self.n_trials,
            show_progress_bar=False,
        )

        best = study.best_params
        best_score = study.best_value

        logger.info(
            "Hyperparameter search complete [%s]: best_score=%.4f trials=%d",
            name, best_score, self.n_trials,
        )

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            out_path = self.output_dir / f"{name}_best_params.json"
            with open(out_path, "w") as fh:
                json.dump({"best_params": best, "best_score": best_score}, fh, indent=2)
            logger.info("Best params saved to %s", out_path)

        return TuningResult(
            best_params=best,
            best_score=best_score,
            n_trials=self.n_trials,
            study_name=name,
        )
