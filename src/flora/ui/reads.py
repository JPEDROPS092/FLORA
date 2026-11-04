"""One reads threshold for preview warnings, QC and rarefaction.

When the project has no saved threshold, the value is the shallowest sample
(the same adaptive depth the Explorer uses), so a study whose deepest sample
is a few thousand reads is not judged against the old fixed cut of 10 000.
"""

from __future__ import annotations

import statistics


def configured_min_reads(db) -> int | None:
    """User-saved threshold, or None when the project has not set one."""
    try:
        frame = db.query("SELECT value FROM analysis_settings WHERE key = 'min_reads'").to_polars()
    except Exception:  # noqa: BLE001 - the settings table is created on first save
        return None
    if frame.height == 0 or frame.row(0)[0] in (None, ""):
        return None
    try:
        return max(1, int(frame.row(0)[0]))
    except (TypeError, ValueError):
        return None


def depth_profile(db) -> dict | None:
    """Per-sample read totals: min, median, max and the two candidate rarefaction depths."""
    try:
        frame = db.query("SELECT sample_id, SUM(abundance) AS depth FROM asv GROUP BY sample_id").to_polars()
    except Exception:  # noqa: BLE001
        return None
    if frame.height == 0:
        return None
    pairs = [(str(sid), int(depth)) for sid, depth in frame.iter_rows() if depth is not None]
    if not pairs:
        return None
    ordered = sorted(depth for _, depth in pairs)
    percentile_index = min(len(ordered) - 1, int(len(ordered) * 0.05))
    return {
        "min": ordered[0],
        "median": int(statistics.median(ordered)),
        "max": ordered[-1],
        "suggested": max(ordered[0], 1),
        "percentile_depth": max(int(ordered[percentile_index]), 1),
        "n": len(ordered),
        "samples": pairs,
    }


def qc_floor(profile: dict) -> int:
    """A depth cut that flags tiny libraries without failing a whole shallow study.

    The adaptive rarefaction depth is the shallowest sample, so a library of 3 reads
    would otherwise set the cut and pass. This floor sits well below the median
    (about 5–10% of it, at least 100 when the study is deep) and never above it.
    """
    median = max(int(profile["median"]), 1)
    if median >= 2000:
        floor = max(100, median // 20)
    elif median >= 200:
        floor = max(20, median // 10)
    else:
        floor = max(1, median // 5)
    return max(1, min(floor, median))


def effective_min_reads(state, explicit: int | None = None) -> int:
    """QC cut: an explicit request, else the saved setting, else :func:`qc_floor`.

    Rarefaction still uses the shallowest sample when no depth is chosen
    (:func:`plan_sampling_depth`). QC does not, so a 3-read library is a warning
    inside a study whose other samples are thousands of reads deep.
    """
    if explicit is not None and int(explicit) > 0:
        return int(explicit)
    configured = configured_min_reads(state.db)
    if configured:
        return configured
    profile = depth_profile(state.db)
    if profile:
        return qc_floor(profile)
    return 1000


def plan_sampling_depth(db, requested: int | None) -> dict:
    """Choose a rarefaction depth and list the samples it drops.

    ``requested is None`` means adaptive: the minimum sample depth, which keeps
    every sample. A saved ``min_reads`` is treated as the request. A depth no
    sample can meet raises a Portuguese error naming the maximum and the suggestion.
    """
    from flora.ui.http import UiHttpError

    profile = depth_profile(db)
    if profile is None:
        raise UiHttpError(
            "Não há contagens de ASV para rarefazer. Ingira a tabela ASV antes de calcular a diversidade.",
            code="empty_feature_matrix",
        )
    if requested is None:
        requested = configured_min_reads(db)
    source = "adaptive_min" if requested is None else "requested"
    chosen = int(profile["suggested"] if requested is None else requested)
    if chosen < 1:
        raise UiHttpError("A profundidade de rarefação precisa ser pelo menos 1 read.", code="invalid_depth")
    dropped = [sid for sid, depth in profile["samples"] if depth < chosen]
    retained = [sid for sid, depth in profile["samples"] if depth >= chosen]
    if not retained:
        raise UiHttpError(
            f"Nenhuma amostra tem pelo menos {chosen} reads (o máximo neste projeto é {profile['max']}). "
            f"Deixe a profundidade em branco para usar {profile['suggested']} (o mínimo, sem descartar amostras) "
            f"ou {profile['percentile_depth']} (profundidade que mantém cerca de 95% das amostras).",
            code="depth_too_high",
            details={
                "max_depth": profile["max"],
                "suggested": profile["suggested"],
                "percentile_depth": profile["percentile_depth"],
            },
        )
    return {
        "sampling_depth": chosen,
        "depth_source": source,
        "dropped_samples": dropped[:200],
        "dropped_count": len(dropped),
        "retained": len(retained),
        "reads": {"min": profile["min"], "median": profile["median"], "max": profile["max"]},
        "suggested_depth": profile["suggested"],
        "percentile_depth": profile["percentile_depth"],
    }
