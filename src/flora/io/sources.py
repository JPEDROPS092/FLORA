"""One interface for catalog sources: search, metadata preview, download.

MGnify, EMP and URL downloads call the existing download helpers. ENA studies
in this catalog are large, so the library download writes a run-metadata table
instead of pulling FASTQ (that path stays on ``NCBISRADownloader``).
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import requests

from flora.core.exceptions import IngestionError
from flora.io.catalog import Entry, get_entry, load_catalog
from flora.io.downloaders import (
    EMPDownloader,
    MGnifyDownloader,
    _download_file,
    _make_session,
)
from flora.io.library import LibraryError, search_ena, search_mgnify
from flora.io.synthetic import preview_synthetic, write_synthetic

logger = logging.getLogger("flora.io.sources")

_ENA = "https://www.ebi.ac.uk/ena/portal/api/search"
_ENA_FIELDS = (
    "run_accession,sample_accession,library_strategy,library_source,"
    "instrument_platform,scientific_name,country,lat,lon,isolation_source"
)
_ACCESSION = re.compile(r"^[A-Za-z]{1,6}\d{3,}$")
_MGNIFY_ACC = re.compile(r"^MGYS\d+$")
_PREVIEW_CAP = 50
_ENA_DOWNLOAD_CAP = 500
_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class Source(Protocol):
    """Search a catalogue, preview sample metadata, and download what is practical."""

    id: str

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]: ...

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]: ...

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]: ...


def _preview(source: str, accession: str, columns: list[str], rows: list[dict], limit: int) -> dict:
    clipped = rows[:limit]
    return {
        "source": source,
        "accession": accession,
        "columns": columns,
        "rows": clipped,
        "row_count": len(clipped),
        "truncated": len(rows) > limit,
    }


def _write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        columns = list(rows[0].keys())
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in columns})


def _safe_name(url: str, fallback: str) -> str:
    name = urlparse(url).path.rstrip("/").split("/")[-1]
    name = _FILENAME.sub("_", name).strip("._") or fallback
    return name[:180]


def _require_entry(source: str, accession: str, entry: Entry | None) -> Entry:
    found = entry or get_entry(source, accession)
    if found is None:
        raise LibraryError(f"{accession} is not in the {source} catalog")
    return found


class SyntheticSource:
    id = "synthetic"

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return [item for item in load_catalog() if item["source"] == self.id]

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]:
        _require_entry(self.id, accession, None)
        limit = max(1, min(limit, _PREVIEW_CAP))
        rows = preview_synthetic(limit + 1)
        return _preview(self.id, accession, list(rows[0].keys()) if rows else [], rows, limit)

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]:
        _require_entry(self.id, accession, opts.get("entry"))
        written = write_synthetic(
            output_dir,
            samples=int(opts.get("samples") or 80),
            features=int(opts.get("features") or 200),
            seed=int(opts.get("seed") or 42),
        )
        return {key: str(path) for key, path in written.items()}


class EmpSource:
    id = "emp"

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return [item for item in load_catalog() if item["source"] == self.id]

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]:
        entry = _require_entry(self.id, accession, None)
        limit = max(1, min(limit, _PREVIEW_CAP))
        files = entry.get("files") or []
        url = next((item["url"] for item in files if item.get("kind") == "metadata"), "")
        if not url:
            raise LibraryError("EMP catalog entry has no metadata file")
        try:
            response = _make_session().get(url, stream=True, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LibraryError(f"EMP metadata request failed: {exc}") from exc
        lines: list[str] = []
        for chunk in response.iter_lines(decode_unicode=True):
            if chunk is None:
                continue
            lines.append(str(chunk))
            if len(lines) > limit + 2:
                break
        response.close()
        rows = _tsv_rows(lines, limit + 1)
        columns = list(rows[0].keys()) if rows else []
        return _preview(self.id, accession, columns, rows, limit)

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]:
        _require_entry(self.id, accession, opts.get("entry"))
        biome = opts.get("biome") or None
        files = EMPDownloader(biome_filter=biome).fetch(
            output_dir=output_dir,
            max_samples=int(opts.get("max_samples") or 200),
        )
        return {key: str(path) for key, path in files.items()}


class MGnifySource:
    id = "mgnify"

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        biome = str(filters.get("biome") or "")
        limit = int(filters.get("limit") or 20)
        return search_mgnify(query, biome, limit)

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]:
        _check_mgnify(accession)
        limit = max(1, min(limit, _PREVIEW_CAP))
        rows = _mgnify_samples(accession, limit + 1)
        columns = list(rows[0].keys()) if rows else _SAMPLE_COLUMNS
        return _preview(self.id, accession, columns, rows, limit)

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]:
        _require_entry(self.id, accession, opts.get("entry"))
        return download_mgnify_tables(accession, Path(output_dir))


class EnaSource:
    id = "ena"

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return search_ena(query, int(filters.get("limit") or 20))

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]:
        _check_ena(accession)
        limit = max(1, min(limit, _PREVIEW_CAP))
        rows = _ena_runs(accession, limit + 1)
        columns = list(rows[0].keys()) if rows else _ENA_FIELDS.split(",")
        return _preview(self.id, accession, columns, rows, limit)

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]:
        _require_entry(self.id, accession, opts.get("entry"))
        _check_ena(accession)
        out = Path(output_dir)
        rows = _ena_runs(accession, _ENA_DOWNLOAD_CAP)
        if not rows:
            raise LibraryError(f"No public runs found for {accession}")
        metadata_path = out / "metadata.tsv"
        _write_tsv(metadata_path, rows)
        return {"metadata": str(metadata_path)}


class UrlSource:
    id = "url"

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return [item for item in load_catalog() if item["source"] == self.id]

    def metadata(self, accession: str, limit: int = 50) -> dict[str, Any]:
        entry = _require_entry(self.id, accession, None)
        limit = max(1, min(limit, _PREVIEW_CAP))
        url = entry.get("metadata_url") or next(
            (item["url"] for item in entry.get("files") or [] if item.get("kind") == "metadata"),
            "",
        )
        if not url:
            raise LibraryError(f"{accession} has no metadata table to preview")
        text = _fetch_text(url, max_bytes=2_000_000)
        rows = _tsv_rows(text.splitlines(), limit + 1)
        columns = list(rows[0].keys()) if rows else []
        return _preview(self.id, accession, columns, rows, limit)

    def download(self, accession: str, output_dir: str | Path, **opts: Any) -> dict[str, str]:
        entry = _require_entry(self.id, accession, opts.get("entry"))
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}
        session = _make_session()
        for index, item in enumerate(entry.get("files") or []):
            url = str(item.get("url") or "")
            if urlparse(url).scheme not in ("http", "https"):
                raise LibraryError(f"Refusing non-HTTP download for {accession}")
            kind = str(item.get("kind") or "file")
            dest = out / _safe_name(url, f"{kind}-{index}")
            _download_file(url, dest, session=session, min_bytes=32)
            key = _artifact_key(kind, index)
            artifacts[key] = str(dest)
        if not artifacts:
            raise LibraryError(f"{accession} has no files to download")
        return artifacts


def _artifact_key(kind: str, index: int) -> str:
    if kind in {"metadata", "taxonomy", "asv", "sequences", "barcodes", "archive"}:
        if kind == "asv":
            return "asv_table"
        return kind
    if kind == "sequences_reverse":
        return "sequences_reverse"
    return f"file_{index}"


_SAMPLE_COLUMNS = [
    "sample_id",
    "latitude",
    "longitude",
    "environment_biome",
    "environment_feature",
    "environment_material",
    "geo_loc_name",
    "collection_date",
    "sample_name",
    "sample_desc",
    "substrate",
    "land_cover",
    "site",
]


def _check_mgnify(accession: str) -> None:
    if not _MGNIFY_ACC.match(accession or ""):
        raise LibraryError("Invalid MGnify accession")


def _check_ena(accession: str) -> None:
    if not _ACCESSION.match(accession or ""):
        raise LibraryError("Invalid ENA study accession")


def _mgnify_samples(accession: str, limit: int) -> list[dict[str, Any]]:
    downloader = MGnifyDownloader()
    session = _make_session()
    url = f"{downloader.api_base}/studies/{accession}/samples?page_size={min(max(limit, 1), 100)}"
    rows: list[dict[str, Any]] = []
    try:
        for item in downloader._iter_paginated(session, url):
            rows.append(_sample_row(item))
            if len(rows) >= limit:
                break
    except IngestionError as exc:
        raise LibraryError(str(exc)) from exc
    return rows


_LAND_COVER = (("deforest", "deforested"), ("regenerat", "regeneration"), ("pastur", "pasture"), ("forest", "forest"))
_MUNICIPALITY = re.compile(r"\b(Bel[eé]n|Solano)\b", re.IGNORECASE)
_SITE = re.compile(r"\bsite\s+(\w+)", re.IGNORECASE)


def _from_description(desc: str) -> dict[str, str]:
    """Plain keyword reading of the submitter's sample description (kept next to the raw text in ``sample_desc``)."""
    low = desc.lower()
    first = low.split(" ", 1)[0] if low else ""
    cover = next((label for key, label in _LAND_COVER if key in low), "")
    place = _MUNICIPALITY.search(desc)
    site = _SITE.search(desc)
    return {
        "substrate": first if first in {"soil", "litter"} else "",
        "land_cover": cover,
        "site": (place.group(1).capitalize() if place else f"site {site.group(1)}" if site else ""),
    }


