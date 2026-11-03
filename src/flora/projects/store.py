"""Directory-of-JSON record store (experiments, download jobs). Atomic writes, newest first."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ID = re.compile(r"^[0-9a-f]{12}$")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RecordStore:
    """``<folder>/<id>.json`` records, each carrying a ``created_at`` ISO timestamp."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self._lock = threading.Lock()

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        rid = record.get("id", "")
        if not _ID.match(rid):
            raise ValueError("Record id must be 12 hex chars.")
        record.setdefault("created_at", now_iso())
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"{rid}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(record, indent=2, default=str), "utf-8")
            os.replace(tmp, path)
        return record

    def get(self, record_id: str) -> dict[str, Any] | None:
        if not _ID.match(record_id or ""):
            return None
        path = self.folder / f"{record_id}.json"
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.folder.exists():
            return []
        records = []
        for path in self.folder.glob("*.json"):
            try:
                records.append(json.loads(path.read_text("utf-8")))
            except (OSError, ValueError):
                continue
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]
