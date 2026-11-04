"""Run external workflows as persisted background jobs (log, progress, cancel, optional ingestion)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from flora.engines import registry
from flora.engines import workflows as wf

_ID = re.compile(r"^[0-9a-f]{12}$")
_ACTIVE = {"queued", "running"}
_MAX_LOG = 400
_MAX_JOBS = 2

#: workflow -> engine it needs; the last four read the active project's table, exported by the caller
NEEDS = {"qiime2-dada2": "qiime2", "dada2-r": "dada2", "aldex2": "aldex2", "ancombc2": "ancombc2", "vegan": "vegan",
         "cutadapt-trim": "cutadapt", "vsearch-otu": "vsearch"}
USES_PROJECT_DATA = {"aldex2", "ancombc2", "vegan", "vsearch-otu"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EngineError(Exception):
    def __init__(self, message: str, code: str = "engine_error", status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


class JobManager:
    """One manager per workdir. ``ingest(job_paths)`` is called on success when the user asked to ingest."""

    def __init__(self, root: Path, ingest: Callable[[dict[str, str]], dict[str, Any]] | None = None) -> None:
        self.root = Path(root)
        self._ingest = ingest
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen] = {}
        self._cancel: set[str] = set()
        self._slots = threading.BoundedSemaphore(_MAX_JOBS)

    # -- persistence ------------------------------------------------------
    def _path(self, job_id: str) -> Path:
        if not _ID.fullmatch(job_id or ""):
            raise EngineError("Invalid job id.", "invalid_job_id")
        return self.root / "jobs" / f"{job_id}.json"

    def _save(self, job: dict[str, Any]) -> None:
        path = self._path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def get(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.exists():
            raise EngineError("Job não encontrado.", "not_found", 404)
        return json.loads(path.read_text("utf-8"))

    def list(self) -> list[dict[str, Any]]:
        folder = self.root / "jobs"
        jobs = []
        for f in folder.glob("*.json") if folder.exists() else []:
            try:
                jobs.append(json.loads(f.read_text("utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def recover(self) -> None:
        """Jobs left 'running' by a previous process cannot still be running: mark them failed."""
        for job in self.list():
            if job["status"] in _ACTIVE:
                job.update(status="failed", error="O FLORA foi reiniciado durante a execução.", finished_at=_now())
                self._save(job)

    # -- planning ---------------------------------------------------------
    def plan(self, kind: str, params: dict[str, Any], out: Path, state_data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Steps: ``{label, cmd, script?}``. Raises ``EngineError``/``WorkflowError`` before anything runs."""
        threads = int(params.get("threads") or 4)
        need = NEEDS.get(kind)
        if need is None:
            raise EngineError(f"Fluxo desconhecido: {kind}", "unknown_workflow")
        if registry.detect(need) is None:
            raise EngineError(f"{registry.ENGINES[need].name} não está instalado. {registry.ENGINES[need].install}", "engine_unavailable", 409)
        try:
            if kind == "qiime2-dada2" and str(params.get("backend") or "cli") == "python":
                python = registry.qiime_python()
                if python is None:
                    raise EngineError("Nenhum Python com o QIIME 2 foi encontrado. Aponte o interpretador do ambiente do QIIME 2 em Ambientes.", "engine_unavailable", 409)
                spec, command = wf.qiime2_python_job(str(params.get("manifest") or ""), out, bool(params.get("paired", True)), params,
                                                     params.get("classifier") or None, threads, bool(params.get("build_tree")), python)
                return [{"label": "qiime2 (API Python)", "cmd": command, "spec": spec, "spec_path": command[2]}]
            if kind == "qiime2-dada2":
                cmds = wf.qiime2_dada2_commands(str(params.get("manifest") or ""), out, bool(params.get("paired", True)), params,
                                                params.get("classifier") or None, threads, bool(params.get("build_tree")))
                return [{"label": " ".join(c[1:3]), "cmd": c} for c in cmds]
            if kind == "dada2-r":
                cmd, script = wf.dada2_r_command(str(params.get("fastq_dir") or ""), out, str(params.get("ref_fasta") or ""), params, threads)
                return [{"label": "dada2", "cmd": cmd, "script": script, "script_path": cmd[2]}]
            data = state_data or {}
            asv, meta = str(data.get("asv", "")), str(data.get("metadata", ""))
            group, a, b = str(params.get("group_by") or ""), str(params.get("a") or ""), str(params.get("b") or "")
            if kind == "aldex2":
                cmd, script = wf.aldex2_command(asv, meta, group, a, b, out)
            elif kind == "ancombc2":
                cmd, script = wf.ancombc2_command(asv, meta, group, a, b, out)
            elif kind == "vegan":
                cmd, script = wf.vegan_command(asv, meta, group, str(params.get("metric") or "bray_curtis"), params.get("permutations") or 999, out)
            elif kind == "cutadapt-trim":
                return wf.cutadapt_commands(str(params.get("fastq_dir") or ""), out, str(params.get("fwd_primer") or ""), params.get("rev_primer") or None, threads)
            else:  # vsearch-otu
                return [{"label": "vsearch", "cmd": wf.vsearch_cluster_command(str(params.get("fasta") or ""), float(params.get("identity") or 0.97), out, threads)}]
            return [{"label": kind, "cmd": cmd, "script": script, "script_path": cmd[2]}]
        except wf.WorkflowError as exc:
            raise EngineError(str(exc), "invalid_params") from exc

    # -- execution --------------------------------------------------------
    def start(self, kind: str, params: dict[str, Any], state_data: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        out = self.root / job_id
        steps = self.plan(kind, params, out, state_data)  # validates before creating the job
        with self._lock:
            if sum(1 for j in self.list() if j["status"] in _ACTIVE) >= _MAX_JOBS:
                raise EngineError("Já há análises demais em execução; aguarde uma terminar.", "too_many_jobs", 409)
            out.mkdir(parents=True, exist_ok=True)
            job = {"id": job_id, "kind": kind, "status": "queued", "progress": 0, "step": "", "steps": [s["label"] for s in steps], "log": [],
                   "error": "", "artifacts": {}, "ingest": {}, "output_dir": str(out), "params": {k: v for k, v in params.items()}, "created_at": _now(), "finished_at": ""}
            self._save(job)
        threading.Thread(target=self._run, args=(job_id, kind, steps, params, state_data or {}), daemon=True, name=f"engine-{job_id}").start()
        return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] not in _ACTIVE:
            return job
        self._cancel.add(job_id)
        proc = self._procs.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
        return job

    @staticmethod
    def _environment(executable: str) -> dict[str, str]:
        """Process environment for a step. A tool given by absolute path is used as if its environment were activated:
        its ``bin`` goes first on PATH (QIIME 2's DADA2 plugin calls ``run_dada.R`` by name) and CONDA_PREFIX points to it."""
        env = dict(os.environ)
        path = Path(executable)
        if path.is_absolute():
            env["PATH"] = f"{path.parent}{os.pathsep}{env.get('PATH', '')}"
            if (path.parent.parent / "conda-meta").is_dir():
                env["CONDA_PREFIX"] = str(path.parent.parent)
        return env

    def _log(self, job: dict[str, Any], line: str) -> None:
        job["log"] = (job["log"] + [line.rstrip()])[-_MAX_LOG:]

    def _run(self, job_id: str, kind: str, steps: list[dict[str, Any]], params: dict[str, Any], state_data: dict[str, Any]) -> None:
        job = self.get(job_id)
        out = Path(job["output_dir"])
        with self._slots:
            job.update(status="running")
            self._save(job)
            try:
                for i, step in enumerate(steps):
                    if job_id in self._cancel:
                        raise InterruptedError
                    job.update(step=step["label"], progress=int(i / len(steps) * 90))
                    step["cmd"] = registry.resolve_cmd(step["cmd"])  # use the configured qiime / Rscript / python
                    self._log(job, f"$ {' '.join(step['cmd'])}")
                    self._save(job)
                    if step.get("script"):
                        Path(step["script_path"]).write_text(step["script"], encoding="utf-8")
                    if step.get("spec"):
                        Path(step["spec_path"]).write_text(json.dumps(step["spec"]), encoding="utf-8")
                    proc = subprocess.Popen(step["cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=out, env=self._environment(step["cmd"][0]))
                    self._procs[job_id] = proc
                    for line in proc.stdout or []:
                        self._log(job, line)
                    code = proc.wait()
                    if job_id in self._cancel:
                        raise InterruptedError
                    if code != 0:
                        raise EngineError(f"'{step['label']}' terminou com erro (código {code}). Veja o log.", "step_failed")
                job["artifacts"] = self._collect(kind, out, params, state_data)
                if params.get("ingest") and self._ingest and {"metadata", "asv_table", "taxonomy"} <= set(job["artifacts"]):
                    job["ingest"] = self._ingest(job["artifacts"])
                job.update(status="completed", progress=100, step="")
            except InterruptedError:
                job.update(status="cancelled", error="Cancelado pelo usuário.")
            except (EngineError, wf.WorkflowError, OSError, ValueError) as exc:
                job.update(status="failed", error=str(exc))
            finally:
                self._procs.pop(job_id, None)
                self._cancel.discard(job_id)
                job["finished_at"] = _now()
                self._save(job)

    def _collect(self, kind: str, out: Path, params: dict[str, Any], state_data: dict[str, Any]) -> dict[str, str]:
        if kind == "qiime2-dada2":
            paths = wf.convert_qiime_export(out, params.get("metadata") or None)
            tree = out / "export" / "tree" / "tree.nwk"
            if tree.is_file():
                paths["tree"] = str(tree)
            return paths
        if kind == "dada2-r":
            paths = {"asv_table": str(out / "asv_table.tsv"), "taxonomy": str(out / "taxonomy.tsv")}
            missing = [p for p in paths.values() if not Path(p).is_file()]
            if missing:
                raise EngineError("O DADA2 terminou sem gerar as tabelas esperadas; veja o log.", "no_output")
            meta = out / "metadata.tsv"
            if params.get("metadata") and Path(params["metadata"]).is_file():
                meta.write_bytes(Path(params["metadata"]).read_bytes())
            else:
                ids = [ln.split("\t", 1)[0] for ln in Path(paths["asv_table"]).read_text().splitlines()[1:]]
                meta.write_text("sample_id\n" + "".join(f"{s}\n" for s in ids), encoding="utf-8")
            return {**paths, "metadata": str(meta)}
        if kind == "cutadapt-trim":
            return wf.write_trimmed_manifest(out)
        if kind == "vsearch-otu":
            return wf.collapse_asv_to_otu(Path(state_data["asv"]), out / "clusters.uc", out)
        res = out / f"{kind}.tsv"
        if not res.is_file():
            raise EngineError(f"O fluxo '{kind}' terminou sem gerar resultados; veja o log.", "no_output")
        return {"results": str(res)}
