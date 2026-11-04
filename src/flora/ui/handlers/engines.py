"""External engine endpoints: detection, running QIIME 2 / DADA2 / ALDEx2 jobs, job status."""

from __future__ import annotations

import csv
from pathlib import Path

from flora.engines import envs, registry
from flora.engines import workflows as wf
from flora.engines.jobs import USES_PROJECT_DATA, EngineError, JobManager
from flora.ui.http import UiHttpError, json_success

_MANAGERS: dict[str, JobManager] = {}


def _ingest(state):
    def run(paths: dict[str, str]) -> dict:
        pipe = state.pipeline
        if paths.get("tree") and Path(paths["tree"]).is_file():  # lets UniFrac work right after a QIIME 2 run
            (Path(state.data_dir) / "tree.nwk").write_bytes(Path(paths["tree"]).read_bytes())
        return {
            "samples": pipe.ingest_metadata(paths["metadata"], sample_col="sample_id"),
            "observations": pipe.ingest_asv_table(paths["asv_table"], wide_format=True),
            "taxonomy_rows": pipe.ingest_taxonomy(paths["taxonomy"]),
        }

    return run


_APPLIED: dict[str, tuple[str, ...]] = {}


def _apply_config(state) -> dict[str, str]:
    """Load the saved environment once per workdir (and again after it is saved) into the registry."""
    workdir = Path(getattr(state, "workdir", None) or state.data_dir)
    config = envs.load(workdir)
    marker = tuple(sorted(config.items()))
    key = str(workdir.resolve())
    if _APPLIED.get(key) != marker:
        registry.configure(config)
        _APPLIED[key] = marker
    return config


def manager(state) -> JobManager:
    _apply_config(state)
    key = str(Path(state.data_dir).resolve())
    mgr = _MANAGERS.get(key)
    if mgr is None:
        mgr = _MANAGERS[key] = JobManager(Path(state.data_dir) / "engines", _ingest(state))
        mgr.recover()
    return mgr


def _wrap(exc: EngineError) -> UiHttpError:
    return UiHttpError(str(exc), status=exc.status, code=exc.code)


def list_engines(state, params=None):
    _apply_config(state)
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
        if kind in USES_PROJECT_DATA:
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


def job_results(state, params=None):
    """The result table of a finished R workflow (and a volcano plot when it has effect sizes)."""
    import json
    import math

    import plotly.graph_objects as go

    try:
        job = manager(state).get((params or {}).get("id", [""])[0])
    except EngineError as exc:
        raise _wrap(exc) from exc
    path = (job.get("artifacts") or {}).get("results")
    if job["status"] != "completed" or not path or not Path(path).is_file():
        raise UiHttpError("Este job ainda não tem tabela de resultados.", code="no_results", status=404)
    table = wf.parse_diff_results(Path(path))
    plot = None
    if {"diff_btw", "q"} <= set(table["columns"]):
        taxa = {r[0]: r[1] for r in state.db.query("SELECT feature_id, COALESCE(NULLIF(genus, ''), NULLIF(family, ''), NULLIF(phylum, ''), feature_id) FROM taxonomy").to_polars().iter_rows()}
        pts = []
        for r in table["rows"]:
            r["taxon"] = taxa.get(r.get("feature_id", ""), r.get("feature_id", ""))
            try:
                pts.append((float(r["diff_btw"]), -math.log10(max(float(r["q"]), 1e-300)), r["taxon"]))
            except (TypeError, ValueError):
                continue
        fig = go.Figure(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", text=[p[2] for p in pts], marker={"size": 8, "color": "#B0436A"}))
        fig.add_hline(y=-math.log10(0.05), line_dash="dot")
        fig.update_layout(margin={"t": 16, "r": 16, "b": 48, "l": 56}, xaxis={"title": "efeito (log fold change)"}, yaxis={"title": "-log10(q)"})
        plot = json.loads(fig.to_json())
    return json_success(data={"kind": job["kind"], **table, "plot": plot})


def get_environments(state, params=None):
    """Conda environments with QIIME 2 / DADA2 found on disk, the saved choice and what is in effect."""
    config = _apply_config(state)
    effective = {"qiime": registry.exe("qiime") or "", "python": registry.qiime_python() or "", "rscript": registry.exe("Rscript") or ""}
    return json_success(data={"environments": envs.discover(), "config": config, "effective": effective})


def save_environment(state, body: dict):
    """Save the executables FLORA should use for QIIME 2 (``qiime``, ``python``) and R (``rscript``)."""
    try:
        config = envs.save(Path(state.workdir), body)
    except envs.EnvError as exc:
        raise UiHttpError(str(exc), code="invalid_environment") from exc
    _APPLIED.pop(str(Path(state.workdir).resolve()), None)
    _apply_config(state)
    return json_success(data={"config": config, "engines": registry.detect_all(fresh=True)})
