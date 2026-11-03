"""Local synthetic cohort used by the download API and the library."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def write_synthetic(
    output_dir: str | Path,
    *,
    samples: int = 80,
    features: int = 200,
    seed: int = 42,
) -> dict[str, Path]:
    """Write metadata, a wide ASV table and a taxonomy TSV. Not real data."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    sample_ids = [f"S{i:03d}" for i in range(samples)]
    feature_ids = [f"ASV_{j:04d}" for j in range(features)]
    biomes = (["Amazon", "Cerrado", "Atlantic_Forest", "Pantanal"] * (samples // 4 + 1))[:samples]
    counts = rng.negative_binomial(n=5, p=0.3, size=(samples, features)).astype(int)

    metadata_path = out / "metadata.tsv"
    with metadata_path.open("w", encoding="utf-8") as handle:
        handle.write("sample_id\tbiome\tlocation\n")
        for index, sample_id in enumerate(sample_ids):
            handle.write(f"{sample_id}\t{biomes[index]}\tBrazil\n")

    asv_path = out / "asv_table.tsv"
    with asv_path.open("w", encoding="utf-8") as handle:
        handle.write("sample_id\t" + "\t".join(feature_ids) + "\n")
        for index, sample_id in enumerate(sample_ids):
            handle.write(sample_id + "\t" + "\t".join(map(str, counts[index])) + "\n")

    phyla = ["Proteobacteria", "Firmicutes", "Bacteroidetes", "Actinobacteria", "Chloroflexi"]
    taxonomy_path = out / "taxonomy.tsv"
    with taxonomy_path.open("w", encoding="utf-8") as handle:
        handle.write("feature_id\tkingdom\tphylum\tclass\torder\tfamily\tgenus\tspecies\n")
        for index, feature_id in enumerate(feature_ids):
            handle.write(
                f"{feature_id}\tBacteria\t{phyla[index % len(phyla)]}\t"
                f"Class_{index % 6}\tOrder_{index % 8}\tFamily_{index % 10}\tGenus_{index % 15}\t\n"
            )
    return {"asv_table": asv_path, "taxonomy": taxonomy_path, "metadata": metadata_path}


def preview_synthetic(limit: int = 50, samples: int = 80) -> list[dict[str, str]]:
    """First rows of the synthetic metadata, without writing the count matrix."""
    biomes = (["Amazon", "Cerrado", "Atlantic_Forest", "Pantanal"] * (samples // 4 + 1))[:samples]
    rows = [
        {"sample_id": f"S{i:03d}", "biome": biomes[i], "location": "Brazil"}
        for i in range(min(limit, samples))
    ]
    return rows
