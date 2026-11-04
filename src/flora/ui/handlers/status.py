"""Status-related UI handlers."""

from __future__ import annotations

from typing import Any

from flora.ui.frontend import frontend_mode
from flora.ui.http import json_success


def _active_project(state) -> dict[str, str] | None:
    """The active project, or ``None`` (also when the state has no project registry)."""
    try:
        active = state.projects.active_id()
        if not active:
            return None
        p = state.projects.get(active)
        return {"id": p.id, "name": p.name, "stage": p.stage}
    except Exception:  # noqa: BLE001 - status must answer even when projects are unavailable
        return None


def get_status(state, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Return UI/runtime status payload."""
    try:
        info = state.db.table_info()
        tables = {row["table_name"]: int(row["row_count"]) for row in info.iter_rows(named=True)}
        db_path = getattr(state.db, "path", None) or state.config.database.path
        project = _active_project(state)
        return json_success(
            data={
                "status": "connected",
                "workdir": str(state.workdir),
                "db_path": db_path,
                "db_persistent": db_path != ":memory:",
                "project": project,
                "frontend": {"mode": frontend_mode()},
                "tables": tables,
            }
        )
    except Exception:
        return json_success(
            data={
                "status": "initialized",
                "workdir": str(state.workdir),
                "frontend": {"mode": frontend_mode()},
                "tables": {},
            }
        )
