"""Explorer read-models: dataset schema (what can be grouped/filtered) and paged table viewer.

Everything is derived from the active project's DuckDB; nothing is invented.
"""

from __future__ import annotations

import statistics
from typing import Any

from flora.ui.http import UiHttpError, json_success

_TABLES = ("samples", "features", "taxonomy")
_MAX_LIMIT = 200
_MAX_GROUP_VALUES = 24
_RANKS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")
_SKIP_GROUP_COLS = {"sample_id", "latitude", "longitude", "sequencing_depth"}


def _q(params: dict | None, key: str, default: str = "") -> str:
    values = (params or {}).get(key)
    return values[0] if values else default


def _count(db, sql: str, args: list | None = None) -> int:
    try:
        return int(db.query(sql, args or []).to_polars().row(0)[0])
    except Exception:  # noqa: BLE001 - a missing table means an empty workspace
        return 0


def _group_columns(db) -> list[dict[str, Any]]:
    """Categorical columns usable for grouping, with their real values and counts."""
    found: dict[str, list[tuple[str, int]]] = {}
    try:
        cols = db.query("SELECT * FROM samples LIMIT 0").to_polars().columns
    except Exception:  # noqa: BLE001
        return []
    for col in cols:
        if col in _SKIP_GROUP_COLS:
            continue
        rows = db.query(
            f'SELECT CAST("{col}" AS VARCHAR) AS v, COUNT(*) AS n FROM samples WHERE "{col}" IS NOT NULL GROUP BY 1 ORDER BY n DESC'
        ).to_polars().iter_rows()
        found[col] = [(str(v), int(n)) for v, n in rows]
    try:
        rows = db.query(
            "SELECT key, value, COUNT(*) AS n FROM sample_metadata WHERE value IS NOT NULL GROUP BY key, value ORDER BY key, n DESC"
        ).to_polars().iter_rows()
        for key, value, n in rows:
            if key not in _SKIP_GROUP_COLS and key not in found:
                found.setdefault(f"meta:{key}", []).append((str(value), int(n)))
    except Exception:  # noqa: BLE001
        pass
    out = []
    for name, values in found.items():
        if 2 <= len(values) <= _MAX_GROUP_VALUES:
            out.append({"name": name.removeprefix("meta:"), "values": [{"value": v, "count": n} for v, n in values]})
    out.sort(key=lambda c: (c["name"] != "biome", len(c["values"])))
    return out


def get_schema(state, params: dict | None = None):
    """What the loaded dataset contains: counts, read depth and the columns the user can group by."""
    db = state.db
    counts = {
        "samples": _count(db, "SELECT COUNT(*) FROM samples"),
        "asvs": _count(db, "SELECT COUNT(DISTINCT feature_id) FROM asv"),
        "observations": _count(db, "SELECT COUNT(*) FROM asv"),
        "taxa": _count(db, "SELECT COUNT(*) FROM taxonomy"),
    }
    reads: dict[str, float] = {}
    if counts["samples"]:
        try:
            totals = [float(r[0]) for r in db.query("SELECT SUM(abundance) FROM asv GROUP BY sample_id").to_polars().iter_rows()]
        except Exception:  # noqa: BLE001
            totals = []
        if totals:
            reads = {"min": min(totals), "median": statistics.median(totals), "max": max(totals)}
    project = None
    active = state.projects.active_id()
    if active:
        p = state.projects.get(active)
        project = {"id": p.id, "name": p.name, "stage": p.stage, "question": p.question, "kind": p.kind, "synthetic": p.synthetic}
    return json_success(data={"project": project, "counts": counts, "reads": reads, "group_columns": _group_columns(db)})


