# 3 · Exploração

Todas as vistas usam os mesmos filtros de grupo e normalização.

- **PCoA** (Bray–Curtis) — separação entre grupos.
- **Alfa** — Shannon, Simpson, ASVs observados, Chao1.
- **Beta** — mapa de calor de distâncias (Bray–Curtis ou Jaccard).
- **Taxonomia** — composição por nível e árvore taxonômica.
- **Relações** — rede de correlação entre gêneros.

## Táxons diferenciais

Para cada táxon (filo ou gênero) aplica-se **Kruskal–Wallis** entre os grupos com ao menos 2 amostras; os p-valores recebem correção **Benjamini–Hochberg** (`q`). O `log2FC` compara o grupo de maior média com os demais.

> Um `q` baixo indica diferença **estatística** entre grupos, não causa biológica.
