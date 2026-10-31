"""Status-related UI handlers."""

from __future__ import annotations

from typing import Any

from flora.ui.frontend import frontend_mode
from flora.ui.http import json_success


def get_status(state, params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Return UI/runtime status payload."""
    try:
        info = state.db.table_info()
        tables = {row["table_name"]: int(row["row_count"]) for row in info.iter_rows(named=True)}
        return json_success(
            data={
                "status": "connected",
                "workdir": str(state.workdir),
                "db_path": state.config.database.path,
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