def get_table(state, params: dict | None = None):
    """Paged, searchable view of the dataset: samples (+ metadata), features (+ taxonomy) or taxonomy."""
    name = _q(params, "name", "samples")
    if name not in _TABLES:
        raise UiHttpError(f"Unknown table '{name}'. Use one of: {', '.join(_TABLES)}.", code="invalid_table")
    try:
        limit = max(1, min(int(_q(params, "limit", "25")), _MAX_LIMIT))
        offset = max(0, int(_q(params, "offset", "0")))
    except ValueError as exc:
        raise UiHttpError("limit and offset must be integers", code="invalid_params") from exc
    needle = f"%{_q(params, 'q').strip().lower()}%"
    db = state.db

    if name == "samples":
        meta_keys = [r[0] for r in db.query("SELECT DISTINCT key FROM sample_metadata ORDER BY key").to_polars().iter_rows()][:12]
        extras = "".join(f', MAX(CASE WHEN m.key = ? THEN m.value END) AS "{i}"' for i, _ in enumerate(meta_keys))
        sql = f"""
            SELECT s.sample_id, s.biome, s.location, COALESCE(r.reads, 0) AS reads, COALESCE(r.n_features, 0) AS n_features {extras}
            FROM samples s
            LEFT JOIN (SELECT sample_id, SUM(abundance) AS reads, COUNT(*) AS n_features FROM asv GROUP BY sample_id) r USING (sample_id)
            LEFT JOIN sample_metadata m USING (sample_id)
            WHERE lower(s.sample_id) LIKE ? OR lower(COALESCE(s.biome, '')) LIKE ? OR lower(COALESCE(s.location, '')) LIKE ?
            GROUP BY s.sample_id, s.biome, s.location, r.reads, r.n_features
            ORDER BY s.sample_id LIMIT ? OFFSET ?
        """
        args = [*meta_keys, needle, needle, needle, limit, offset]
        total = _count(db, "SELECT COUNT(*) FROM samples s WHERE lower(s.sample_id) LIKE ? OR lower(COALESCE(s.biome,'')) LIKE ? OR lower(COALESCE(s.location,'')) LIKE ?", [needle] * 3)
        frame = db.query(sql, args).to_polars()
        frame = frame.rename({str(i): k for i, k in enumerate(meta_keys)})
    elif name == "features":
        sql = """
            SELECT a.feature_id, t.phylum, t.class, t."order", t.family, t.genus, SUM(a.abundance) AS total_abundance, COUNT(*) AS prevalence
            FROM asv a LEFT JOIN taxonomy t USING (feature_id)
            WHERE lower(a.feature_id) LIKE ? OR lower(COALESCE(t.genus, '')) LIKE ? OR lower(COALESCE(t.phylum, '')) LIKE ?
            GROUP BY a.feature_id, t.phylum, t.class, t."order", t.family, t.genus
            ORDER BY total_abundance DESC LIMIT ? OFFSET ?
        """
        total = _count(db, """SELECT COUNT(DISTINCT a.feature_id) FROM asv a LEFT JOIN taxonomy t USING (feature_id)
            WHERE lower(a.feature_id) LIKE ? OR lower(COALESCE(t.genus,'')) LIKE ? OR lower(COALESCE(t.phylum,'')) LIKE ?""", [needle] * 3)
        frame = db.query(sql, [needle, needle, needle, limit, offset]).to_polars()
    else:
        sql = """
            SELECT feature_id, kingdom, phylum, class, "order", family, genus, species
            FROM taxonomy
            WHERE lower(feature_id) LIKE ? OR lower(COALESCE(genus,'')) LIKE ? OR lower(COALESCE(phylum,'')) LIKE ?
            ORDER BY feature_id LIMIT ? OFFSET ?
        """
        total = _count(db, "SELECT COUNT(*) FROM taxonomy WHERE lower(feature_id) LIKE ? OR lower(COALESCE(genus,'')) LIKE ? OR lower(COALESCE(phylum,'')) LIKE ?", [needle] * 3)
        frame = db.query(sql, [needle, needle, needle, limit, offset]).to_polars()

    rows = [["" if v is None else (round(v, 3) if isinstance(v, float) else v) for v in row] for row in frame.iter_rows()]
    return json_success(data={"name": name, "columns": frame.columns, "rows": rows, "total": total, "limit": limit, "offset": offset})
