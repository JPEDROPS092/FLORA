"""Bundled example projects. Public accessions were checked on 2026-11-03."""

from __future__ import annotations

from typing import Any

EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "synthetic-demo",
        "name": "Synthetic Microbiome Demo",
        "question": "Does alpha/beta diversity differ among the four synthetic biomes?",
        "description": (
            "80 samples, 200 ASVs, four biomes, seed 42. Generated offline; not real data."
        ),
        "biome": "synthetic",
        "marker": "16S",
        "synthetic": True,
        "verified": True,
        "installable": True,
        "source": {
            "type": "synthetic",
            "accession": "seed-42",
            "params": {"samples": 80, "features": 200, "seed": 42},
        },
    },
    {
        "id": "amazon-forest-mgnify",
        "name": "Amazon deforestation soil",
        "question": "How does slash-and-burn clearing change Amazonian soil communities?",
        "description": (
            "MGnify MGYS00001352 (PRJEB8643). 18 amplicon samples of forest and "
            "deforested soil in the Brazilian Amazon. Verified 2026-11-03. "
            "Raw files are not an ASV matrix yet."
        ),
        "biome": "root:Environmental:Terrestrial:Soil",
        "marker": "amplicon",
        "synthetic": False,
        "verified": True,
        "installable": True,
        "source": {"type": "mgnify", "accession": "MGYS00001352", "params": {"max_samples": 18}},
    },
    {
        "id": "amazon-sediments-sra",
        "name": "Amazon River lake sediments",
        "question": "How do sediment communities vary among Amazon River lakes?",
        "description": (
            "ENA PRJNA289633 (MGYS00004385). 29 amplicon runs from Amazon River "
            "lake sediments. Verified 2026-11-03. Not a tropical-forest soil study."
        ),
        "biome": "sediment",
        "marker": "amplicon",
        "synthetic": False,
        "verified": True,
        "installable": True,
        "source": {"type": "sra", "accession": "PRJNA289633", "params": {}},
    },
    {
        "id": "ocean-sampling-day",
        "name": "Ocean Sampling Day 2014",
        "question": "What does a single-day global marine survey look like?",
        "description": (
            "PRJEB8682 (secondary ERP009703). 467 runs, amplicon and WGS. "
            "Previously mislabeled here as Amazonian rhizosphere. Verified 2026-11-03. "
            "Not installed automatically because of the archive size."
        ),
        "biome": "marine",
        "marker": "mixed",
        "synthetic": False,
        "verified": True,
        "installable": False,
        "source": {"type": "sra", "accession": "PRJEB8682", "params": {}},
    },
]


def get_example(example_id: str) -> dict[str, Any] | None:
    return next((entry for entry in EXAMPLES if entry["id"] == example_id), None)
