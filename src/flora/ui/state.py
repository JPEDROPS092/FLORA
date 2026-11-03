"""Shared UI application state."""

from __future__ import annotations

import threading
from pathlib import Path

from flora.config.settings import FloraConfig
from flora.projects import ProjectRegistry, SyncManager


class FLORAState:
    """Singleton application state shared across HTTP handler instances.

    ``pipeline`` follows the *active project*: each project has its own directory and DuckDB
    file, so data never leaks between projects. Without an active project the legacy
    single-workdir pipeline is used.
    """

    def __init__(self, config: FloraConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir
        self._pipeline = None
        self._project_pipelines: dict[str, object] = {}
        self._lock = threading.RLock()
        self.projects = ProjectRegistry(Path(workdir) / "projects")
        self.sync = SyncManager(self.projects, self.pipeline_for)
        self.sync.recover()

    def pipeline_for(self, project_id: str):
        """Pipeline bound to ``<workdir>/projects/<id>`` with a persistent DuckDB file."""
        from flora.pipelines.main_pipeline import FLORAPipeline

        with self._lock:
            pipe = self._project_pipelines.get(project_id)
            if pipe is None:
                cfg = self.config.model_copy(deep=True)
                cfg.database.path = "flora.duckdb"
                pipe = FLORAPipeline(config=cfg, workdir=self.projects.dir(project_id))
                self._project_pipelines[project_id] = pipe
            return pipe

    @property
    def pipeline(self):
        from flora.pipelines.main_pipeline import FLORAPipeline

        active = self.projects.active_id()
        if active:
            return self.pipeline_for(active)
        with self._lock:
            if self._pipeline is None:
                self._pipeline = FLORAPipeline(config=self.config, workdir=self.workdir)
        return self._pipeline

    @property
    def db(self):
        return self.pipeline.db
