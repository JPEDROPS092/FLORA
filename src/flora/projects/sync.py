"""Asynchronous, persisted, incremental data-source synchronisation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from flora.projects.registry import ProjectError, ProjectRegistry, Source, _now

_ACTIVE = {"queued", "running"}
_ACCESSION = re.compile(r"^[A-Za-z0-9_.\-:]{3,64}$")
_MAX_CONCURRENT = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Cancelled(Exception):
    pass


class SyncManager:
    """Runs one sync job per project in a worker thread; state lives in ``<project>/jobs``.

    ``pipeline_for(project_id)`` must return the project's isolated ``FLORAPipeline``.
    """

    def __init__(self, registry: ProjectRegistry, pipeline_for: Callable[[str], Any]) -> None:
        self.registry = registry
        self._pipeline_for = pipeline_for
        self._lock = threading.Lock()
        self._cancel: dict[str, threading.Event] = {}
        self._slots = threading.BoundedSemaphore(_MAX_CONCURRENT)

    # ---- public API ------------------------------------------------------
    def start(self, project_id: str, source: dict[str, Any]) -> dict[str, Any]:
        project = self.registry.get(project_id)
        src = self._validate(source)
        with self._lock:
            if any(j["status"] in _ACTIVE for j in self.list(project_id)):
                raise ProjectError("A sync is already running for this project.", "sync_in_progress", 409)
            job = {
                "id": uuid.uuid4().hex[:12], "project_id": project.id, "source": src.model_dump(), "status": "queued",
                "message": "Na fila", "progress": 0, "log": [], "error": "", "result": {}, "created_at": _now(), "finished_at": "",
            }
            self._save(job)
            self._cancel[job["id"]] = threading.Event()
        threading.Thread(target=self._run, args=(job["id"], project.id), daemon=True, name=f"sync-{job['id']}").start()
        return job

    def get(self, job_id: str, project_id: str | None = None) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{12}", job_id or ""):
            raise ProjectError("Invalid job id.", "invalid_job_id")
        for pid in [project_id] if project_id else [p.id for p in self.registry.list()]:
            path = self.registry.dir(pid) / "jobs" / f"{job_id}.json"
            if path.exists():
                return json.loads(path.read_text("utf-8"))
        raise ProjectError("Sync job not found.", "not_found", 404)

    def list(self, project_id: str) -> list[dict[str, Any]]:
        folder = self.registry.dir(project_id) / "jobs"
        jobs = []
        for f in folder.glob("*.json") if folder.exists() else []:
            try:
                jobs.append(json.loads(f.read_text("utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] not in _ACTIVE:
            return job
        event = self._cancel.get(job_id)
        if event is None:  # job from a previous process: nothing is running
            return self._finish(job, "cancelled", "Cancelado")
        event.set()
        job["message"] = "Cancelando… (a etapa em andamento termina antes)"
        self._save(job)
        return job

    def recover(self) -> int:
        """Mark jobs left running by a previous process as failed. Returns how many."""
        count = 0
        for project in self.registry.list():
            for job in self.list(project.id):
                if job["status"] in _ACTIVE and job["id"] not in self._cancel:
                    self._finish(job, "failed", "Interrompido por reinício do servidor", error="interrupted")
                    count += 1
        return count

    # ---- internals -------------------------------------------------------
    @staticmethod
    def _validate(source: dict[str, Any]) -> Source:
        src = Source.model_validate(source or {})
        if src.type not in {"synthetic", "mgnify", "sra", "emp"}:
            raise ProjectError("Unsupported source type.", "invalid_source")
        if src.type in {"mgnify", "sra"} and not _ACCESSION.match(src.accession):
            raise ProjectError("A valid accession is required (letters, digits, . _ - :).", "invalid_accession")
        return src

    def _save(self, job: dict[str, Any]) -> None:
        folder = self.registry.dir(job["project_id"]) / "jobs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{job['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, indent=2), "utf-8")
        os.replace(tmp, path)

    def _finish(self, job: dict[str, Any], status: str, message: str, error: str = "") -> dict[str, Any]:
        job.update(status=status, message=message, error=error, finished_at=_now())
        if status == "completed":
            job["progress"] = 100
        self._save(job)
        self._cancel.pop(job["id"], None)
        return job

    def _step(self, job: dict[str, Any], progress: int, message: str) -> None:
        if self._cancel[job["id"]].is_set():
            raise _Cancelled()
        job.update(status="running", progress=progress, message=message)
        job["log"].append(f"{time.strftime('%H:%M:%S')} {message}")
        self._save(job)

    def _run(self, job_id: str, project_id: str) -> None:
        job = self.get(job_id, project_id)
        with self._slots:
            try:
                self._step(job, 5, "Iniciando")
                self._execute(job)
                self._finish(job, "completed", job["result"].get("summary", "Concluído"))
            except _Cancelled:
                self._finish(job, "cancelled", "Cancelado")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, never swallowed
                self._finish(job, "failed", "Falhou", error=str(exc))

    # ---- the actual work -------------------------------------------------
    def _execute(self, job: dict[str, Any]) -> None:
        project = self.registry.get(job["project_id"])
        src = Source.model_validate(job["source"])
        raw = self.registry.dir(project.id) / "raw" / src.type
        manifest_path = self.registry.dir(project.id) / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {"sources": {}}
        key = f"{src.type}:{src.accession}:{json.dumps(src.params, sort_keys=True)}"

        if project.stage == "ingested" and project.sources and key not in manifest["sources"]:
            raise ProjectError("This project already has analysed data from another source. Create a new project for this one.", "project_has_data", 409)

        if self._up_to_date(project.id, manifest, key):
            self._step(job, 90, "Verificando integridade (SHA-256)")
            job["result"] = {"up_to_date": True, "summary": "Já sincronizado: nada novo para baixar", "files": len(manifest["sources"][key]["files"])}
            return

        if project.stage == "ingested":
            raise ProjectError("Local files differ from the manifest and the data is already ingested. Create a new project to re-import.", "manifest_mismatch", 409)

        raw.mkdir(parents=True, exist_ok=True)
        self._step(job, 15, f"Baixando de {src.type}")
        ingest = self._download(src, raw, job)

        self._step(job, 60, "Calculando SHA-256 dos arquivos")
        files = {str(p.relative_to(raw)): {"sha256": sha256_file(p), "size": p.stat().st_size} for p in sorted(raw.rglob("*")) if p.is_file()}
        manifest["sources"][key] = {"files": files, "synced_at": _now()}
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), "utf-8")
        os.replace(tmp, manifest_path)

        stage, stats = "raw_downloaded", {}
        if ingest:
            self._step(job, 75, "Ingerindo no DuckDB do projeto")
            stats = self._ingest(project.id, ingest)
            stage = "ingested"
        patch: dict[str, Any] = {"stage": stage, "sources": [src.model_dump()], **stats}
        self.registry.update(project.id, patch)
        job["result"] = {
            "up_to_date": False, "files": len(files), "stage": stage,
            "summary": f"{len(files)} arquivos; " + ("pronto para análise" if stage == "ingested" else "arquivos brutos baixados — ainda não há matriz ASV"),
        }

    def _up_to_date(self, project_id: str, manifest: dict[str, Any], key: str) -> bool:
        entry = manifest["sources"].get(key)
        if not entry or not entry["files"]:
            return False
        stage = self.registry.get(project_id).stage
        if stage == "empty":
            return False
        raw = self.registry.dir(project_id) / "raw" / key.split(":", 1)[0]
        return all((raw / rel).is_file() and (raw / rel).stat().st_size == meta["size"] and sha256_file(raw / rel) == meta["sha256"]
                   for rel, meta in entry["files"].items())

    def _download(self, src: Source, raw: Path, job: dict[str, Any]) -> dict[str, Path] | None:
        """Fetch ``src`` into ``raw``. Returns tables to ingest, or None for raw-only sources."""
        if src.type == "synthetic":
            from flora.ui.handlers.downloads import download_synthetic

            p = {"samples": 80, "features": 200, "seed": 42, **src.params}
            out = download_synthetic(SimpleState(raw.parent.parent), {"output_dir": str(raw), **{k: int(v) for k, v in p.items()}})
            return {"metadata": Path(out["metadata"]), "asv": Path(out["asv_table"]), "taxonomy": Path(out["taxonomy"])}
        if src.type == "emp":
            from flora.io.downloaders import EMPDownloader

            files = EMPDownloader(biome_filter=src.params.get("biome_filter") or None).fetch(output_dir=str(raw), max_samples=int(src.params.get("max_samples", 200)))
            return {"metadata": Path(files["metadata"]), "asv": Path(files["asv_table"]), "taxonomy": Path(files["taxonomy"])}
        if src.type == "mgnify":
            from flora.io.sources import download_mgnify_tables

            # MGnify serves processed taxonomic tables, not raw reads: ingest them when they are complete.
            files = download_mgnify_tables(src.accession, raw)
            if {"metadata", "asv_table", "taxonomy"} <= set(files):
                return {"metadata": Path(files["metadata"]), "asv": Path(files["asv_table"]), "taxonomy": Path(files["taxonomy"])}
            job["log"].append("MGnify não publicou a tabela taxonômica deste estudo: só os metadados foram baixados.")
            return None
        from flora.io.downloaders import NCBISRADownloader

        NCBISRADownloader(n_jobs=int(src.params.get("n_jobs", 2))).fetch(accessions=[src.accession], output_dir=str(raw))
        return None

    def _ingest(self, project_id: str, files: dict[str, Path]) -> dict[str, Any]:
        pipe = self._pipeline_for(project_id)
        pipe.ingest_metadata(files["metadata"])
        pipe.ingest_asv_table(files["asv"], wide_format=True)
        pipe.ingest_taxonomy(files["taxonomy"])
        samples = int(pipe.db.query("SELECT COUNT(*) AS n FROM samples").to_polars()["n"][0])
        asvs = int(pipe.db.query("SELECT COUNT(DISTINCT feature_id) AS n FROM asv").to_polars()["n"][0])
        groups = [r[0] for r in pipe.db.query("SELECT DISTINCT biome FROM samples WHERE biome IS NOT NULL ORDER BY 1").to_polars().iter_rows()]
        return {"samples": samples, "asvs": asvs, "groups": groups}


class SimpleState:
    """Minimal stand-in exposing ``workdir`` for helpers written against the UI state."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
