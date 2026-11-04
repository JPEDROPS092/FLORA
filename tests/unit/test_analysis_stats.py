"""PERMANOVA / PERMDISP / FDR / rarefaction against known answers."""

from __future__ import annotations

import numpy as np
import pytest

from flora.analysis import stats


def test_bh_fdr_matches_hand_computation_and_is_monotone():
    p = [0.01, 0.04, 0.03, 0.005]
    q = stats.bh_fdr(p)
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02])
    assert all(0 <= v <= 1 for v in q) and stats.bh_fdr([]) == []


def test_kruskal_wallis_separates_groups_and_rejects_degenerate():
    res = stats.kruskal_wallis({"a": [1, 2, 3, 4], "b": [10, 11, 12, 13]})
    assert res and res["p"] < 0.05 and res["epsilon2"] > 0.5
    assert stats.kruskal_wallis({"a": [1, 1], "b": [1, 1]}) is None
    assert stats.kruskal_wallis({"a": [1, 2]}) is None


def _two_clusters(shift: float, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = np.vstack([rng.normal(0, 1, (12, 4)), rng.normal(shift, 1, (12, 4))])
    return stats.distance_matrix(np.abs(X) * 10, "euclidean"), ["a"] * 12 + ["b"] * 12


def test_permanova_detects_separation_and_is_reproducible():
    D, g = _two_clusters(4.0)
    r1, r2 = stats.permanova(D, g, permutations=199, seed=1), stats.permanova(D, g, permutations=199, seed=1)
    assert r1 == r2 and r1["p"] <= 0.01 and r1["r2"] > 0.3
    D0, g0 = _two_clusters(0.0, seed=3)
    assert stats.permanova(D0, g0, permutations=199)["p"] > 0.05


def test_permanova_f_matches_closed_form_for_euclidean():
    # For euclidean distances PERMANOVA's pseudo-F equals the one-way ANOVA F on the centred coordinates.
    rng = np.random.default_rng(5)
    X = np.vstack([rng.normal(0, 1, (6, 2)), rng.normal(2, 1, (6, 2))])
    g = ["a"] * 6 + ["b"] * 6
    D = stats.distance_matrix(X, "euclidean")
    grand = X.mean(axis=0)
    ss_b = sum(6 * ((X[i * 6:(i + 1) * 6].mean(axis=0) - grand) ** 2).sum() for i in range(2))
    ss_w = sum(((X[i * 6:(i + 1) * 6] - X[i * 6:(i + 1) * 6].mean(axis=0)) ** 2).sum() for i in range(2))
    expected = (ss_b / 1) / (ss_w / 10)
    assert stats.permanova(D, g, permutations=9)["f"] == pytest.approx(expected, rel=1e-9)


def test_permanova_input_validation():
    D, g = _two_clusters(1.0)
    with pytest.raises(ValueError):
        stats.permanova(D, ["a"] * 24)
    with pytest.raises(ValueError):
        stats.permanova(D, g[:-1])


def test_permdisp_flags_unequal_dispersion():
    rng = np.random.default_rng(2)
    X = np.vstack([rng.normal(0, 0.3, (15, 3)), rng.normal(0, 3.0, (15, 3))])
    D = stats.distance_matrix(X, "euclidean")
    res = stats.permdisp(D, ["tight"] * 15 + ["wide"] * 15, permutations=199, seed=4)
    assert res["p"] <= 0.01 and res["mean_distance"]["wide"] > res["mean_distance"]["tight"]


def test_distances_are_valid_metrics():
    X = np.array([[5, 0, 1], [4, 1, 1], [0, 9, 0]])
    for metric in ("bray_curtis", "jaccard", "aitchison"):
        D = stats.distance_matrix(X, metric)
        assert D.shape == (3, 3) and np.allclose(D, D.T) and np.allclose(np.diag(D), 0) and (D >= 0).all()
    assert stats.distance_matrix(X, "bray_curtis")[0, 1] < stats.distance_matrix(X, "bray_curtis")[0, 2]
    with pytest.raises(ValueError):
        stats.distance_matrix(X, "unifrac")


def test_expected_richness_is_exact_and_monotone():
    counts = np.array([10, 5, 1, 1, 1])
    assert stats.expected_richness(counts, 0) == 0
    assert stats.expected_richness(counts, 18) == 5  # full depth -> all features
    assert stats.expected_richness(counts, 1) == pytest.approx(1.0)  # one read -> one feature
    # two reads from {A:1,B:1}: expectation is exactly 2 - P(both equal) = 2 - 0 = 2
    assert stats.expected_richness(np.array([1, 1]), 2) == pytest.approx(2.0)
    depths, rich = stats.rarefaction_curve(counts, points=6)
    assert depths[-1] == 18 and rich == sorted(rich) and rich[-1] == 5
    # Monte-Carlo cross-check
    rng = np.random.default_rng(0)
    pool = np.repeat(np.arange(5), counts)
    mc = np.mean([len(set(rng.choice(pool, 6, replace=False))) for _ in range(4000)])
    assert stats.expected_richness(counts, 6) == pytest.approx(mc, abs=0.08)


def test_pcoa_recovers_pairwise_distances():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(8, 3))
    D = stats.distance_matrix(X, "euclidean")
    coords, vals = stats.pcoa(D, 3)
    assert np.allclose(stats.distance_matrix(coords, "euclidean"), D, atol=1e-8)
