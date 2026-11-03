# 2 · Normalization

16S counts are **compositional**: the per-sample total reflects sequencing, not biology.

- **Rarefaction** — drops samples below the depth and equalizes the rest.
- **TSS** — divides each count by the sample total (relative abundance).
- **CLR** — centred log-ratio; uses a 0.5 pseudocount, which compresses zeros.
- **Minimum prevalence** — removes ASVs present in few samples.

## Caveats

- CLR on very sparse data can **inflate correlations**.
- Changing rarefaction or transform changes the matrix: **do not compare** results from different settings without recording them.

The chosen parameters are stored in the provenance of experiments and reports.
