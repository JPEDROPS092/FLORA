"""Bundled example projects. Public studies are templates until verified at the source."""

from __future__ import annotations

from typing import Any

EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "synthetic-demo",
        "name": "Synthetic Microbiome Demo",
        "question": "Does alpha/beta diversity differ among the four synthetic biomes?",
        "description": "80 samples, 200 ASVs, four biomes, seed 42. Generated offline; not real data.",
        "biome": "synthetic", "marker": "16S", "synthetic": True, "verified": True, "installable": True,
        "source": {"type": "synthetic", "accession": "seed-42", "params": {"samples": 80, "features": 200, "seed": 42}},
    },
    {
        "id": "amazon-forest-mgnify",
        "name": "Amazonian Forest Microbiome",
        "question": "Which taxa characterise Amazonian forest soil communities?",
        "description": "MGnify study template. Downloads raw files; an ASV matrix still has to be produced.",
        "biome": "root:Environmental:Terrestrial:Soil", "marker": "16S", "synthetic": False, "verified": False, "installable": True,
        "source": {"type": "mgnify", "accession": "MGYS00005116", "params": {"max_samples": 20}},
    },
    {
        "id": "tropical-soil-sra",
        "name": "Brazilian Tropical Soil",
        "question": "How does tropical soil composition vary across sites?",
        "description": "NCBI SRA template. Downloads FASTQ; needs processing before analysis.",
        "biome": "soil", "marker": "16S", "synthetic": False, "verified": False, "installable": True,
        "source": {"type": "sra", "accession": "SRP151124", "params": {}},
    },
    {
        "id": "amazon-rhizosphere",
        "name": "Amazonian Rhizosphere",
        "question": "How do rhizosphere communities differ from bulk soil?",
        "description": "Template: the accession (ERP009703) has to be confirmed at the source before importing.",
        "biome": "rhizosphere", "marker": "16S", "synthetic": False, "verified": False, "installable": False,
        "source": {"type": "mgnify", "accession": "ERP009703", "params": {}},
    },
]


def get_example(example_id: str) -> dict[str, Any] | None:
    return next((e for e in EXAMPLES if e["id"] == example_id), None)
