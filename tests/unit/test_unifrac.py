"""UniFrac against hand-computed values."""

from __future__ import annotations

import numpy as np
import pytest

from flora.analysis.unifrac import TreeError, parse_newick, unifrac

TREE = "((A:1,B:1):1,C:2);"
FEATURES = ["A", "B", "C"]
# s1 = {A}, s2 = {B}, s3 = {C}
COUNTS = np.array([[5.0, 0, 0], [0, 3.0, 0], [0, 0, 9.0]])


def test_parse_newick_tips_lengths_and_formats():
    t = parse_newick(TREE)
    assert set(t.tips) == {"A", "B", "C"} and t.size == 5 and t.length.sum() == 5
    q = parse_newick("(('ASV 1':0.1,B:0.2)0.95:0.05,'C''x':0.3)root;")
    assert set(q.tips) == {"ASV 1", "B", "C'x"}
    assert set(parse_newick("((A,B),C);").tips) == {"A", "B", "C"}  # no lengths -> 0


@pytest.mark.parametrize("bad", ["(A,B)", "((A,B);", "(A,B));", "(A:x,B);", "A;", ""])
def test_parse_newick_rejects_malformed(bad):
    with pytest.raises(TreeError):
        parse_newick(bad)


def test_unweighted_unifrac_matches_hand_computation():
    D, missing = unifrac(COUNTS, FEATURES, parse_newick(TREE))
    assert missing == 0
    assert D[0, 1] == pytest.approx(2 / 3) and D[0, 2] == pytest.approx(1.0) and D[1, 2] == pytest.approx(1.0)
    assert np.allclose(D, D.T) and np.allclose(np.diag(D), 0)


def test_weighted_normalized_unifrac_matches_hand_computation():
    D, _ = unifrac(COUNTS, FEATURES, parse_newick(TREE), weighted=True)
    assert D[0, 1] == pytest.approx(0.5) and D[0, 2] == pytest.approx(1.0)


def test_unifrac_ignores_scaling_and_reports_features_missing_from_tree():
    t = parse_newick(TREE)
    a, _ = unifrac(COUNTS, FEATURES, t, weighted=True)
    b, _ = unifrac(COUNTS * 10, FEATURES, t, weighted=True)
    assert np.allclose(a, b)
    wide = np.hstack([COUNTS, np.ones((3, 1))])
    D, missing = unifrac(wide, FEATURES + ["NOT_IN_TREE"], t)
    assert missing == 1 and D.shape == (3, 3)


def test_unifrac_identical_samples_are_zero_and_overlap_is_required():
    t = parse_newick(TREE)
    same = np.array([[1.0, 2, 3], [2.0, 4, 6]])
    assert unifrac(same, FEATURES, t, weighted=True)[0][0, 1] == pytest.approx(0.0)
    with pytest.raises(TreeError):
        unifrac(np.ones((2, 1)), ["X"], t)
