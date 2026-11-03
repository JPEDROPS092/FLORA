"""File-backed project registry: one directory per project (isolated data)."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_ID = re.compile(r"^[0-9a-f]{12}$")


class ProjectError(Exception):
    """Invalid project operation. ``code`` maps to the HTTP error code."""

    def __init__(self, message: str, code: str = "project_error", status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Source(BaseModel):
    type: str  # synthetic | mgnify | sra | emp
    accession: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Project(BaseModel):
    id: str
    name: str
    question: str = ""
    description: str = ""
    organism: str = "bacteria"
    biome: str = ""
    marker: str = "16S"
    kind: str = "local"  # local | example | public
    synthetic: bool = False
    example_id: str = ""
    #: empty -> raw_downloaded -> ingested. Only "ingested" can be analysed.
    stage: str = "empty"
    sources: list[Source] = Field(default_factory=list)
    samples: int = 0
    asvs: int = 0
    groups: list[str] = Field(default_factory=list)
    analyses: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class ProjectRegistry:
    """CRUD over ``<root>/<id>/project.json``. Writes are atomic and lock-protected."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()

    # ---- paths -----------------------------------------------------------
    def dir(self, project_id: str) -> Path:
        if not _ID.match(project_id or ""):
            raise ProjectError("Invalid project id.", "invalid_project_id")
        return self.root / project_id

    def _file(self, project_id: str) -> Path:
        return self.dir(project_id) / "project.json"

    # ---- CRUD ------------------------------------------------------------
    def create(self, name: str, question: str = "", **fields: Any) -> Project:
        name = (name or "").strip()
        if not name:
            raise ProjectError("Project name is required.", "missing_name")
        allowed = {k: v for k, v in fields.items() if k in Project.model_fields and k not in {"id", "stage", "created_at", "updated_at"}}
        project = Project(id=uuid.uuid4().hex[:12], name=name[:120], question=(question or "").strip()[:1000], **allowed)
        with self._lock:
            (self.dir(project.id) / "raw").mkdir(parents=True, exist_ok=True)
            self._write(project)
        return project

    def get(self, project_id: str) -> Project:
        with self._lock:
            path = self._file(project_id)
            if not path.exists():
                raise ProjectError("Project not found.", "not_found", 404)
            return Project.model_validate(json.loads(path.read_text("utf-8")))

    def list(self) -> list[Project]:
        if not self.root.exists():
            return []
        found: list[Project] = []
        with self._lock:
            for child in self.root.iterdir():
                if _ID.match(child.name) and (child / "project.json").exists():
                    try:
                        found.append(self.get(child.name))
                    except (ValueError, OSError):
                        continue
        return sorted(found, key=lambda p: p.updated_at, reverse=True)

    def update(self, project_id: str, patch: dict[str, Any]) -> Project:
        with self._lock:
            project = self.get(project_id)
            data = project.model_dump()
            for key, value in patch.items():
                if key in {"name", "question", "description", "organism", "biome", "marker", "samples", "asvs", "groups", "stage", "analyses", "results", "sources"}:
                    data[key] = value
            data["updated_at"] = _now()
            updated = Project.model_validate(data)
            self._write(updated)
            return updated

    def _write(self, project: Project) -> None:
        path = self._file(project.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(project.model_dump(), indent=2), "utf-8")
        os.replace(tmp, path)

    # ---- active project --------------------------------------------------
    def active_id(self) -> str:
        try:
            value = json.loads((self.root / "active.json").read_text("utf-8")).get("id", "")
        except (OSError, ValueError):
            return ""
        return value if _ID.match(value) and self._file(value).exists() else ""

    def set_active(self, project_id: str) -> None:
        self.get(project_id)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "active.json").write_text(json.dumps({"id": project_id}), "utf-8")
