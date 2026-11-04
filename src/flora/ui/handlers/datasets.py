"""Datasets the pipeline can ingest: already downloaded (project/workdir) or uploaded from the computer."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timezone
from pathlib import Path

from flora.ui.http import UiHttpError, json_success

_FILES = {"metadata": "metadata.tsv", "asv": "asv_table.tsv", "taxonomy": "taxonomy.tsv"}
_UPLOAD_KINDS = {"metadata", "asv", "taxonomy"}
_ALLOWED_EXT = {".tsv", ".csv", ".txt", ".biom"}
_MAX_UPLOAD = 200 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_DEPTH = 4


def _roots(state) -> list[tuple[Path, str]]:
    """Folders scanned for downloaded datasets, with a label saying where they belong."""
    roots: list[tuple[Path, str]] = []
    active = state.projects.active_id()
    if active:
        roots.append((state.projects.dir(active) / "raw", "project"))
    roots.append((Path(state.workdir) / "raw", "workdir"))
    roots.append((Path(state.workdir) / "uploads", "upload"))
    return roots


def _header(path: Path) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            line = fh.readline().rstrip("\r\n")
    except OSError:
        return []
    return [c.strip() for c in re.split(r"[\t,]", line) if c.strip()]


def _rows(path: Path) -> int:
    try:
        with open(path, "rb") as fh:
            return max(sum(1 for _ in fh) - 1, 0)
    except OSError:
        return 0


def _describe(folder: Path, origin: str, root: Path) -> dict | None:
    found = {kind: folder / name for kind, name in _FILES.items() if (folder / name).is_file()}
    has_fastq = (folder / "fastq").is_dir() or (folder / "manifest.tsv").is_file()
    if not found and not has_fastq:
        return None
    meta = found.get("metadata")
    missing = [k for k in _FILES if k not in found]
    newest = max((p.stat().st_mtime for p in found.values()), default=folder.stat().st_mtime)
    raw_reads_only = bool(has_fastq and "asv" not in found)
    metadata_only = bool(meta and "asv" not in found and not raw_reads_only)
    return {
        "id": str(folder),
        "label": str(folder.relative_to(root)) if folder != root else folder.name,
        "path": str(folder),
        "origin": origin,
        "files": {k: str(v) for k, v in found.items()},
        "missing": missing,
        "complete": not missing,
        "raw_reads_only": raw_reads_only,
        "metadata_only": metadata_only,
        "analyzable": not missing and not raw_reads_only,
        "samples": _rows(meta) if meta else 0,
        "columns": _header(meta) if meta else [],
        "modified": datetime.fromtimestamp(newest, timezone.utc).isoformat(timespec="seconds"),
    }


def list_datasets(state, params=None):
    """Datasets found on disk, newest first. Complete ones (metadata + ASV + taxonomy) can be ingested directly."""
    seen: set[Path] = set()
    out: list[dict] = []
    for root, origin in _roots(state):
        if not root.is_dir():
            continue
        candidates = [root, *sorted(p for p in root.rglob("*") if p.is_dir() and len(p.relative_to(root).parts) <= _MAX_DEPTH)]
        for folder in candidates:
            if folder in seen or folder.name == "fastq":
                continue
            seen.add(folder)
            item = _describe(folder, origin, root)
            if item:
                out.append(item)
    out.sort(key=lambda d: d["modified"], reverse=True)
    return json_success(data={"datasets": out})


def upload_file(state, body: dict):
    """Receive a file picked on the user's computer (base64) and store it under ``<workdir>/uploads``."""
    kind = str(body.get("kind") or "")
    if kind not in _UPLOAD_KINDS:
        raise UiHttpError("kind must be metadata, asv or taxonomy", code="invalid_kind")
    name = _SAFE_NAME.sub("_", Path(str(body.get("filename") or "")).name).strip("._")
    if not name or Path(name).suffix.lower() not in _ALLOWED_EXT:
        raise UiHttpError(f"Unsupported file. Use one of: {', '.join(sorted(_ALLOWED_EXT))}", code="invalid_file")
    try:
        data = base64.b64decode(str(body.get("content") or ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UiHttpError("content must be valid base64", code="invalid_content") from exc
    if not data:
        raise UiHttpError("The file is empty", code="empty_file")
    if len(data) > _MAX_UPLOAD:
        raise UiHttpError("File larger than 200 MB", status=413, code="too_large")

    batch = _SAFE_NAME.sub("_", str(body.get("batch") or "")).strip("._")[:40] or "manual"
    folder = Path(state.workdir) / "uploads" / batch
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    dest.write_bytes(data)
    return json_success(data={"path": str(dest), "kind": kind, "bytes": len(data), "columns": _header(dest) if kind == "metadata" else []})
