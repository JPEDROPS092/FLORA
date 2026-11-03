# 3 · Exploration

All views share the same group and normalization filters.

- **PCoA** (Bray–Curtis) — separation between groups.
- **Alpha** — Shannon, Simpson, observed ASVs, Chao1.
- **Beta** — distance heatmap (Bray–Curtis or Jaccard).
- **Taxonomy** — composition by rank and taxonomic tree.
- **Relations** — genus correlation network.

## Differential taxa

Each taxon (phylum or genus) is tested with **Kruskal–Wallis** across groups with at least 2 samples; p-values get **Benjamini–Hochberg** correction (`q`). `log2FC` compares the highest-mean group with the others.

> A low `q` means a **statistical** difference between groups, not a biological cause.
