"""scikit-bio as an external engine: run with the Python of an environment that has it installed.

Standalone (standard library + numpy + scikit-bio only), so FLORA can call it with the interpreter of a connected
conda environment. ``python skbio_bridge.py permanova|unifrac spec.json`` prints one JSON object.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def run(op: str, spec: dict) -> dict:
    import numpy as np

    if op == "permanova":
        from skbio import DistanceMatrix
        from skbio.stats.distance import permanova

        res = permanova(DistanceMatrix(np.array(spec["distances"], dtype=float), spec["ids"]), grouping=spec["groups"], permutations=int(spec.get("permutations", 999)))
        return {"backend": "scikit-bio", "f": float(res["test statistic"]), "p": float(res["p-value"])}
    if op == "unifrac":
        import io

        from skbio import TreeNode
        from skbio.diversity import beta_diversity

        weighted = bool(spec.get("weighted"))
        tree = TreeNode.read(io.StringIO(spec["newick"]))
        counts = np.array(spec["counts"], dtype=int)
        ids = [f"S{i}" for i in range(len(counts))]
        kw = {"normalized": True} if weighted else {}
        metric = "weighted_unifrac" if weighted else "unweighted_unifrac"
        try:  # scikit-bio >= 0.6 calls the feature ids ``taxa``; older releases ``otu_ids``
            dm = beta_diversity(metric, counts, ids, taxa=spec["features"], tree=tree, **kw)
        except (TypeError, ValueError):
            dm = beta_diversity(metric, counts, ids, otu_ids=spec["features"], tree=tree, **kw)
        return {"backend": "scikit-bio", "distances": dm.data.tolist()}
    raise ValueError(f"unknown operation: {op}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python skbio_bridge.py permanova|unifrac spec.json", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(run(sys.argv[1], json.loads(Path(sys.argv[2]).read_text("utf-8")))))
