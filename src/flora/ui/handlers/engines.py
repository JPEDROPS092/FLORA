"""External engine endpoints: detection, running QIIME 2 / DADA2 / ALDEx2 jobs, job status."""

from __future__ import annotations

import csv
from pathlib import Path

from flora.engines import registry
from flora.engines.jobs import EngineError, JobManager
from flora.ui.http import UiHttpError, json_success

_MANAGERS: dict[str, JobManager] = {}


def _ingest(state):
    def run(paths: dict[str, str]) -> dict:
        pipe = state.pipeline
        return {
            "samples": pipe.ingest_metadata(paths["metadata"], sample_col="sample_id"),
            "observations": pipe.ingest_asv_table(paths["asv_table"], wide_format=True),
            "taxonomy_rows": pipe.ingest_taxonomy(paths["taxonomy"]),
        }

    return run


def manager(state) -> JobManager:
    key = str(Path(state.data_dir).resolve())
    mgr = _MANAGERS.get(key)
    if mgr is None:
        mgr = _MANAGERS[key] = JobManager(Path(state.data_dir) / "engines", _ingest(state))
        mgr.recover()
    return mgr


def _wrap(exc: EngineError) -> UiHttpError:
    return UiHttpError(str(exc), status=exc.status, code=exc.code)


def list_engines(state, params=None):
    fresh = bool(params and (params.get("fresh") or [""])[0] in {"1", "true"})
    return json_success(data={"engines": registry.detect_all(fresh=fresh)})


def _export_current(state, out: Path, group_by: str) -> dict[str, str]:
    """Write the active dataset as the TSVs an R workflow reads."""
    from flora.ui.handlers.workspace import _groups_frame

    out.mkdir(parents=True, exist_ok=True)
    wide = state.db.pivot_asv(normalize=None)
    asv, meta = out / "asv_input.tsv", out / "metadata_input.tsv"
    wide.write_csv(asv, separator="\t")
    groups = _groups_frame(state.db, group_by)
    with open(meta, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["sample_id", group_by])
        for sid, g in groups.iter_rows():
            w.writerow([sid, g])
    return {"asv": str(asv), "metadata": str(meta)}


def run_engine(state, body: dict):
    kind = str(body.get("workflow") or "")
    mgr = manager(state)
    try:
        data = None
        if kind == "aldex2":
            data = _export_current(state, Path(state.data_dir) / "engines" / "_inputs", str(body.get("group_by") or ""))
        job = mgr.start(kind, {k: v for k, v in body.items() if k != "workflow"}, data)
    except EngineError as exc:
        raise _wrap(exc) from exc
    return json_success(data={"job": job})


def list_jobs(state, params=None):
    return json_success(data={"jobs": manager(state).list()})


def get_job(state, params=None):
    try:
        return json_success(data={"job": manager(state).get((params or {}).get("id", [""])[0])})
    except EngineError as exc:
        raise _wrap(exc) from exc


def cancel_job(state, body: dict):
    try:
        return json_success(data={"job": manager(state).cancel(str(body.get("id") or ""))})
    except EngineError as exc:
        raise _wrap(exc) from exc
