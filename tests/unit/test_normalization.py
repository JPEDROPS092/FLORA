"""Tests for feature engineering normalization functions."""

import numpy as np
import polars as pl
import pytest

from flora.feature_engineering.normalization import (
    clr_transform,
    rarefy,
    suggest_rarefaction_depth,
    tss_transform,
    rarefaction_curve,
)
from flora.core.exceptions import ValidationError


def make_count_df(n_samples=10, n_features=20, seed=42):
    rng = np.random.default_rng(seed)
    counts = rng.negative_binomial(5, 0.3, size=(n_samples, n_features)).astype(float)
    sids = [f"S{i}" for i in range(n_samples)]
    fids = [f"F{j}" for j in range(n_features)]
    data = {"sample_id": sids}
    data.update({f: counts[:, i].tolist() for i, f in enumerate(fids)})
    return pl.DataFrame(data)


def test_tss_rows_sum_to_one():
    df = make_count_df()
    result = tss_transform(df)
    feat_cols = [c for c in result.columns if c != "sample_id"]
    row_sums = result.select(feat_cols).sum_horizontal()
    for s in row_sums.to_list():
        assert abs(s - 1.0) < 1e-9


def test_tss_requires_sample_id():
    df = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    with pytest.raises(ValidationError):
        tss_transform(df)


def test_clr_mean_approximately_zero():
    df = make_count_df()
    result = clr_transform(df)
    feat_cols = [c for c in result.columns if c != "sample_id"]
    X = result.select(feat_cols).to_numpy()
    row_means = X.mean(axis=1)
    for m in row_means:
        assert abs(m) < 1e-8


def test_clr_requires_sample_id():
    df = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    with pytest.raises(ValidationError):
        clr_transform(df)


def test_rarefy_output_depth():
    df = make_count_df()
    feat_cols = [c for c in df.columns if c != "sample_id"]
    min_depth = int(df.select(feat_cols).sum_horizontal().min())
    depth = min_depth - 1 if min_depth > 10 else 10
    rarefied = rarefy(df, depth=depth)
    feat_cols_r = [c for c in rarefied.columns if c != "sample_id"]
    depths = rarefied.select(feat_cols_r).sum_horizontal()
    for d in depths.to_list():
        assert abs(int(d) - depth) < 2


def test_rarefy_drops_low_depth_samples():
    rng = np.random.default_rng(0)
    counts = rng.negative_binomial(5, 0.3, size=(5, 10)).astype(float)
    counts[0] = np.array([1.0] * 10)
    sids = [f"S{i}" for i in range(5)]
    fids = [f"F{j}" for j in range(10)]
    data = {"sample_id": sids}
    data.update({f: counts[:, i].tolist() for i, f in enumerate(fids)})
    df = pl.DataFrame(data)
    depth = 50
    rarefied = rarefy(df, depth=depth)
    assert len(rarefied) < 5


def test_suggest_rarefaction_depth():
    df = make_count_df(n_samples=20, n_features=30)
    depth = suggest_rarefaction_depth(df, target_retention=0.9)
    assert depth > 0


def test_rarefaction_curve_returns_expected_columns():
    df = make_count_df(n_samples=5, n_features=15)
    curve = rarefaction_curve(df, n_iterations=3)
    assert "sample_id" in curve.columns
    assert "depth" in curve.columns
    assert "mean_richness" in curve.columns
    assert "ci_lower" in curve.columns
    assert "ci_upper" in curve.columns
    assert len(curve) > 0
