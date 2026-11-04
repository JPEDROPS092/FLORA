"""Workspace read-models for the SPA: dashboard, pipeline/QC, ingest preview and explorer summary.

Everything here is derived from the active project's DuckDB (nothing is invented); when a
piece cannot be computed the payload says so instead of returning plausible-looking numbers.
"""

from __future__ import annotations

import logging
import math
import re
import statistics
from pathlib import Path
from typing import Any

import polars as pl

from flora.ui.http import UiHttpError, json_success
from flora.ui.i18n import lang_of, tr
from flora.ui.provenance import build_provenance

logger = logging.getLogger("flora.ui.workspace")

_RANKS = ["phylum", "class", "order", "family", "genus"]
_TREE_COLS = ["kingdom", *_RANKS]
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_DEFAULT_MIN_READS = 10_000
_TREE_MAX_CHILDREN = 25


def _q(params: dict | None, key: str, default: str = "") -> str:
    values = (params or {}).get(key)
    return values[0] if values else default


def _int(params: dict | None, key: str, default: int) -> int:
    try:
        return int(_q(params, key, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Shared queries
# ---------------------------------------------------------------------------
def _groups_frame(db, group_by: str) -> pl.DataFrame:
    """``sample_id, group`` for a column of ``samples`` or a key of ``sample_metadata``."""
    if not _IDENT.match(group_by or ""):
        return pl.DataFrame({"sample_id": [], "group": []}, schema={"sample_id": pl.Utf8, "group": pl.Utf8})
    columns = db.query("SELECT * FROM samples LIMIT 0").to_polars().columns
    if group_by in columns:
        frame = db.query(f'SELECT sample_id, CAST("{group_by}" AS VARCHAR) AS "group" FROM samples').to_polars()
    else:
        frame = db.query("SELECT sample_id, value AS \"group\" FROM sample_metadata WHERE key = ?", [group_by]).to_polars()
    return frame.with_columns(pl.col("group").cast(pl.Utf8))


def _status(in_meta: bool, in_asv: bool, reads: float | None, group: str | None, min_reads: int, lang: str) -> tuple[str, list[str]]:
    issues: list[str] = []
    status = "pass"
    if not in_asv:
        issues.append(tr(lang, "qc.missing_asv"))
        status = "fail"
    elif not reads:
        issues.append(tr(lang, "qc.zero_reads"))
        status = "fail"
    elif reads < min_reads:
        issues.append(tr(lang, "qc.low_depth", n=min_reads))
        status = "warn"
    if not in_meta:
        issues.append(tr(lang, "qc.missing_metadata"))
        status = "fail"
    elif not group:
        issues.append(tr(lang, "qc.no_group"))
        status = "warn" if status == "pass" else status
    return status, issues


def _histogram(reads: list[float]) -> dict[str, Any]:
    return {
        "data": [{"type": "histogram", "x": reads, "nbinsx": 20, "marker": {"color": "#155E53"}}] if reads else [],
        "layout": {"margin": {"t": 16, "r": 16, "b": 40, "l": 48}, "showlegend": False, "bargap": 0.05},
    }


def _qc(db, group_by: str, min_reads: int, lang: str) -> dict[str, Any]:
    reads_df = db.query(
        """
        SELECT s.sample_id, COALESCE(SUM(a.abundance), 0) AS reads, COUNT(a.feature_id) AS n_obs
        FROM samples s LEFT JOIN asv a ON a.sample_id = s.sample_id
        GROUP BY s.sample_id ORDER BY s.sample_id
        """
    ).to_polars()
    groups = {r["sample_id"]: r["group"] for r in _groups_frame(db, group_by).iter_rows(named=True)}
    rows = []
    for r in reads_df.iter_rows(named=True):
        in_asv = r["n_obs"] > 0
        reads = float(r["reads"]) if in_asv else None
        group = groups.get(r["sample_id"])
        status, issues = _status(True, in_asv, reads, group, min_reads, lang)
        rows.append({
            "sample_id": r["sample_id"], "metadata_id": r["sample_id"], "group": group,
            "in_metadata": True, "in_asv": in_asv, "reads": int(reads) if reads is not None else None,
            "status": status, "issues": issues,
        })
    order = {"fail": 0, "warn": 1, "pass": 2}
    rows.sort(key=lambda row: (order[row["status"]], row["sample_id"]))
    reads_list = [row["reads"] for row in rows if row["reads"]]
    return {
        "rows": rows,
        "reads": reads_list,
        "counts": {s: sum(1 for row in rows if row["status"] == s) for s in order},
        "low_depth": sum(1 for row in rows if row["reads"] and row["reads"] < min_reads),
        "mean_reads": round(statistics.fmean(reads_list)) if reads_list else 0,
        "median_reads": round(statistics.median(reads_list)) if reads_list else 0,
        "histogram": _histogram(reads_list),
    }


def _table_counts(db) -> dict[str, int]:
    def count(sql: str) -> int:
        try:
            return int(db.query(sql).to_polars().row(0)[0])
        except Exception:  # noqa: BLE001 - missing table == empty workspace
            return 0

    return {
        "samples": count("SELECT COUNT(*) FROM samples"),
        "observations": count("SELECT COUNT(*) FROM asv"),
        "asvs": count("SELECT COUNT(DISTINCT feature_id) FROM asv"),
        "taxa": count("SELECT COUNT(*) FROM taxonomy"),
    }


def _active_project(state):
    active = state.projects.active_id()
    return state.projects.get(active) if active else None


# ---------------------------------------------------------------------------
# GET /api/dashboard
# ---------------------------------------------------------------------------
def get_dashboard(state, params: dict | None = None):
    lang = lang_of(params)
    group_by = _q(params, "group_by", "biome")
    min_reads = _int(params, "min_reads", _DEFAULT_MIN_READS)
    project = _active_project(state)

    data: dict[str, Any] = {
        "study_id": project.id if project else "workspace",
        "study_name": project.name if project else tr(lang, "dash.workspace"),
        "marker": project.marker if project else "16S",
        "project_id": project.id if project else "",
        "stage": project.stage if project else "",
        "group_by": group_by,
        "samples": 0, "asvs": 0, "groups": 0, "group_names": [],
        "quality": {"pass": 0, "warn": 0, "fail": 0, "mean_reads": 0, "median_reads": 0},
        "recent": [],
        "workdir": str(state.data_dir),
    }
    try:
        db = state.db
        counts = _table_counts(db)
        data.update(samples=counts["samples"], asvs=counts["asvs"], status="connected")
        if counts["samples"]:
            qc = _qc(db, group_by, min_reads, lang)
            names = sorted({row["group"] for row in qc["rows"] if row["group"]})
            data.update(
                groups=len(names), group_names=names,
                quality={**qc["counts"], "mean_reads": qc["mean_reads"], "median_reads": qc["median_reads"]},
            )
            data["recent"].append({
                "id": "qc", "name": tr(lang, "dash.qc_name"), "kind": "ingest", "status": "completed", "finished_at": "",
                "project_id": data["project_id"],
                "summary": tr(lang, "dash.qc_summary", p=qc["counts"]["pass"], w=qc["counts"]["warn"], f=qc["counts"]["fail"]),
                "provenance": build_provenance(state, parameters=[{"label": "min_reads", "value": str(min_reads)}]),
            })
    except Exception as exc:  # noqa: BLE001 - dashboard must degrade, not fail
        logger.warning("Dashboard degraded: %s", exc)
        data["status"] = "initialized"

    for exp in state.experiments.list(limit=5):
        data["recent"].append(_recent_from_experiment(exp, data["project_id"], lang))
    if project:
        for job in state.sync.list(project.id)[:2]:
            data["recent"].append({
                "id": job["id"], "name": tr(lang, "dash.sync_name"), "kind": "sync",
                "status": {"completed": "completed", "failed": "failed"}.get(job["status"], "running"),
                "finished_at": (job.get("finished_at") or job.get("created_at", ""))[:16].replace("T", " "),
                "project_id": project.id, "summary": job.get("message", ""),
                "provenance": build_provenance(state, history=[{"at": job.get("created_at", ""), "event": e} for e in job.get("log", [])]),
            })
    return json_success(data=data)


def _recent_from_experiment(exp: dict[str, Any], project_id: str, lang: str) -> dict[str, Any]:
    return {
        "id": exp["id"], "name": exp["name"], "kind": "ml", "status": exp["status"],
        "finished_at": exp.get("created_at", "")[:16].replace("T", " "), "project_id": project_id,
        "summary": tr(lang, "dash.ml_summary", a=f"{exp['accuracy']:.2f}", f=f"{exp['f1_macro']:.2f}") if exp["status"] == "completed" else exp.get("error", ""),
        "provenance": exp.get("provenance", {}),
    }


# ---------------------------------------------------------------------------
# GET /api/pipeline
# ---------------------------------------------------------------------------
def get_pipeline(state, params: dict | None = None):
    lang = lang_of(params)
    group_by = _q(params, "group_by", "biome")
    min_reads = _int(params, "min_reads", _DEFAULT_MIN_READS)
    db = state.db
    counts = _table_counts(db)
    steps: dict[str, Any] = {}
    try:
        log = db.query(
            """
            SELECT step, arg_max(status, started_at) AS status, CAST(MAX(started_at) AS VARCHAR) AS at,
                   arg_max(message, started_at) AS message
            FROM pipeline_log GROUP BY step
            """
        ).to_polars()
        steps = {r["step"]: {"status": r["status"], "at": r["at"], "message": r["message"] or ""} for r in log.iter_rows(named=True)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("pipeline_log unavailable: %s", exc)

    qc = _qc(db, group_by, min_reads, lang) if counts["samples"] else None
    return json_success(data={
        "ingested": counts["samples"] > 0 and counts["observations"] > 0,
        "counts": counts,
        "steps": steps,
        "qc": _preview_payload(
            columns=_metadata_columns(db), rows=qc["rows"] if qc else [], histogram=qc["histogram"] if qc else _histogram([]),
            summary={
                "matched": sum(1 for r in (qc["rows"] if qc else []) if r["in_asv"]), "metadata_only": sum(1 for r in (qc["rows"] if qc else []) if not r["in_asv"]),
                "asv_only": 0, "low_depth": qc["low_depth"] if qc else 0, "total_asvs": counts["asvs"],
            },
            warnings=[],
        ),
    })


def _metadata_columns(db) -> list[str]:
    try:
        base = [c for c in db.query("SELECT * FROM samples LIMIT 0").to_polars().columns]
        extra = [r[0] for r in db.query("SELECT DISTINCT key FROM sample_metadata ORDER BY 1").to_polars().iter_rows()]
        return base + [c for c in extra if c not in base]
    except Exception:  # noqa: BLE001
        return []


def _preview_payload(*, columns, rows, histogram, summary, warnings) -> dict[str, Any]:
    return {"columns": columns, "rows": rows, "summary": summary, "histogram": histogram, "warnings": warnings}


# ---------------------------------------------------------------------------
# POST /api/ingest/preview  (structural, nothing is written)
# ---------------------------------------------------------------------------
def _read_table(path: str, what: str, lang: str) -> pl.DataFrame:
    file = Path(path)
    if not file.is_file():
        raise UiHttpError(tr(lang, "preview.read_error", what=what, err="not found"), code="missing_file")
    sep = "\t" if file.suffix.lower() in {".tsv", ".txt"} else ","
    try:
        return pl.read_csv(file, separator=sep, infer_schema_length=2000, null_values=["", "NA"])
    except Exception as exc:  # noqa: BLE001
        raise UiHttpError(tr(lang, "preview.read_error", what=what, err=str(exc)), code="unreadable_file") from exc


def preview_ingest(state, body: dict):
    from flora.db.ingestion import asv_frame_to_long
    from flora.ui.reads import configured_min_reads

    lang = lang_of(body)
    sample_col = body.get("sample_col") or "sample_id"
    group_col = body.get("group_col") or "biome"
    explicit = body.get("min_reads")
    min_reads = int(explicit) if explicit else (configured_min_reads(state.db) or 0)
    wide = None if "wide_format" not in body else bool(body.get("wide_format"))
    warnings: list[str] = []

    meta = _read_table(body.get("metadata_path", ""), "metadata", lang)
    if sample_col not in meta.columns:
        warnings.append(tr(lang, "preview.sample_col_missing", col=sample_col))
        return json_success(data=_preview_payload(
            columns=meta.columns, rows=[], histogram=_histogram([]),
            summary={"matched": 0, "metadata_only": 0, "asv_only": 0, "low_depth": 0, "total_asvs": 0}, warnings=warnings))
    meta_ids = [str(v) for v in meta[sample_col].to_list()]
    groups = dict(zip(meta_ids, meta[group_col].cast(pl.Utf8).to_list(), strict=True)) if group_col in meta.columns else {}

    reads: dict[str, float] = {}
    total_asvs = 0
    asv_path = body.get("asv_path", "")
    if asv_path.lower().endswith(".biom"):
        warnings.append(tr(lang, "preview.biom"))
    elif asv_path:
        asv = _read_table(asv_path, "ASV", lang)
        try:
            long, _layout = asv_frame_to_long(asv, sample_col=sample_col, wide_format=wide, drop_zeros=False)
        except Exception as exc:  # noqa: BLE001 - the preview explains the file instead of failing the page
            warnings.append(tr(lang, "preview.read_error", what="ASV", err=str(exc)))
        else:
            agg = long.group_by("sample_id").agg(pl.col("abundance").sum().alias("reads"))
            reads = {str(a): float(b) for a, b in agg.iter_rows()}
            total_asvs = int(long["feature_id"].n_unique())

    if not min_reads and reads:
        min_reads = max(1, int(min(reads.values())))
    elif not min_reads:
        min_reads = _DEFAULT_MIN_READS
    if reads and min_reads > max(reads.values()):
        warnings.append(tr(lang, "preview.threshold_above_max", cut=min_reads, max=int(max(reads.values())), suggested=max(1, int(min(reads.values())))))
    suggested = max(1, int(min(reads.values()))) if reads else min_reads

    ids = list(dict.fromkeys([*meta_ids, *reads]))
    in_meta, in_asv = set(meta_ids), set(reads)
    rows = []
    for sid in ids:
        status, issues = _status(sid in in_meta, sid in in_asv, reads.get(sid), groups.get(sid), min_reads, lang) if reads or not asv_path.lower().endswith(".biom") else ("pass", [])
        rows.append({
            "sample_id": sid, "metadata_id": sid if sid in in_meta else "", "group": groups.get(sid),
            "in_metadata": sid in in_meta, "in_asv": sid in in_asv, "reads": int(reads[sid]) if sid in reads else None,
            "status": status, "issues": issues,
        })
    order = {"fail": 0, "warn": 1, "pass": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["sample_id"]))
    if reads and not (in_meta & in_asv):
        warnings.append(tr(lang, "preview.no_overlap"))
    return json_success(data=_preview_payload(
        columns=meta.columns, rows=rows, histogram=_histogram([r["reads"] for r in rows if r["reads"]]),
        summary={
            "matched": len(in_meta & in_asv), "metadata_only": len(in_meta - in_asv) if reads else 0, "asv_only": len(in_asv - in_meta),
            "low_depth": sum(1 for v in reads.values() if 0 < v < min_reads), "total_asvs": total_asvs,
            "min_reads": min_reads, "suggested_depth": suggested,
            "reads_min": int(min(reads.values())) if reads else 0,
            "reads_median": int(statistics.median(reads.values())) if reads else 0,
            "reads_max": int(max(reads.values())) if reads else 0,
        },
        warnings=warnings))


# ---------------------------------------------------------------------------
# GET /api/explore/summary
# ---------------------------------------------------------------------------
def _bh(pvalues: list[float]) -> list[float]:
    """Benjamini–Hochberg adjusted p-values."""
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: pvalues[i])
    adjusted = [0.0] * n
    running = 1.0
    for rank in range(n, 0, -1):
        idx = order[rank - 1]
        running = min(running, pvalues[idx] * n / rank)
        adjusted[idx] = running
    return adjusted


def _tree(db, rank: str, keep: set[str], total: float) -> list[dict[str, Any]]:
    cols = _TREE_COLS[: _TREE_COLS.index(rank) + 1]
    select = ", ".join(f'COALESCE(NULLIF(t."{c}", \'\'), \'?\') AS "{c}"' for c in cols)
    frame = db.query(
        f"""
        SELECT a.sample_id, {select}, SUM(a.abundance) AS ab
        FROM asv a LEFT JOIN taxonomy t ON t.feature_id = a.feature_id
        GROUP BY ALL
        """
    ).to_polars().filter(pl.col("sample_id").is_in(list(keep)))
    agg = frame.group_by(cols).agg(pl.col("ab").sum()).to_dicts()

    root: dict[str, Any] = {"children": {}}
    for row in agg:
        node = root
        path = []
        for col in cols:
            path.append(row[col])
            child = node["children"].setdefault(row[col], {"key": "|".join(path), "label": row[col], "rank": col, "ab": 0.0, "children": {}})
            child["ab"] += row["ab"]
            node = child

    def build(node: dict[str, Any]) -> list[dict[str, Any]]:
        kids = sorted(node["children"].values(), key=lambda c: c["ab"], reverse=True)[:_TREE_MAX_CHILDREN]
        out = []
        for kid in kids:
            item = {"key": kid["key"], "label": kid["label"], "rank": kid["rank"], "abundance": round(kid["ab"] / total, 6) if total else 0.0}
            sub = build(kid)
            if sub:
                item["children"] = sub
            out.append(item)
        return out

    return build(root)


def explore_summary(state, params: dict | None = None):
    from scipy import stats

    from flora.diversity.alpha import compute_alpha_diversity

    lang = lang_of(params)
    group_by = _q(params, "group_by", "biome")
    rank = _q(params, "rank", "genus")
    if rank not in _RANKS:
        raise UiHttpError(f"Unknown rank: {rank}", code="invalid_rank")
    wanted = [g for g in _q(params, "groups").split(",") if g]
    min_reads = _int(params, "min_reads", 0)
    db = state.db

    reads = {r["sample_id"]: float(r["reads"]) for r in db.query("SELECT sample_id, SUM(abundance) AS reads FROM asv GROUP BY sample_id").to_polars().iter_rows(named=True)}
    groups = {r["sample_id"]: r["group"] for r in _groups_frame(db, group_by).iter_rows(named=True)}
    keep = {sid for sid, n in reads.items() if n >= max(min_reads, 1) and (not wanted or groups.get(sid) in wanted)}
    total = sum(reads[s] for s in keep)
    out: dict[str, Any] = {
        "sample_count": len(keep), "asv_count": _table_counts(db)["asvs"], "tree": [], "comparisons": [], "differential": [], "notes": [],
    }
    if not keep:
        return json_success(data=out)

    # --- alpha diversity per group -----------------------------------------
    wide = db.pivot_asv().filter(pl.col("sample_id").is_in(list(keep)))
    alpha = compute_alpha_diversity(wide, metrics=["shannon", "observed_features"])
    per_group: dict[str, list[tuple[float, float]]] = {}
    for r in alpha.iter_rows(named=True):
        g = groups.get(r["sample_id"])
        if g:
            per_group.setdefault(g, []).append((float(r["shannon"]), float(r["observed_features"])))
    for g, vals in sorted(per_group.items()):
        sh = [v[0] for v in vals]
        out["comparisons"].append({
            "group": g, "n": len(vals), "shannon_mean": round(statistics.fmean(sh), 3),
            "shannon_sd": round(statistics.stdev(sh), 3) if len(sh) > 1 else 0.0,
            "observed_mean": round(statistics.fmean(v[1] for v in vals)),
        })

    # --- taxonomic tree ---------------------------------------------------
    out["tree"] = _tree(db, rank, keep, total)

    # --- differential abundance (Kruskal–Wallis, BH-adjusted) ---------------
    diff_rank = "phylum" if rank == "phylum" else "genus"
    members = {g: [s for s in keep if groups.get(s) == g] for g in per_group}
    members = {g: ids for g, ids in members.items() if len(ids) >= 2}
    if len(members) < 2:
        out["notes"].append(tr(lang, "explore.few_groups"))
        return json_success(data=out)
    unclassified = tr(lang, "explore.unclassified")
    frame = db.query(
        f"""
        SELECT a.sample_id, COALESCE(NULLIF(t."{diff_rank}", ''), '{unclassified}') AS taxon, SUM(a.abundance) AS ab
        FROM asv a LEFT JOIN taxonomy t ON t.feature_id = a.feature_id GROUP BY ALL
        """
    ).to_polars().filter(pl.col("sample_id").is_in(list(keep)) & (pl.col("taxon") != unclassified))
    rel: dict[str, dict[str, float]] = {}
    for r in frame.iter_rows(named=True):
        rel.setdefault(r["taxon"], {})[r["sample_id"]] = r["ab"] / reads[r["sample_id"]]
    top = sorted(rel, key=lambda tx: sum(rel[tx].values()), reverse=True)[:60]
    tested: list[dict[str, Any]] = []
    for taxon in top:
        samples = [[rel[taxon].get(s, 0.0) for s in ids] for ids in members.values()]
        try:
            p = float(stats.kruskal(*samples).pvalue)
        except ValueError:  # all values identical
            continue
        if not math.isfinite(p):
            continue
        means = {g: statistics.fmean(v) for g, v in zip(members, samples, strict=True)}
        higher = max(means, key=means.get)
        others = [m for g, m in means.items() if g != higher]
        rest = statistics.fmean(others)
        contrast_rest = next(iter(o for o in members if o != higher)) if len(members) == 2 else tr(lang, "explore.rest")
        tested.append({
            "taxon": taxon, "rank": diff_rank, "log2_fold_change": round(math.log2((means[higher] + 1e-6) / (rest + 1e-6)), 3),
            "p_value": p, "higher_in": higher, "contrast": f"{higher} vs {contrast_rest}",
        })
    for row, q in zip(tested, _bh([r["p_value"] for r in tested]), strict=True):
        row["q_value"] = q
    out["differential"] = sorted(tested, key=lambda r: r["q_value"])[:20]
    return json_success(data=out)
