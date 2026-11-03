"""Study library: discover public studies (and their accession codes) before downloading.

Two kinds of entries share one shape (:data:`Study`):

* **curated** — studies already referenced by FLORA itself (README, examples); no network needed;
* **live** — searched on MGnify (EBI) and ENA Portal APIs, both public and key-less.

Nothing here downloads data; it only lists what exists so the user can pick a code.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

logger = logging.getLogger("flora.io.library")

Study = dict[str, Any]

_MGNIFY = "https://www.ebi.ac.uk/metagenomics/api/v1/studies"
_ENA = "https://www.ebi.ac.uk/ena/portal/api"
_TIMEOUT = 25
_SAFE_QUERY = re.compile(r"[^\w\s.\-:]", re.UNICODE)
_ACCESSION = re.compile(r"^[A-Za-z]{2,6}\d{3,}$")

SOURCES = ("curated", "mgnify", "ena")

# Studies already named in FLORA's own docs/examples. Titles are descriptive labels, not fetched metadata.
CURATED: list[Study] = [
    {
        "source": "synthetic",
        "accession": "SYNTHETIC",
        "title": "Synthetic cohort",
        "description": "Generated locally with a seed; four Brazilian biomes. No internet, not real data.",
        "biome": "Synthetic",
        "samples": 80,
        "centre": "FLORA",
        "url": "",
        "origin": "curated",
        "importable": True,
    },
    {
        "source": "emp",
        "accession": "EMP-R1",
        "title": "Earth Microbiome Project — Release 1",
        "description": "Standardised global sampling; Deblur 150 bp tables and metadata (Thompson et al. 2017, Nature 551).",
        "biome": "Global",
        "samples": 2000,
        "centre": "EMP · Qiita / UCSD",
        "url": "https://doi.org/10.5281/zenodo.890000",
        "origin": "curated",
        "importable": True,
    },
    {
        "source": "mgnify",
        "accession": "MGYS00005116",
        "title": "Amazonian forest soil (MGnify)",
        "description": "Template study referenced by FLORA. Not re-verified against the source on every release.",
        "biome": "Amazonian Forest",
        "samples": 80,
        "centre": "MGnify",
        "url": "https://www.ebi.ac.uk/metagenomics/studies/MGYS00005116",
        "origin": "curated",
        "importable": True,
    },
    {
        "source": "ena",
        "accession": "SRP151124",
        "title": "Brazilian tropical soil (NCBI SRA)",
        "description": "Template study referenced by FLORA. Raw FASTQ; needs processing before analysis.",
        "biome": "Brazilian Tropical Soil",
        "samples": 60,
        "centre": "NCBI SRA",
        "url": "https://www.ncbi.nlm.nih.gov/sra/?term=SRP151124",
        "origin": "curated",
        "importable": True,
    },
    {
        "source": "ena",
        "accession": "ERP009703",
        "title": "Amazonian rhizosphere",
        "description": "Template study referenced by FLORA (ENA secondary accession).",
        "biome": "Amazonian Rhizosphere",
        "samples": 120,
        "centre": "ENA",
        "url": "https://www.ebi.ac.uk/ena/browser/view/ERP009703",
        "origin": "curated",
        "importable": True,
    },
]


class LibraryError(RuntimeError):
    """A remote catalogue could not be queried."""


def _clean(query: str) -> str:
    return _SAFE_QUERY.sub(" ", query or "").strip()


def search_curated(query: str = "") -> list[Study]:
    q = _clean(query).lower()
    if not q:
        return [dict(s) for s in CURATED]
    return [
        dict(s)
        for s in CURATED
        if q in " ".join(str(s.get(k, "")) for k in ("accession", "title", "description", "biome")).lower()
    ]


def search_mgnify(query: str = "", biome: str = "", limit: int = 20, page: int = 1) -> list[Study]:
    """Search MGnify studies by free text and/or biome lineage."""
    params: dict[str, Any] = {"page_size": max(1, min(limit, 50)), "page": max(1, page)}
    if _clean(query):
        params["search"] = _clean(query)
    url = _MGNIFY
    if biome.strip():
        url = f"{_MGNIFY.rsplit('/', 1)[0]}/biomes/{biome.strip().replace(':', '%3A')}/studies"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        items = resp.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        raise LibraryError(f"MGnify search failed: {exc}") from exc

    out: list[Study] = []
    for item in items:
        a = item.get("attributes", {})
        acc = item.get("id") or a.get("accession", "")
        out.append(
            {
                "source": "mgnify",
                "accession": acc,
                "title": a.get("study-name") or acc,
                "description": (a.get("study-abstract") or "").strip(),
                "biome": (a.get("biome-id") or "").strip(),
                "samples": a.get("samples-count") or 0,
                "centre": a.get("centre-name") or "",
                "bioproject": a.get("bioproject") or "",
                "secondary": a.get("secondary-accession") or "",
                "updated": (a.get("last-update") or "")[:10],
                "url": f"https://www.ebi.ac.uk/metagenomics/studies/{acc}",
                "origin": "live",
                "importable": True,
            }
        )
    return out


def search_ena(query: str = "", limit: int = 20) -> list[Study]:
    """Search ENA studies (mirrors NCBI SRA / DDBJ) whose title matches *query*."""
    q = _clean(query)
    if not q:
        raise LibraryError("ENA search needs a query (e.g. '16S soil Amazon').")
    clauses = " AND ".join(f'study_title="*{w}*"' for w in q.split()[:6])
    params = {
        "result": "study",
        "query": clauses,
        "fields": "study_accession,secondary_study_accession,study_title,center_name,first_public",
        "format": "json",
        "limit": max(1, min(limit, 50)),
    }
    try:
        resp = requests.get(f"{_ENA}/search", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json() if resp.text.strip() else []
    except (requests.RequestException, ValueError) as exc:
        raise LibraryError(f"ENA search failed: {exc}") from exc

    return [
        {
            "source": "ena",
            "accession": r.get("study_accession", ""),
            "title": r.get("study_title") or r.get("study_accession", ""),
            "description": "",
            "biome": "",
            "samples": 0,
            "centre": r.get("center_name") or "",
            "bioproject": r.get("study_accession", "") if str(r.get("study_accession", "")).startswith("PRJ") else "",
            "secondary": r.get("secondary_study_accession") or "",
            "updated": r.get("first_public") or "",
            "url": f"https://www.ebi.ac.uk/ena/browser/view/{r.get('study_accession', '')}",
            "origin": "live",
            "importable": True,
        }
        for r in rows
    ]


def resolve_runs(study_accession: str, limit: int = 10) -> list[str]:
    """Run accessions (SRR/ERR/DRR) of an ENA/SRA study, so they can be fed to the SRA downloader."""
    acc = (study_accession or "").strip()
    if not _ACCESSION.match(acc):
        raise LibraryError("Invalid study accession.")
    try:
        resp = requests.get(
            f"{_ENA}/filereport",
            params={"accession": acc, "result": "read_run", "fields": "run_accession", "format": "tsv"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise LibraryError(f"ENA lookup failed: {exc}") from exc
    runs = [ln.strip() for ln in resp.text.splitlines()[1:] if ln.strip()]
    return runs[: max(1, min(limit, 200))]


def search(source: str, query: str = "", biome: str = "", limit: int = 20, page: int = 1) -> list[Study]:
    if source == "curated":
        return search_curated(query)
    if source == "mgnify":
        return search_mgnify(query, biome, limit, page)
    if source == "ena":
        return search_ena(query, limit)
    raise LibraryError(f"Unknown source '{source}'. Use one of: {', '.join(SOURCES)}.")
