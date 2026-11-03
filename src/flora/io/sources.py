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
        _check_mgnify(accession)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        rows = _mgnify_samples(accession, 200)
        if not rows:
            raise LibraryError(f"No samples returned for {accession}")
        metadata_path = out / "metadata.tsv"
        _write_tsv(metadata_path, rows)
        artifacts = {"metadata": str(metadata_path)}
        taxonomy = _download_ssu_table(accession, out)
        if taxonomy is not None:
            artifacts["taxonomy"] = str(taxonomy)
        return artifacts


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


def _sample_row(item: dict) -> dict[str, Any]:
    attrs = item.get("attributes") or {}
    return {
        "sample_id": item.get("id") or "",
        "latitude": attrs.get("latitude") if attrs.get("latitude") is not None else "",
        "longitude": attrs.get("longitude") if attrs.get("longitude") is not None else "",
        "environment_biome": attrs.get("environment-biome") or "",
        "environment_feature": attrs.get("environment-feature") or "",
        "environment_material": attrs.get("environment-material") or "",
        "geo_loc_name": attrs.get("geo-loc-name") or "",
    }


def _download_ssu_table(accession: str, output_dir: Path) -> Path | None:
    downloader = MGnifyDownloader()
    session = _make_session()
    url = f"{downloader.api_base}/studies/{accession}/downloads?page_size=100"
    try:
        payload = downloader._api_get(session, url)
    except IngestionError as exc:
        logger.warning("MGnify downloads list failed for %s: %s", accession, exc)
        return None
    chosen = ""
    for item in payload.get("data") or []:
        alias = str((item.get("attributes") or {}).get("alias") or item.get("id") or "").lower()
        link = str((item.get("links") or {}).get("self") or "")
        if "taxonomy_abundances_ssu" in alias and "phylum" not in alias and link:
            chosen = link
            break
        if not chosen and "taxonomy_abundances_ssu" in alias and link:
            chosen = link
    if not chosen:
        return None
    dest = output_dir / _safe_name(chosen, "taxonomy_ssu.tsv")
    try:
        _download_file(chosen, dest, session=session, min_bytes=32)
    except IngestionError as exc:
        logger.warning("SSU table download failed for %s: %s", accession, exc)
        return None
    return dest


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
