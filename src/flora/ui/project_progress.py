"""Keep the active project's stage aligned with what is actually in its database.

Stages the interface already understands: empty, raw_downloaded, ingested.
Each successful pipeline step also appends a short entry the project page can show.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("flora.ui.project_progress")


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
        groups = [row[0] for row in db.query("SELECT DISTINCT biome FROM samples WHERE biome IS NOT NULL AND biome <> '' ORDER BY 1").to_polars().iter_rows()]
        project = state.projects.get(active)
        if samples and observations:
            stage = "ingested"
        elif _has_raw_files(state.projects.dir(active)):
            stage = "raw_downloaded"
        else:
            stage = "empty"
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
