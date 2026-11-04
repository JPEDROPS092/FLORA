"""Analysis endpoints: QC, rarefaction, alpha/beta statistics, differential abundance, MIxS, settings."""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import numpy as np
import plotly.graph_objects as go
import polars as pl

from flora.analysis import stats
from flora.ui.handlers.workspace import _groups_frame
from flora.ui.http import UiHttpError, json_success

logger = logging.getLogger("flora.ui.analysis")

_ALPHA_METRICS = ["shannon", "observed_features", "chao1", "simpson"]
_RANKS = ("phylum", "class", "order", "family", "genus")
_MAX_PERMUTATIONS = 9999
_ORGANELLE_COLS = ("kingdom", "phylum", "class", "order", "family", "genus")
_PALETTE = ["#155E53", "#D9822B", "#3B7DD8", "#B0436A", "#6B8E23", "#7A5BC0", "#2A9D8F", "#C8553D", "#5C6B73", "#A68A00"]


def _q(params: dict | None, key: str, default: str = "") -> str:
    values = (params or {}).get(key)
    return values[0] if values else default


def _int(params: dict | None, key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(_q(params, key, str(default))), hi))
    except ValueError as exc:
        raise UiHttpError(f"{key} must be an integer", code="invalid_params") from exc


def _plot(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def _need_data(db) -> None:
    try:
        n = int(db.query("SELECT COUNT(*) FROM asv").to_polars().row(0)[0])
    except Exception:  # noqa: BLE001
        n = 0
    if n == 0:
        raise UiHttpError("Esta análise precisa de dados ingeridos (metadata, tabela ASV e taxonomia).", code="empty_feature_matrix")


def _counts(db) -> tuple[list[str], list[str], np.ndarray]:
    """Raw counts as (sample_ids, feature_ids, samples x features)."""
    wide = db.pivot_asv(normalize=None)
    return wide["sample_id"].to_list(), [c for c in wide.columns if c != "sample_id"], wide.drop("sample_id").to_numpy().astype(float)


def _group_of(db, group_by: str, samples: list[str]) -> list[str]:
    frame = _groups_frame(db, group_by)
    mapping = dict(zip(frame["sample_id"].to_list(), frame["group"].to_list(), strict=True))
    return [mapping.get(s) or "" for s in samples]


def _require_groups(db, group_by: str, samples: list[str], min_groups: int = 2) -> list[str]:
    if not group_by:
        raise UiHttpError("Escolha a coluna de agrupamento (group_by).", code="missing_group_by")
    groups = _group_of(db, group_by, samples)
    if len({g for g in groups if g}) < min_groups:
        raise UiHttpError(f"A coluna '{group_by}' tem menos de {min_groups} grupos com dados.", code="insufficient_groups")
    return groups


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------
def _organelle_features(db) -> list[str]:
    cols = " OR ".join(f"lower(COALESCE(\"{c}\", '')) LIKE '%chloroplast%' OR lower(COALESCE(\"{c}\", '')) LIKE '%mitochond%'" for c in _ORGANELLE_COLS)
    try:
        return [r[0] for r in db.query(f"SELECT feature_id FROM taxonomy WHERE {cols}").to_polars().iter_rows()]
    except Exception:  # noqa: BLE001
        return []


def get_qc(state, params: dict | None = None):
    """Reads per sample, depth cut-off and chloroplast/mitochondria content."""
    db = state.db
    min_reads = _int(params, "min_reads", 1000, 0, 10**9)
    organelle = _organelle_features(db)
    rows = db.query(
        "SELECT s.sample_id, COALESCE(SUM(a.abundance), 0) AS reads, COUNT(a.feature_id) AS features "
        "FROM samples s LEFT JOIN asv a USING (sample_id) GROUP BY s.sample_id ORDER BY reads"
    ).to_polars()
    org_reads: dict[str, float] = {}
    if organelle:
        marks = ",".join("?" for _ in organelle)
        org_reads = {r[0]: float(r[1]) for r in db.query(f"SELECT sample_id, SUM(abundance) FROM asv WHERE feature_id IN ({marks}) GROUP BY sample_id", organelle).to_polars().iter_rows()}
    table = []
    for sid, reads, features in rows.iter_rows():
        pct = (org_reads.get(sid, 0.0) / reads * 100) if reads else 0.0
        status = "fail" if not reads else "warn" if reads < min_reads else "pass"
        table.append({"sample_id": sid, "reads": int(reads), "features": int(features), "organelle_pct": round(pct, 2), "status": status})
    total = sum(r["reads"] for r in table)
    org_total = sum(org_reads.values())
    summary = {
        "samples": len(table),
        "below_depth": sum(1 for r in table if r["status"] != "pass"),
        "min_reads": min_reads,
        "organelle_features": len(organelle),
        "organelle_reads_pct": round(org_total / total * 100, 2) if total else 0.0,
    }
    fig = go.Figure(go.Bar(x=[r["sample_id"] for r in table], y=[r["reads"] for r in table], marker_color=["#8E2F2F" if r["status"] != "pass" else "#155E53" for r in table]))
    if min_reads:
        fig.add_hline(y=min_reads, line_dash="dash", annotation_text=f"corte: {min_reads}")
    fig.update_layout(margin={"t": 16, "r": 16, "b": 80, "l": 56}, xaxis={"tickangle": -45, "title": "amostra"}, yaxis={"title": "reads"}, showlegend=False)
    return json_success(data={"summary": summary, "samples": table, "plot": _plot(fig)})


def apply_qc(state, body: dict):
    """Remove chloroplast/mitochondria features and/or samples below the depth cut-off. Needs ``confirm: true``."""
    db = state.db
    min_reads = int(body.get("min_reads") or 0)
    drop_organelles = bool(body.get("remove_organelles"))
    drop_low = bool(body.get("drop_low_depth")) and min_reads > 0
    confirm = body.get("confirm") is True
    if not (drop_organelles or drop_low):
        raise UiHttpError("Escolha ao menos uma ação: remove_organelles ou drop_low_depth.", code="nothing_to_do")

    plan: dict[str, Any] = {"features_removed": 0, "reads_removed": 0, "samples_removed": 0}
    organelle = _organelle_features(db) if drop_organelles else []
    if organelle:
        marks = ",".join("?" for _ in organelle)
        plan["features_removed"] = len(organelle)
        plan["reads_removed"] = int(db.query(f"SELECT COALESCE(SUM(abundance), 0) FROM asv WHERE feature_id IN ({marks})", organelle).to_polars().row(0)[0])
    low: list[str] = []
    if drop_low:
        marks = ",".join("?" for _ in organelle) or "NULL"
        low = [r[0] for r in db.query(
            f"SELECT s.sample_id FROM samples s LEFT JOIN (SELECT sample_id, SUM(abundance) r FROM asv WHERE feature_id NOT IN ({marks}) GROUP BY sample_id) a USING (sample_id) WHERE COALESCE(a.r, 0) < ?",
            [*organelle, min_reads],
        ).to_polars().iter_rows()]
        plan["samples_removed"] = len(low)
    if not confirm:
        return json_success(data={"applied": False, "plan": plan, "message": "Nada foi alterado. Envie confirm=true para aplicar."})

    db.execute("CREATE TABLE IF NOT EXISTS qc_log (ts TIMESTAMP DEFAULT now(), action TEXT, detail TEXT)")
    if organelle:
        marks = ",".join("?" for _ in organelle)
        db.execute(f"DELETE FROM asv WHERE feature_id IN ({marks})", organelle)
        db.execute(f"DELETE FROM taxonomy WHERE feature_id IN ({marks})", organelle)
    for sid in low:
        for table in ("asv", "sample_metadata", "samples"):
            db.execute(f"DELETE FROM {table} WHERE sample_id = ?", [sid])
    db.execute("INSERT INTO qc_log (action, detail) VALUES (?, ?)", ["apply_qc", json.dumps({**plan, "min_reads": min_reads, "dropped_samples": low[:200]})])
    return json_success(data={"applied": True, "plan": plan})


# ---------------------------------------------------------------------------
# Rarefaction
# ---------------------------------------------------------------------------
def get_rarefaction(state, params: dict | None = None):
    db = state.db
    _need_data(db)
    group_by = _q(params, "group_by")
    depth = _int(params, "depth", 0, 0, 10**9)
    max_samples = _int(params, "max_samples", 120, 1, 400)
    samples, _features, X = _counts(db)
    groups = _group_of(db, group_by, samples) if group_by else [""] * len(samples)
    names = sorted({g for g in groups if g}) or [""]
    color = {g: _PALETTE[i % len(_PALETTE)] for i, g in enumerate(names)}
    fig = go.Figure()
    shown: set[str] = set()
    table = []
    for i in np.argsort([-X[i].sum() for i in range(len(samples))])[:max_samples]:
        depths, rich = stats.rarefaction_curve(X[i], points=24)
        if not depths:
            continue
        g = groups[i]
        fig.add_trace(go.Scatter(x=depths, y=rich, mode="lines", name=g or "amostras", legendgroup=g, showlegend=g not in shown,
                                 line={"color": color.get(g, "#5C6B73"), "width": 1.2}, opacity=0.75, hovertemplate=f"{samples[i]}<br>%{{x}} reads → %{{y:.0f}} features<extra></extra>"))
        shown.add(g)
        total = float(X[i].sum())
        tail = stats.expected_richness(np.round(X[i]), int(total * 0.9))
        full = float((X[i] > 0).sum())
        table.append({"sample_id": samples[i], "group": g, "reads": int(total), "observed": int(full), "saturation": round(tail / full, 3) if full else 0.0})
    if depth:
        fig.add_vline(x=depth, line_dash="dash", annotation_text=f"profundidade: {depth}")
    fig.update_layout(margin={"t": 16, "r": 16, "b": 48, "l": 56}, xaxis={"title": "reads amostrados"}, yaxis={"title": "features observadas (esperado)"})
    return json_success(data={"plot": _plot(fig), "samples": table, "depth": depth,
                              "note": "Curva exata (esperança hipergeométrica), sem sorteios. Saturação = riqueza a 90% das reads ÷ riqueza total; perto de 1 indica que mais sequenciamento acrescenta pouco."})


# ---------------------------------------------------------------------------
# Alpha statistics
# ---------------------------------------------------------------------------
def get_alpha_stats(state, params: dict | None = None):
    from flora.diversity.alpha import compute_alpha_diversity

    db = state.db
    _need_data(db)
    group_by = _q(params, "group_by")
    wide = db.pivot_asv(normalize=None)
    groups = _require_groups(db, group_by, wide["sample_id"].to_list())
    alpha = compute_alpha_diversity(wide, metrics=_ALPHA_METRICS)
    tests = []
    for metric in _ALPHA_METRICS:
        by_group: dict[str, list[float]] = {}
        for g, v in zip(groups, alpha[metric].to_list(), strict=True):
            if g:
                by_group.setdefault(g, []).append(float(v))
        res = stats.kruskal_wallis(by_group)
        if res is None:
            continue
        pairs = stats.pairwise_mannwhitney(by_group)
        tests.append({"metric": metric, **res, "groups": {g: {"n": len(v), "median": float(np.median(v))} for g, v in by_group.items()}, "pairwise": pairs})
    for row, q in zip(tests, stats.bh_fdr([t["p"] for t in tests]), strict=True):
        row["q"] = q
    notes = ["Kruskal-Wallis por métrica; q = Benjamini-Hochberg entre as métricas. Pares: Mann-Whitney com BH dentro de cada métrica."]
    if not tests:
        notes.append("Nenhum teste pôde ser calculado (valores idênticos ou grupos insuficientes).")
    return json_success(data={"group_by": group_by, "tests": tests, "notes": notes})


# ---------------------------------------------------------------------------
# Beta statistics
# ---------------------------------------------------------------------------
def get_beta_stats(state, params: dict | None = None):
    db = state.db
    _need_data(db)
    metric = _q(params, "metric", "bray_curtis")
    group_by = _q(params, "group_by")
    permutations = _int(params, "permutations", 999, 99, _MAX_PERMUTATIONS)
    if metric == "unifrac":
        raise UiHttpError("UniFrac exige uma árvore filogenética (sequências dos ASVs). Gere-a com o QIIME 2 em Configurações → Motores de análise.", code="requires_tree")
    if metric not in stats.DISTANCES:
        raise UiHttpError(f"Distância desconhecida: {metric}. Use {', '.join(stats.DISTANCES)}.", code="invalid_metric")
    samples, _features, X = _counts(db)
    groups = _require_groups(db, group_by, samples)
    keep = [i for i, g in enumerate(groups) if g]
    sizes: dict[str, int] = {}
    for i in keep:
        sizes[groups[i]] = sizes.get(groups[i], 0) + 1
    notes = []
    if min(sizes.values()) < 3:
        notes.append("Há grupos com menos de 3 amostras: o poder do teste é baixo.")
    D = stats.distance_matrix(X[keep], metric)
    g = [groups[i] for i in keep]
    try:
        perm = stats.permanova(D, g, permutations=permutations)
        disp = stats.permdisp(D, g, permutations=permutations)
    except ValueError as exc:
        raise UiHttpError(str(exc), code="insufficient_groups") from exc
    if disp["p"] < 0.05:
        notes.append("PERMDISP significativo: uma PERMANOVA significativa pode refletir diferença de dispersão, não só de posição entre grupos.")
    coords, vals = stats.pcoa(D, 2)
    pos = vals[vals > 0]
    explained = [float(v / pos.sum()) for v in vals[:2]] if len(pos) else [0.0, 0.0]
    fig = go.Figure()
    for i, name in enumerate(sorted(sizes)):
        idx = [j for j, gg in enumerate(g) if gg == name]
        fig.add_trace(go.Scatter(x=coords[idx, 0], y=coords[idx, 1] if coords.shape[1] > 1 else np.zeros(len(idx)), mode="markers", name=name,
                                 text=[samples[keep[j]] for j in idx], marker={"size": 9, "color": _PALETTE[i % len(_PALETTE)]}))
    fig.update_layout(margin={"t": 16, "r": 16, "b": 48, "l": 56}, xaxis={"title": f"PCo1 ({explained[0] * 100:.1f}%)"}, yaxis={"title": f"PCo2 ({explained[1] * 100:.1f}%)"})
    return json_success(data={"metric": metric, "group_by": group_by, "permanova": perm, "permdisp": disp, "sizes": sizes, "notes": notes, "plot": _plot(fig)})


# ---------------------------------------------------------------------------
# Differential abundance (volcano)
# ---------------------------------------------------------------------------
def get_volcano(state, params: dict | None = None):
    from scipy import stats as sps

    db = state.db
    _need_data(db)
    group_by, a, b = _q(params, "group_by"), _q(params, "a"), _q(params, "b")
    rank = _q(params, "rank", "genus")
    if rank not in _RANKS:
        raise UiHttpError(f"Rank desconhecido: {rank}", code="invalid_rank")
    samples = [r[0] for r in db.query("SELECT sample_id FROM samples ORDER BY sample_id").to_polars().iter_rows()]
    groups = _require_groups(db, group_by, samples)
    levels = sorted({g for g in groups if g})
    if not a or not b:
        a, b = levels[0], levels[1]
    if a not in levels or b not in levels or a == b:
        raise UiHttpError("Escolha dois grupos diferentes e existentes (a e b).", code="invalid_contrast")
    frame = db.query(
        f"SELECT a.sample_id, COALESCE(NULLIF(t.\"{rank}\", ''), 'Não classificado') AS taxon, SUM(a.abundance) AS ab "
        "FROM asv a LEFT JOIN taxonomy t USING (feature_id) GROUP BY ALL"
    ).to_polars()
    wide = frame.pivot(on="taxon", index="sample_id", values="ab").fill_null(0)
    ids = wide["sample_id"].to_list()
    taxa = [c for c in wide.columns if c != "sample_id" and c != "Não classificado"]
    X = stats.clr(wide.select(taxa).to_numpy().astype(float))
    gmap = dict(zip(samples, groups, strict=True))
    ia = [i for i, s in enumerate(ids) if gmap.get(s) == a]
    ib = [i for i, s in enumerate(ids) if gmap.get(s) == b]
    if len(ia) < 2 or len(ib) < 2:
        raise UiHttpError("Cada grupo do contraste precisa de ao menos 2 amostras.", code="insufficient_samples")
    rows = []
    for j, taxon in enumerate(taxa):
        xa, xb = X[ia, j], X[ib, j]
        if np.ptp(np.concatenate([xa, xb])) == 0:
            continue
        p = float(sps.mannwhitneyu(xb, xa).pvalue)
        if math.isfinite(p):
            rows.append({"taxon": taxon, "log2fc": float((xb.mean() - xa.mean()) / math.log(2)), "p": p})
    for row, q in zip(rows, stats.bh_fdr([r["p"] for r in rows]), strict=True):
        row["q"] = q
        row["significant"] = bool(q < 0.05 and abs(row["log2fc"]) >= 1)
    rows.sort(key=lambda r: r["q"])
    fig = go.Figure()
    for sig, name, color in ((False, "n.s.", "#9AA7A2"), (True, "q<0,05 e |log2FC|≥1", "#B0436A")):
        pts = [r for r in rows if r["significant"] == sig]
        fig.add_trace(go.Scatter(x=[r["log2fc"] for r in pts], y=[-math.log10(max(r["q"], 1e-300)) for r in pts], mode="markers", name=name,
                                 text=[r["taxon"] for r in pts], marker={"size": 8, "color": color}, hovertemplate="%{text}<br>log2FC %{x:.2f}<extra></extra>"))
    fig.add_hline(y=-math.log10(0.05), line_dash="dot")
    fig.update_layout(margin={"t": 16, "r": 16, "b": 48, "l": 56}, xaxis={"title": f"log2 fold change ({b} vs {a})"}, yaxis={"title": "-log10(q)"})
    return json_success(data={"group_by": group_by, "a": a, "b": b, "rank": rank, "n_a": len(ia), "n_b": len(ib), "results": rows[:200], "plot": _plot(fig),
                              "method": "flora-clr-mannwhitney",
                              "notes": ["Mann-Whitney sobre valores CLR (pseudocontagem 0,5), q = Benjamini-Hochberg. É uma aproximação composicional simples; para ANCOM-BC2 ou ALDEx2 use os motores R em Configurações."]})


# ---------------------------------------------------------------------------
# MIxS metadata check
# ---------------------------------------------------------------------------
_MIXS = [
    ("collection_date", "obrigatório", ("collection_date", "date", "sampling_date")),
    ("geo_loc_name", "obrigatório", ("geo_loc_name", "country", "location")),
    ("lat_lon", "obrigatório", ("lat_lon", "latitude+longitude")),
    ("env_broad_scale", "obrigatório", ("env_broad_scale", "environment_biome", "biome")),
    ("env_local_scale", "obrigatório", ("env_local_scale", "environment_feature")),
    ("env_medium", "obrigatório", ("env_medium", "environment_material")),
    ("target_gene", "recomendado (MIMARKS)", ("target_gene", "marker", "gene")),
    ("target_subfragment", "recomendado (MIMARKS)", ("target_subfragment", "marker_region", "region")),
    ("pcr_primers", "recomendado (MIMARKS)", ("pcr_primers", "primers")),
    ("seq_meth", "recomendado (MIMARKS)", ("seq_meth", "platform", "instrument_platform")),
]


def get_mixs(state, params: dict | None = None):
    """Compare the sample metadata with MIxS core / MIMARKS fields (by name and common aliases)."""
    db = state.db
    columns = [c for c in db.query("SELECT * FROM samples LIMIT 0").to_polars().columns if c != "sample_id"]
    try:
        columns += [r[0] for r in db.query("SELECT DISTINCT key FROM sample_metadata").to_polars().iter_rows()]
    except Exception:  # noqa: BLE001
        pass
    total = int(db.query("SELECT COUNT(*) FROM samples").to_polars().row(0)[0]) or 1
    lower = {c.lower(): c for c in columns}

    def filled(col: str) -> float:
        if col in db.query("SELECT * FROM samples LIMIT 0").to_polars().columns:
            n = db.query(f'SELECT COUNT(*) FROM samples WHERE "{col}" IS NOT NULL AND CAST("{col}" AS VARCHAR) <> \'\'').to_polars().row(0)[0]
        else:
            n = db.query("SELECT COUNT(DISTINCT sample_id) FROM sample_metadata WHERE key = ? AND value IS NOT NULL AND value <> ''", [col]).to_polars().row(0)[0]
        return round(int(n) / total * 100, 1)

    fields = []
    for name, level, aliases in _MIXS:
        found, pct = "", 0.0
        for alias in aliases:
            if alias == "latitude+longitude":
                if "latitude" in lower and "longitude" in lower:
                    found, pct = "latitude + longitude", min(filled(lower["latitude"]), filled(lower["longitude"]))
                    break
            elif alias in lower:
                found, pct = lower[alias], filled(lower[alias])
                break
        fields.append({"field": name, "level": level, "column": found, "present": bool(found), "filled_pct": pct})
    required = [f for f in fields if f["level"] == "obrigatório"]
    return json_success(data={
        "fields": fields,
        "required_present": sum(1 for f in required if f["present"]),
        "required_total": len(required),
        "note": "Verificação por nome de coluna e apelidos comuns; não valida vocabulários controlados (ENVO) nem formatos de data.",
    })


# ---------------------------------------------------------------------------
# Settings (taxonomy database, recorded for the report)
# ---------------------------------------------------------------------------
_TAXONOMY_DBS = ("", "SILVA 138", "SILVA 132", "GTDB r214", "GTDB r220", "Greengenes2", "MGnify SSU (SILVA)", "Outro")


def read_settings(db) -> dict[str, str]:
    try:
        return {k: v for k, v in db.query("SELECT key, value FROM analysis_settings").to_polars().iter_rows()}
    except Exception:  # noqa: BLE001
        return {}


def get_settings(state, params: dict | None = None):
    return json_success(data={"settings": read_settings(state.db), "taxonomy_db_options": list(_TAXONOMY_DBS)})


def save_settings(state, body: dict):
    db = state.db
    db.execute("CREATE TABLE IF NOT EXISTS analysis_settings (key TEXT PRIMARY KEY, value TEXT)")
    value = str(body.get("taxonomy_db", ""))
    if value not in _TAXONOMY_DBS:
        raise UiHttpError(f"Banco taxonômico desconhecido: {value}", code="invalid_taxonomy_db")
    db.execute("DELETE FROM analysis_settings WHERE key = 'taxonomy_db'")
    db.execute("INSERT INTO analysis_settings (key, value) VALUES ('taxonomy_db', ?)", [value])
    return json_success(data={"settings": read_settings(db)})
