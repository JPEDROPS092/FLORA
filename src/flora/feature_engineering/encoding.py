"""Metadata encoding for microbiome ML pipelines.

Converts categorical and ordinal sample metadata columns into numeric
representations compatible with scikit-learn estimators.
"""

from __future__ import annotations

import logging
from typing import Literal

import polars as pl
from sklearn.preprocessing import LabelEncoder, OrdinalEncoder

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.feature_engineering.encoding")

EncodingStrategy = Literal["onehot", "ordinal", "label", "target"]


def encode_metadata(
    metadata_df: pl.DataFrame,
    columns: list[str],
    strategy: EncodingStrategy = "onehot",
    target_col: str | None = None,
    ordinal_categories: dict[str, list[str]] | None = None,
    drop_original: bool = True,
) -> pl.DataFrame:
    """Encode categorical metadata columns for ML use.

    Parameters
    ----------
    metadata_df : polars.DataFrame
        Metadata table. Must contain ``sample_id`` and all columns listed
        in ``columns``.
    columns : list of str
        Names of categorical columns to encode.
    strategy : str
        Encoding method:
        - ``"onehot"``: binary indicator columns per category
        - ``"ordinal"``: integer codes in user-defined order
        - ``"label"``: integer codes (arbitrary order, for tree models)
        - ``"target"``: mean target encoding (requires ``target_col``)
    target_col : str, optional
        Column name for target variable, required when ``strategy="target"``.
    ordinal_categories : dict of {str: list of str}, optional
        For ``strategy="ordinal"``, the ordered categories per column.
        Example: ``{"severity": ["low", "medium", "high"]}``.
    drop_original : bool
        If True, remove original categorical columns after encoding.

    Returns
    -------
    polars.DataFrame
        Metadata table with encoded columns added (and originals optionally
        removed).

    Raises
    ------
    ValidationError
        If required columns are missing.
    ValueError
        If an unsupported strategy is specified or target_col is missing for
        target encoding.
    """
    if "sample_id" not in metadata_df.columns:
        raise ValidationError("metadata_df must have a 'sample_id' column", field="sample_id")

    missing = set(columns) - set(metadata_df.columns)
    if missing:
        raise ValidationError(
            f"Columns not found in metadata: {missing}",
            context={"available_columns": metadata_df.columns},
        )

    df = metadata_df.clone()
    encoded_cols: list[str] = []

    for col in columns:
        values = df[col].fill_null("__missing__").to_list()

        if strategy == "onehot":
            unique_cats = sorted(set(v for v in values if v != "__missing__"))
            for cat in unique_cats:
                safe_name = f"{col}__{cat}".replace(" ", "_").replace("-", "_")
                df = df.with_columns(
                    pl.Series(safe_name, [1.0 if v == cat else 0.0 for v in values])
                )
                encoded_cols.append(safe_name)

        elif strategy == "label":
            le = LabelEncoder()
            codes = le.fit_transform(values)
            out_col = f"{col}__label"
            df = df.with_columns(pl.Series(out_col, codes.astype(float)))
            encoded_cols.append(out_col)

        elif strategy == "ordinal":
            if ordinal_categories is None or col not in ordinal_categories:
                raise ValueError(
                    f"ordinal_categories must be provided for column '{col}' "
                    f"when strategy='ordinal'"
                )
            cats = ordinal_categories[col]
            cat_map = {c: i for i, c in enumerate(cats)}
            codes = [float(cat_map.get(v, -1)) for v in values]
            out_col = f"{col}__ordinal"
            df = df.with_columns(pl.Series(out_col, codes))
            encoded_cols.append(out_col)

        elif strategy == "target":
            if target_col is None:
                raise ValueError("target_col is required for target encoding")
            if target_col not in df.columns:
                raise ValidationError(f"target_col '{target_col}' not in DataFrame", field=target_col)

            target_vals = df[target_col].to_list()
            cat_means: dict[str, float] = {}
            cat_counts: dict[str, list] = {}
            for v, t in zip(values, target_vals):
                cat_counts.setdefault(v, []).append(t)
            global_mean = float(np.mean([t for t in target_vals if t is not None]))

            for cat, tvals in cat_counts.items():
                try:
                    cat_means[cat] = float(np.mean([float(x) for x in tvals if x is not None]))
                except (TypeError, ValueError):
                    cat_means[cat] = global_mean

            out_col = f"{col}__target"
            encoded = [cat_means.get(v, global_mean) for v in values]
            df = df.with_columns(pl.Series(out_col, encoded))
            encoded_cols.append(out_col)

        else:
            raise ValueError(
                f"Unknown encoding strategy '{strategy}'. "
                f"Choose from: onehot, ordinal, label, target"
            )

        if drop_original:
            df = df.drop(col)

    logger.info(
        "Encoded %d columns using '%s' strategy, added %d columns",
        len(columns), strategy, len(encoded_cols),
    )
    return df


# numpy is needed for target encoding — import at module level to keep it explicit
import numpy as np  # noqa: E402
