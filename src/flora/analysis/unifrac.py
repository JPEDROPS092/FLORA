"""UniFrac (Lozupone & Knight 2005) on a Newick tree, in numpy.

Supports unweighted and weighted-normalized UniFrac. The tree comes from QIIME 2 (``build_tree``) or is uploaded;
its tip names must be the feature ids of the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np


class TreeError(ValueError):
    """The Newick text is not a usable rooted tree."""


@dataclass
class Tree:
    parent: np.ndarray  # parent index per node, -1 for the root
    length: np.ndarray  # branch length above each node (0 for the root)
    tips: dict[str, int]  # tip name -> node index
    order: np.ndarray  # node indices, children before parents

    @property
    def size(self) -> int:
        return len(self.parent)


_TOKEN = re.compile(r"\s*(?:'((?:[^']|'')*)'|([^,:;()\[\]\s]+))")


def parse_newick(text: str) -> Tree:
    """Parse Newick into parent/length arrays. Internal labels (support values) are ignored."""
    text = re.sub(r"\[[^\]]*\]", "", text or "").strip()
    if not text.endswith(";"):
        raise TreeError("O Newick precisa terminar com ';'.")
    parent: list[int] = []
    length: list[float] = []
    names: list[str] = []
    stack: list[int] = []
    i, n = 0, len(text) - 1
    current = -1  # node whose label/length is being read

    def new_node() -> int:
        parent.append(stack[-1] if stack else -1)
        length.append(0.0)
        names.append("")
        return len(parent) - 1

    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "(":
            stack.append(new_node())
            current = -1
            i += 1
        elif c == ",":
            current = -1
            i += 1
        elif c == ")":
            if not stack:
                raise TreeError("Parênteses desbalanceados.")
            current = stack.pop()
            i += 1
        elif c == ":":
            m = re.compile(r"\s*:\s*([-+0-9.eE]+)").match(text, i)
            if not m or current < 0:
                raise TreeError("Comprimento de ramo inválido.")
            length[current] = float(m.group(1))
            i = m.end()
        else:
            m = _TOKEN.match(text, i)
            if not m:
                raise TreeError(f"Rótulo inválido perto da posição {i}.")
            label = (m.group(1) or m.group(2) or "").replace("''", "'")
            if current < 0:  # a leaf
                current = new_node()
            names[current] = label
            i = m.end()
    if stack:
        raise TreeError("Parênteses desbalanceados.")
    if not parent:
        raise TreeError("Árvore vazia.")
    par = np.array(parent)
    if (par < 0).sum() != 1:
        raise TreeError("A árvore precisa ter uma única raiz.")
    has_child = np.zeros(len(par), dtype=bool)
    has_child[par[par >= 0]] = True
    tips = {names[k]: k for k in range(len(par)) if not has_child[k] and names[k]}
    if len(tips) < 2:
        raise TreeError("A árvore precisa de ao menos 2 pontas nomeadas.")
    lens = np.array(length)
    if (lens < 0).any():
        raise TreeError("Há comprimentos de ramo negativos.")
    # children come before parents when nodes are visited by decreasing depth
    depth = np.zeros(len(par), dtype=int)
    for k in range(len(par)):
        d, p = 0, par[k]
        while p >= 0:
            d, p = d + 1, par[p]
        depth[k] = d
    return Tree(par, lens, tips, np.argsort(-depth, kind="stable"))


def _node_matrix(tree: Tree, counts: np.ndarray, feature_ids: list[str]) -> tuple[np.ndarray, int]:
    """nodes x samples abundance of every node's descendant tips. Also returns the number of features not in the tree."""
    node = np.zeros((tree.size, counts.shape[0]))
    missing = 0
    for j, fid in enumerate(feature_ids):
        k = tree.tips.get(fid)
        if k is None:
            missing += 1
            continue
        node[k] += counts[:, j]
    for k in tree.order:
        p = tree.parent[k]
        if p >= 0:
            node[p] += node[k]
    return node, missing


def unifrac(counts: np.ndarray, feature_ids: list[str], tree: Tree, weighted: bool = False) -> tuple[np.ndarray, int]:
    """Distance matrix between samples (rows of *counts*) and the number of features missing from the tree."""
    counts = np.asarray(counts, dtype=float)
    node, missing = _node_matrix(tree, counts, feature_ids)
    totals = node[int(np.where(tree.parent < 0)[0][0])]
    if (totals <= 0).any():
        raise TreeError("Há amostras sem nenhuma feature presente na árvore.")
    L = tree.length
    m = counts.shape[0]
    if not weighted:
        P = (node > 0).astype(float)
        W = P.T @ (L[:, None] * P)
        d = np.diag(W)
        denom = d[:, None] + d[None, :] - W
        D = np.divide(d[:, None] + d[None, :] - 2 * W, denom, out=np.zeros((m, m)), where=denom > 0)
    else:
        rel = node / totals
        # distance from the root to every tip, to normalise
        root_dist = np.zeros(tree.size)
        for k in tree.order[::-1]:
            p = tree.parent[k]
            if p >= 0:
                root_dist[k] = root_dist[p] + L[k]
        tip_idx = np.array(sorted(tree.tips.values()))
        D = np.zeros((m, m))
        for i in range(m):
            num = (np.abs(rel[:, [i]] - rel) * L[:, None]).sum(axis=0)
            den = (root_dist[tip_idx][:, None] * (rel[tip_idx, i][:, None] + rel[tip_idx])).sum(axis=0)
            D[i] = np.divide(num, den, out=np.zeros(m), where=den > 0)
        D = (D + D.T) / 2
    np.fill_diagonal(D, 0.0)
    return D, missing
