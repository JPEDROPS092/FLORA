"""Keep the active project's stage aligned with what is actually in its database.

Stages: empty → raw_downloaded → ingested → analyzed → reported.
A new ingestion replaces analysed data, so the stage goes back to ingested.
A later step never walks the stage backwards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("flora.ui.project_progress")

_RANK = {"empty": 0, "raw_downloaded": 1, "ingested": 2, "analyzed": 3, "reported": 4}
_ANALYSIS_STEPS = {"diversity", "qc", "alpha", "beta", "classify", "cluster", "rarefaction", "volcano", "stats", "ml"}
_RESET_STEPS = {"ingest", "ingest_metadata", "ingest_asv", "ingest_taxonomy", "clear"}


def _count(db, sql: str) -> int:
    try:
        return int(db.query(sql).to_polars().row(0)[0])
    except Exception:  # noqa: BLE001
        return 0


def _has_raw_files(root: Path) -> bool:
    raw = root / "raw"
    if not raw.is_dir():
        return False
    return any(path.is_file() for path in raw.rglob("*"))


def _group_names(db) -> list[str]:
    """Values of the populated grouping column, not an empty ``samples.biome``."""
    try:
        from flora.ui.handlers.explore import _group_columns

        columns = _group_columns(db)
    except Exception:  # noqa: BLE001
        return []
    if not columns:
        return []
    return [item["value"] for item in columns[0]["values"]]


def _stage_for(step: str, *, has_data: bool, has_raw: bool) -> str:
    if not has_data:
        return "raw_downloaded" if has_raw else "empty"
    if step == "report":
        return "reported"
    if step in _ANALYSIS_STEPS:
        return "analyzed"
    return "ingested"


def record_project_step(state, step: str, detail: str = "") -> str:
    """Recompute stage from the database and append ``step``. Returns the stage, or '' without an active project."""
    active = state.projects.active_id()
    if not active:
        return ""
    try:
        db = state.db
        samples = _count(db, "SELECT COUNT(*) FROM samples")
        observations = _count(db, "SELECT COUNT(*) FROM asv")
        asvs = _count(db, "SELECT COUNT(DISTINCT feature_id) FROM asv")
        groups = _group_names(db)
        project = state.projects.get(active)
        has_data = bool(samples and observations)
        stage = _stage_for(step, has_data=has_data, has_raw=_has_raw_files(state.projects.dir(active)))
        previous = _RANK.get(project.stage, 0)
        if step not in _RESET_STEPS and previous > _RANK.get(stage, 0):
            stage = project.stage
        analyses = [*project.analyses, {"step": step, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "detail": detail}]
        state.projects.update(active, {
            "stage": stage,
            "samples": samples,
            "asvs": asvs,
            "groups": groups,
            "analyses": analyses[-40:],
        })
        return stage
    except Exception:  # noqa: BLE001 - a stage update must not undo a successful analysis
        logger.warning("Could not update project stage after %s", step, exc_info=True)
        return ""
