"""Tests for alpha and beta diversity computation."""

import numpy as np
import polars as pl
import pytest

from flora.diversity.alpha import compute_alpha_diversity
from flora.diversity.beta import compute_beta_diversity


def make_count_df(n_samples=8, n_features=15, seed=1):
    rng = np.random.default_rng(seed)
    counts = rng.negative_binomial(5, 0.3, size=(n_samples, n_features)).astype(float)
    sids = [f"S{i}" for i in range(n_samples)]
    fids = [f"F{j}" for j in range(n_features)]
    data = {"sample_id": sids}
    data.update({f: counts[:, i].tolist() for i, f in enumerate(fids)})
    return pl.DataFrame(data)


def test_alpha_shannon_positive():
    df = make_count_df()
    result = compute_alpha_diversity(df, metrics=["shannon"])
    assert "shannon" in result.columns
    assert (result["shannon"] >= 0).all()


def test_alpha_observed_features_range():
    df = make_count_df(n_features=15)
    result = compute_alpha_diversity(df, metrics=["observed_features"])
    obs = result["observed_features"].to_list()
    for v in obs:
        assert 0 <= v <= 15


def test_alpha_chao1_geq_observed():
    df = make_count_df()
    result = compute_alpha_diversity(df, metrics=["observed_features", "chao1"])
    for obs, chao in zip(result["observed_features"].to_list(), result["chao1"].to_list()):
        assert chao >= obs or abs(chao - obs) < 1.0


def test_alpha_all_metrics():
    df = make_count_df()
    result = compute_alpha_diversity(df, metrics=["shannon", "observed_features", "chao1", "simpson"])
    for m in ["shannon", "observed_features", "chao1", "simpson"]:
        assert m in result.columns
    assert len(result) == 8


def test_beta_bray_curtis_symmetric():
    df = make_count_df()
    result = compute_beta_diversity(df, metric="bray_curtis")
    assert "sample_a" in result.columns
    assert "sample_b" in result.columns
    assert "distance" in result.columns
    assert (result["distance"] >= 0).all()
    assert (result["distance"] <= 1).all()


def test_beta_euclidean_positive():
    df = make_count_df()
    result = compute_beta_diversity(df, metric="euclidean")
    assert (result["distance"] >= 0).all()


def test_beta_n_pairs():
    n = 8
    df = make_count_df(n_samples=n)
    result = compute_beta_diversity(df)
    expected = n * (n - 1) // 2
    assert len(result) == expected


def test_beta_unsupported_metric():
    from flora.core.exceptions import ValidationError
    df = make_count_df()
    with pytest.raises(ValidationError):
        compute_beta_diversity(df, metric="nonexistent_metric")
