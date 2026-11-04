"""Load and filter the curated dataset catalog.

Entries live in ``catalog_data/datasets.yaml`` so accession, counts and labels
are data, not constants in Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent / "catalog_data"
_SOURCES = {"mgnify", "ena", "emp", "url", "synthetic"}
_SEQ_TYPES = {"amplicon", "WGS", "misto"}
_REQUIRED = (
    "id",
    "title",
    "title_pt",
    "description",
    "source",
    "accession",
    "biome",
    "host",
    "region",
    "n_samples",
    "seq_type",
    "verified_at",
    "importable",
    "download_note",
)

Entry = dict[str, Any]


class CatalogError(ValueError):
    """The catalog file is missing a field or breaks a rule."""


def _validate(entry: Any, label: str) -> Entry:
    if not isinstance(entry, dict):
        raise CatalogError(f"{label} is not a mapping")
    missing = [key for key in _REQUIRED if key not in entry or entry[key] in (None, "")]
    if missing:
        raise CatalogError(f"{label} missing {', '.join(missing)}")
    if entry["source"] not in _SOURCES:
        raise CatalogError(f"{label} has unknown source {entry['source']!r}")
    if entry["seq_type"] not in _SEQ_TYPES:
        raise CatalogError(f"{label} has unknown seq_type {entry['seq_type']!r}")
    if int(entry["n_samples"]) < 0:
        raise CatalogError(f"{label} has a negative n_samples")
    highlight = entry.get("highlight") or ""
    if highlight not in ("", "amazonia"):
        raise CatalogError(f"{label} has unknown highlight {highlight!r}")
    entry["highlight"] = highlight
    entry["n_samples"] = int(entry["n_samples"])
    entry["description"] = " ".join(str(entry["description"]).split())
    entry["download_note"] = " ".join(str(entry["download_note"]).split())
    entry.setdefault("files", [])
    entry.setdefault("tags", [])
    return entry


@lru_cache(maxsize=4)
def _load_cached(directory: str) -> tuple[Entry, ...]:
    path = Path(directory)
    files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
    if not files:
        raise CatalogError(f"No catalog YAML in {path}")
    entries: list[Entry] = []
    seen_id: set[str] = set()
    seen_acc: set[tuple[str, str]] = set()
    for file in files:
        loaded = yaml.safe_load(file.read_text(encoding="utf-8"))
        rows = loaded if isinstance(loaded, list) else [loaded]
        for index, raw in enumerate(rows):
            entry = _validate(raw, f"{file.name}[{index}]")
            if entry["id"] in seen_id:
                raise CatalogError(f"Duplicate catalog id {entry['id']}")
            key = (entry["source"], entry["accession"])
            if key in seen_acc:
                raise CatalogError(f"Duplicate accession {key[1]} for {key[0]}")
            seen_id.add(entry["id"])
            seen_acc.add(key)
            entries.append(entry)
    return tuple(entries)


def load_catalog(directory: Path | None = None) -> list[Entry]:
    """Return catalog entries. Each call returns a fresh list of dict copies."""
    folder = Path(directory) if directory else CATALOG_DIR
    return [dict(item) for item in _load_cached(str(folder.resolve()))]


def get_entry(source: str, accession: str, directory: Path | None = None) -> Entry | None:
    for entry in load_catalog(directory):
        if entry["source"] == source and entry["accession"] == accession:
            return entry
    return None


def filter_catalog(
    entries: list[Entry] | None = None,
    *,
    q: str = "",
    biome: str = "",
    host: str = "",
    region: str = "",
    seq_type: str = "",
    amazonia: bool = False,
) -> list[Entry]:
    """Filter by biome, host, region, sequence type, Amazônia highlight and free text."""
    rows = list(entries) if entries is not None else load_catalog()
    needle = " ".join((q or "").lower().split())
    out: list[Entry] = []
    for entry in rows:
        if biome and entry.get("biome") != biome:
            continue
        if host and entry.get("host") != host:
            continue
        if region and entry.get("region") != region:
            continue
        if seq_type and entry.get("seq_type") != seq_type:
            continue
        if amazonia and entry.get("highlight") != "amazonia":
            continue
        if needle:
            blob = " ".join(
                str(entry.get(key) or "")
                for key in (
                    "id",
                    "title",
                    "title_pt",
                    "description",
                    "accession",
                    "bioproject",
                    "secondary",
                    "country",
                    "centre",
                    "region_label",
                    "biome_label",
                    "marker",
                    "marker_region",
                )
            )
            blob = f"{blob} {' '.join(entry.get('tags') or [])}".lower()
            if needle not in blob and not all(part in blob for part in needle.split()):
                continue
        out.append(entry)
    return out


def as_study(entry: Entry) -> dict[str, Any]:
    """Project a catalog entry onto the study shape used by the older search API."""
    return {
        "source": entry["source"],
        "accession": entry["accession"],
        "title": entry["title"],
        "title_pt": entry.get("title_pt") or entry["title"],
        "description": entry.get("description") or "",
        "biome": entry.get("biome_label") or entry.get("biome") or "",
        "samples": int(entry.get("n_samples") or 0),
        "centre": entry.get("centre") or "",
        "bioproject": entry.get("bioproject") or "",
        "secondary": entry.get("secondary") or "",
        "updated": entry.get("verified_at") or "",
        "url": entry.get("url") or "",
        "origin": "curated",
        "importable": bool(entry.get("importable", True)),
        "region_label": entry.get("region_label") or "",
        "highlight": entry.get("highlight") or "",
    }
