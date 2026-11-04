"""Download and log UI handlers."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from flora.ui.http import UiHttpError, json_success

logger = logging.getLogger("flora.ui.downloads")


def get_logs(log_buffer: list[str], params: dict):
    count = min(int(params.get("n", ["100"])[0]), 500)
    return json_success(data={"lines": log_buffer[-count:]})


_ARTIFACT_KEYS = {
    "manifest": "Manifesto",
    "asv_table": "ASV",
    "taxonomy": "Taxonomia",
    "metadata": "Metadata",
    "sequences": "Sequências",
    "sequences_reverse": "Sequências (R2)",
    "barcodes": "Barcodes",
    "archive": "Arquivo",
}

_ACC = r"(?P<acc>[A-Za-z0-9._-]+)"
_SRC = r"(?P<source>[a-z0-9_-]+)"
_LIBRARY_META = re.compile(rf"^/api/library/{_SRC}/{_ACC}/metadata$")
_LIBRARY_MAP = re.compile(rf"^/api/library/{_SRC}/{_ACC}/map$")
_LIBRARY_DOWNLOAD = re.compile(rf"^/api/library/{_SRC}/{_ACC}/download$")


def _store(state):
    from flora.projects.store import RecordStore

    return RecordStore(Path(state.workdir) / "downloads")


def recorded(source: str, handler):
    """Wrap a download handler so every attempt is persisted and returned as a ``job``."""
    from flora.projects.store import new_id, now_iso

    def inner(state, body: dict):
        job = {"id": new_id(), "source": source, "created_at": now_iso(), "artifacts": [], "detail": body.get("output_dir", "")}
        try:
            payload = handler(state, body)
        except Exception as exc:
            job.update(status="failed", detail=str(exc))
            _store(state).save(job)
            raise
        job["artifacts"] = [{"label": label, "path": str(payload[key])} for key, label in _ARTIFACT_KEYS.items() if payload.get(key)]
        job.update(status="completed", detail=str(payload.get("output_dir") or job["detail"]))
        _store(state).save(job)
        return {**payload, "output_dir": job["detail"], "job": job}

    inner.__name__ = f"recorded_{source}"
    return inner


def list_downloads(state, params=None):
    return json_success(data={"jobs": _store(state).list()})


def _first(params: dict | None, key: str, default: str = "") -> str:
    return ((params or {}).get(key) or [default])[0]


def library_search(state, params=None):
    """Discover studies (accession codes, title, biome…) before downloading anything."""
    from flora.io import library

    source = _first(params, "source", "curated")
    try:
        limit = int(_first(params, "limit", "20"))
        page = int(_first(params, "page", "1"))
    except ValueError as exc:
        raise UiHttpError("limit and page must be integers", code="invalid_params") from exc
    try:
        studies = library.search(source, _first(params, "q"), _first(params, "biome"), limit, page)
    except library.LibraryError as exc:
        raise UiHttpError(str(exc), status=502 if "failed" in str(exc) else 400, code="library_error") from exc
    return json_success(data={"source": source, "studies": studies})


def library_route(method: str, path: str) -> tuple[str, dict[str, str]] | None:
    """Match catalog, metadata and download paths. Exact routes stay in the server table."""
    if method == "GET" and path == "/api/library/catalog":
        return "catalog", {}
    if method == "GET" and (match := _LIBRARY_META.fullmatch(path)):
        return "metadata", {"source": match["source"], "accession": match["acc"]}
    if method == "GET" and (match := _LIBRARY_MAP.fullmatch(path)):
        return "map", {"source": match["source"], "accession": match["acc"]}
    if method == "POST" and (match := _LIBRARY_DOWNLOAD.fullmatch(path)):
        return "download", {"source": match["source"], "accession": match["acc"]}
    return None


def _flag(params: dict | None, key: str) -> bool:
    return _first(params, key).lower() in {"1", "true", "yes", "on"}


def library_catalog(state, params=None):
    """Curated catalog with biome, host, region, sequence type and free-text filters."""
    from flora.io.catalog import filter_catalog

    studies = filter_catalog(
        q=_first(params, "q"),
        biome=_first(params, "biome"),
        host=_first(params, "host"),
        region=_first(params, "region"),
        seq_type=_first(params, "seq_type"),
        amazonia=_flag(params, "amazonia"),
    )
    return json_success(data={"studies": studies, "count": len(studies)})


def library_metadata(state, params=None):
    """Preview up to 50 metadata rows for a catalogued dataset."""
    from flora.io.catalog import get_entry
    from flora.io.library import LibraryError
    from flora.io.sources import get_source

    source = _first(params, "source")
    accession = _first(params, "accession")
    if get_entry(source, accession) is None:
        raise UiHttpError(
            f"Dataset {accession} is not in the catalog",
            status=404,
            code="not_found",
        )
    try:
        limit = int(_first(params, "limit", "50"))
    except ValueError as exc:
        raise UiHttpError("limit must be an integer", code="invalid_params") from exc
    try:
        preview = get_source(source).metadata(accession, limit)
    except LibraryError as exc:
        raise UiHttpError(str(exc), status=502, code="library_error") from exc
    return json_success(data={"preview": preview})


def library_map(state, params=None):
    """Sample locations of an already downloaded catalog dataset (empty when none are available)."""
    from flora.io.catalog import get_entry
    from flora.io.geo import read_points

    source = _first(params, "source")
    accession = _first(params, "accession")
    if get_entry(source, accession) is None:
        raise UiHttpError(f"Dataset {accession} is not in the catalog", status=404, code="not_found")
    metadata = _library_output(state, {}, source, accession) / "metadata.tsv"
    return json_success(data={"map": read_points(metadata, _first(params, "group_by") or None)})


def _library_output(state, body: dict, source: str, accession: str) -> Path:
    base = Path(state.workdir).resolve()
    raw = body.get("output_dir")
    if not raw:
        return base / "raw" / source / accession
    path = Path(str(raw))
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if path != base and base not in path.parents:
        raise UiHttpError("output_dir must stay inside the workdir", code="invalid_output_dir")
    return path


def library_download(state, body: dict):
    """Download a catalogued dataset and return artifact paths for ``recorded``."""
    from flora.core.exceptions import IngestionError
    from flora.io.catalog import get_entry
    from flora.io.library import LibraryError
    from flora.io.sources import get_source

    source = str(body.get("source") or "")
    accession = str(body.get("accession") or "")
    entry = get_entry(source, accession)
    if entry is None:
        raise UiHttpError(
            f"Dataset {accession} is not in the catalog",
            status=404,
            code="not_found",
        )
    if not entry.get("importable", True):
        raise UiHttpError(f"{accession} is not downloadable", code="not_importable")
    output_dir = _library_output(state, body, source, accession)
    try:
        artifacts = get_source(source).download(
            accession,
            output_dir,
            entry=entry,
            samples=body.get("samples") or 80,
            features=body.get("features") or 200,
            seed=body.get("seed") if body.get("seed") is not None else 42,
            max_samples=body.get("max_samples") or 200,
            biome=body.get("biome") or body.get("biome_filter"),
        )
    except (LibraryError, IngestionError, OSError, ValueError) as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc
    return json_success(data={**artifacts, "output_dir": str(output_dir), "accession": accession})


def library_runs(state, params=None):
    """Run accessions of an ENA/SRA study, to hand to the SRA downloader."""
    from flora.io import library

    try:
        runs = library.resolve_runs(_first(params, "study"), int(_first(params, "limit", "10")))
    except (library.LibraryError, ValueError) as exc:
        raise UiHttpError(str(exc), status=400, code="library_error") from exc
    return json_success(data={"runs": runs})


def download_mgnify(state, body: dict):
    from flora.io.downloaders import MGnifyDownloader

    study = body.get("study_accession", "")
    if not study:
        raise UiHttpError("study_accession is required", code="missing_study_accession")

    biome = body.get("biome", "root:Environmental:Terrestrial")
    output_dir = body.get("output_dir", str(state.workdir / "raw"))
    max_samples = int(body.get("max_samples", 20))

    downloader = MGnifyDownloader(biome=biome)
    try:
        manifest = downloader.fetch(
            study_accession=study,
            output_dir=output_dir,
            max_samples=max_samples,
        )
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    with open(manifest, encoding="utf-8") as fh:
        n_files = max(sum(1 for _ in fh) - 1, 0)
    if n_files == 0:
        # MGnify serves processed analyses, not raw reads: the sample metadata was saved but no FASTQ exists here.
        raise UiHttpError(
            f"MGnify has no FASTQ files for {study}. Sample metadata was saved in {output_dir}, "
            "but the manifest is empty. Raw reads live in ENA: pick the study under ENA / SRA to download them.",
            code="no_fastq",
            details={"metadata": str(Path(output_dir) / "metadata.tsv")},
        )

    return json_success(data={"manifest": str(manifest), "output_dir": output_dir})


def download_sra(state, body: dict):
    from flora.io.downloaders import NCBISRADownloader

    accessions = body.get("accessions", [])
    if not accessions:
        raise UiHttpError("accessions list is required", code="missing_accessions")

    output_dir = body.get("output_dir", str(state.workdir / "raw"))
    jobs = int(body.get("n_jobs", 4))

    downloader = NCBISRADownloader(n_jobs=jobs)
    try:
        manifest = downloader.fetch(accessions=accessions, output_dir=output_dir)
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    return json_success(data={"manifest": str(manifest), "accessions": accessions})


def download_emp(state, body: dict):
    from flora.io.downloaders import EMPDownloader

    output_dir = body.get("output_dir", str(state.workdir / "raw" / "emp"))
    biome = body.get("biome_filter") or None
    max_samples = int(body.get("max_samples", 200))

    downloader = EMPDownloader(biome_filter=biome)
    try:
        files = downloader.fetch(output_dir=output_dir, max_samples=max_samples)
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    return json_success(
        data={
            "asv_table": str(files["asv_table"]),
            "taxonomy": str(files["taxonomy"]),
            "metadata": str(files["metadata"]),
        }
    )


def download_synthetic(state, body: dict):
    from flora.io.synthetic import write_synthetic

    output_dir = Path(body.get("output_dir", str(state.workdir / "raw" / "synthetic")))
    sample_count = int(body.get("samples", 80))
    feature_count = int(body.get("features", 200))
    seed = int(body.get("seed", 42))
    written = write_synthetic(output_dir, samples=sample_count, features=feature_count, seed=seed)
    logger.info(
        "Synthetic data generated: %d samples, %d features -> %s",
        sample_count,
        feature_count,
        output_dir,
    )
    return json_success(data={key: str(path) for key, path in written.items()})