def _sample_row(item: dict) -> dict[str, Any]:
    attrs = item.get("attributes") or {}

    def text(key: str) -> str:
        value = attrs.get(key)
        return "" if value in (None, "None") else str(value).replace("''", "'").strip()

    desc = text("sample-desc")
    return {
        "sample_id": item.get("id") or "",
        "latitude": attrs.get("latitude") if attrs.get("latitude") is not None else "",
        "longitude": attrs.get("longitude") if attrs.get("longitude") is not None else "",
        "environment_biome": attrs.get("environment-biome") or "",
        "environment_feature": attrs.get("environment-feature") or "",
        "environment_material": attrs.get("environment-material") or "",
        "geo_loc_name": attrs.get("geo-loc-name") or "",
        "collection_date": text("collection-date"),
        "sample_name": text("sample-name"),
        "sample_desc": desc,
        **_from_description(desc),
    }


def download_mgnify_tables(accession: str, out: Path) -> dict[str, str]:
    """Sample metadata plus, when MGnify published it, the SSU table converted to FLORA's ``asv_table``/``taxonomy``."""
    _check_mgnify(accession)
    out.mkdir(parents=True, exist_ok=True)
    rows = _mgnify_samples(accession, 200)
    if not rows:
        raise LibraryError(f"No samples returned for {accession}")
    metadata_path = out / "metadata.tsv"
    _write_tsv(metadata_path, rows)
    artifacts = {"metadata": str(metadata_path)}
    artifacts.update(_download_ssu_table(accession, out))
    return artifacts


