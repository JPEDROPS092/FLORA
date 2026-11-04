"""Core statistics: FDR, Kruskal-Wallis, distances, PERMANOVA, PERMDISP, rarefaction.

All functions take plain numpy arrays so they are easy to test and reuse. Permutation tests use an explicit
seed, so a result is reproducible from the report parameters.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from scipy.special import gammaln

DISTANCES = ("bray_curtis", "jaccard", "aitchison", "euclidean")


# ---------------------------------------------------------------------------
# Multiple testing
# ---------------------------------------------------------------------------
def bh_fdr(pvalues: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (q-values), in the input order."""
    p = np.asarray(pvalues, dtype=float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(n)
    q[order] = np.minimum(ranked, 1.0)
    return q.tolist()


# ---------------------------------------------------------------------------
# Alpha diversity tests
# ---------------------------------------------------------------------------
def kruskal_wallis(values: dict[str, list[float]]) -> dict[str, float] | None:
    """Kruskal-Wallis across groups with effect size epsilon². ``None`` when it cannot be computed."""
    groups = [np.asarray(v, dtype=float) for v in values.values() if len(v) >= 1]
    n = sum(len(g) for g in groups)
    if len(groups) < 2 or n - len(groups) < 1 or np.ptp(np.concatenate(groups)) == 0:
        return None
    try:
        res = stats.kruskal(*groups)
    except ValueError:
        return None
    h, p = float(res.statistic), float(res.pvalue)
    if not math.isfinite(p):
        return None
    return {"h": h, "p": p, "epsilon2": max((h - len(groups) + 1) / (n - len(groups)), 0.0), "n": n, "k": len(groups)}


def pairwise_mannwhitney(values: dict[str, list[float]]) -> list[dict]:
    """All group pairs, Mann-Whitney U, BH-adjusted within the family."""
    names = [g for g, v in values.items() if len(v) >= 1]
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = values[names[i]], values[names[j]]
            if np.ptp(np.concatenate([a, b])) == 0:
                continue
            rows.append({"a": names[i], "b": names[j], "u": float(stats.mannwhitneyu(a, b).statistic), "p": float(stats.mannwhitneyu(a, b).pvalue)})
    for row, q in zip(rows, bh_fdr([r["p"] for r in rows]), strict=True):
        row["q"] = q
    return rows


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------
def clr(X: np.ndarray, pseudocount: float = 0.5) -> np.ndarray:
    """Centred log-ratio with a pseudocount (zero replacement), row-wise."""
    L = np.log(np.asarray(X, dtype=float) + pseudocount)
    return L - L.mean(axis=1, keepdims=True)


def distance_matrix(X: np.ndarray, metric: str) -> np.ndarray:
    """Square distance matrix between the rows of a samples x features count matrix."""
    X = np.asarray(X, dtype=float)
    if metric == "bray_curtis":
        totals = X.sum(axis=1, keepdims=True)
        rel = np.divide(X, totals, out=np.zeros_like(X), where=totals > 0)
        return squareform(pdist(rel, "braycurtis"))
    if metric == "jaccard":
        return squareform(pdist(X > 0, "jaccard"))
    if metric == "aitchison":
        return squareform(pdist(clr(X), "euclidean"))
    if metric == "euclidean":
        return squareform(pdist(X, "euclidean"))
    raise ValueError(f"Unsupported distance '{metric}'. Use one of: {', '.join(DISTANCES)}.")


def pcoa(D: np.ndarray, n_components: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Principal coordinates from a distance matrix. Returns (coordinates, eigenvalues of all axes)."""
    n = len(D)
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ (D**2) @ J
    vals, vecs = np.linalg.eigh(B)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    k = min(n_components, int((vals > 1e-10).sum()))
    coords = vecs[:, :k] * np.sqrt(vals[:k])
    return coords, vals


# ---------------------------------------------------------------------------
# PERMANOVA / PERMDISP
# ---------------------------------------------------------------------------
def _encode(groups: Sequence[str]) -> tuple[np.ndarray, list[str]]:
    names = sorted(set(groups))
    index = {g: i for i, g in enumerate(names)}
    return np.array([index[g] for g in groups]), names


def permanova(D: np.ndarray, groups: Sequence[str], permutations: int = 999, seed: int = 42) -> dict:
    """PERMANOVA (Anderson 2001): pseudo-F, R² and a permutation p-value."""
    D = np.asarray(D, dtype=float)
    labels, names = _encode(groups)
    n, a = len(labels), len(names)
    if n != len(D):
        raise ValueError("groups must have one entry per row of the distance matrix")
    if a < 2:
        raise ValueError("PERMANOVA needs at least 2 groups")
    if n - a < 1:
        raise ValueError("PERMANOVA needs more samples than groups")
    D2 = D**2
    ss_total = D2[np.triu_indices(n, 1)].sum() / n

    def pseudo_f(lab: np.ndarray) -> tuple[float, float]:
        H = np.zeros((n, a))
        H[np.arange(n), lab] = 1.0
        sizes = H.sum(axis=0)
        within = np.diag(H.T @ D2 @ H) / 2.0  # sum of d² over pairs inside each group
        ss_within = float((within / np.maximum(sizes, 1)).sum())
        ss_between = ss_total - ss_within
        f = (ss_between / (a - 1)) / (ss_within / (n - a)) if ss_within > 0 else float("inf")
        return f, ss_between / ss_total if ss_total > 0 else 0.0

    f_obs, r2 = pseudo_f(labels)
    rng = np.random.default_rng(seed)
    hits = sum(1 for _ in range(permutations) if pseudo_f(rng.permutation(labels))[0] >= f_obs)
    return {"f": float(f_obs), "r2": float(r2), "p": (hits + 1) / (permutations + 1), "n": n, "groups": names, "permutations": permutations}


def permdisp(D: np.ndarray, groups: Sequence[str], permutations: int = 999, seed: int = 42) -> dict:
    """PERMDISP (Anderson 2006): are group dispersions (distance to the group centroid) different?

    The centroid is computed in PCoA space using the positive and negative axes (as vegan::betadisper does),
    then a one-way ANOVA F on those distances is tested by permuting the group labels.
    """
    D = np.asarray(D, dtype=float)
    labels, names = _encode(groups)
    n, a = len(labels), len(names)
    if a < 2 or n - a < 1:
        raise ValueError("PERMDISP needs at least 2 groups and more samples than groups")
    J = np.eye(n) - np.ones((n, n)) / n
    vals, vecs = np.linalg.eigh(-0.5 * J @ (D**2) @ J)
    pos, neg = vals > 1e-10, vals < -1e-10
    coords = vecs * np.sqrt(np.abs(vals))
    dist_pos = np.zeros(n)
    dist_neg = np.zeros(n)
    for g in range(a):
        idx = labels == g
        centred = coords[idx] - coords[idx].mean(axis=0)
        dist_pos[idx] = (centred[:, pos] ** 2).sum(axis=1)
        dist_neg[idx] = (centred[:, neg] ** 2).sum(axis=1)
    z = np.sqrt(np.abs(dist_pos - dist_neg))

    def anova_f(lab: np.ndarray) -> float:
        groups_z = [z[lab == g] for g in range(a)]
        grand = z.mean()
        ss_b = sum(len(v) * (v.mean() - grand) ** 2 for v in groups_z if len(v))
        ss_w = sum(((v - v.mean()) ** 2).sum() for v in groups_z if len(v))
        return (ss_b / (a - 1)) / (ss_w / (n - a)) if ss_w > 0 else float("inf")

    f_obs = anova_f(labels)
    rng = np.random.default_rng(seed)
    hits = sum(1 for _ in range(permutations) if anova_f(rng.permutation(labels)) >= f_obs)
    return {
        "f": float(f_obs),
        "p": (hits + 1) / (permutations + 1),
        "n": n,
        "permutations": permutations,
        "mean_distance": {names[g]: float(z[labels == g].mean()) for g in range(a)},
    }


# ---------------------------------------------------------------------------
# Rarefaction
# ---------------------------------------------------------------------------
def expected_richness(counts: np.ndarray, depth: int) -> float:
    """Expected number of observed features after subsampling *depth* reads (exact, hypergeometric)."""
    counts = counts[counts > 0].astype(float)
    total = counts.sum()
    if depth <= 0:
        return 0.0
    if depth >= total:
        return float(len(counts))
    n_minus = total - counts
    ok = n_minus >= depth
    miss = np.zeros_like(counts)
    miss[ok] = np.exp(gammaln(n_minus[ok] + 1) + gammaln(total - depth + 1) - gammaln(n_minus[ok] - depth + 1) - gammaln(total + 1))
    return float(len(counts) - miss.sum())


def rarefaction_curve(counts: np.ndarray, points: int = 20, max_depth: int | None = None) -> tuple[list[int], list[float]]:
    """Depths and expected richness for one sample."""
    counts = np.round(np.asarray(counts, dtype=float))
    total = int(counts.sum())
    top = min(total, max_depth) if max_depth else total
    if top < 1:
        return [], []
    depths = sorted({int(round(x)) for x in np.linspace(0, top, points)})
    return depths, [expected_richness(counts, d) for d in depths]