def _download_ssu_table(accession: str, output_dir: Path) -> dict[str, str]:
    """Study-level SSU taxonomy table from MGnify, converted to FLORA's ``asv_table.tsv`` + ``taxonomy.tsv``.

    Returns the artifacts it managed to write (possibly empty). Failures are logged, never raised,
    because the sample metadata is still worth keeping.
    """
    from flora.io.mgnify_tables import analysis_sample_map, convert_ssu_table

    downloader = MGnifyDownloader()
    session = _make_session()
    try:
        payload = downloader._api_get(session, f"{downloader.api_base}/studies/{accession}/downloads?page_size=100")
    except IngestionError as exc:
        logger.warning("MGnify downloads list failed for %s: %s", accession, exc)
        return {}
    links: dict[str, str] = {}
    for item in payload.get("data") or []:
        alias = str((item.get("attributes") or {}).get("alias") or item.get("id") or "").lower()
        link = str((item.get("links") or {}).get("self") or "")
        if link and "taxonomy_abundances" in alias and "phylum" not in alias:
            links["ssu" if "_ssu_" in alias else "lsu" if "_lsu_" in alias else "other"] = link
    chosen = links.get("ssu") or links.get("lsu") or links.get("other")
    if not chosen:
        return {}
    raw = output_dir / _safe_name(chosen, "taxonomy_abundances.tsv")
    try:
        _download_file(chosen, raw, session=session, min_bytes=32)
        analyses = list(downloader._iter_paginated(session, f"{downloader.api_base}/studies/{accession}/analyses?page_size=100"))
        tables = convert_ssu_table(raw.read_text(encoding="utf-8", errors="replace"), analysis_sample_map(analyses), output_dir)
    except (IngestionError, ValueError, OSError) as exc:
        logger.warning("MGnify SSU table for %s could not be converted: %s", accession, exc)
        raise LibraryError(
            f"A MGnify publicou a tabela taxonômica de {accession}, mas ela não pôde ser convertida em tabela ASV: {exc}"
        ) from exc
    return {**tables, "raw_taxonomy": str(raw)}


def _ena_runs(accession: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "result": "read_run",
        "query": f"study_accession={accession}",
        "fields": _ENA_FIELDS,
        "format": "json",
        "limit": max(1, limit),
    }
    try:
        response = _make_session().get(_ENA, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json() if response.text.strip() else []
    except (requests.RequestException, ValueError) as exc:
        raise LibraryError(f"ENA metadata request failed: {exc}") from exc
    if not isinstance(payload, list):
        raise LibraryError("ENA metadata response was not a list")
    return payload


def _fetch_text(url: str, max_bytes: int) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        raise LibraryError("Metadata URL must be HTTP(S)")
    try:
        response = _make_session().get(url, stream=True, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LibraryError(f"Metadata request failed: {exc}") from exc
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        chunks.append(chunk)
        size += len(chunk)
        if size >= max_bytes:
            break
    response.close()
    return b"".join(chunks).decode("utf-8", "replace")


def _tsv_rows(lines: list[str], limit: int) -> list[dict[str, str]]:
    body = [line for line in lines if line.strip() and not line.startswith("#")]
    if not body:
        return []
    header = body[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in body[1 : limit + 1]:
        cells = line.split("\t")
        rows.append({header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))})
    return rows


_REGISTRY: dict[str, Source] = {
    "synthetic": SyntheticSource(),
    "emp": EmpSource(),
    "mgnify": MGnifySource(),
    "ena": EnaSource(),
    "url": UrlSource(),
}


def get_source(source_id: str) -> Source:
    try:
        return _REGISTRY[source_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise LibraryError(f"Unknown source '{source_id}'. Use one of: {known}.") from exc
