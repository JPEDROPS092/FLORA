"""Shared UI application state."""

from __future__ import annotations

import threading
from pathlib import Path

from flora.config.settings import FloraConfig


class FLORAState:
    """Singleton application state shared across HTTP handler instances."""

    def __init__(self, config: FloraConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir
        self._pipeline = None
        self._lock = threading.Lock()

    @property
    def pipeline(self):
        from flora.pipelines.main_pipeline import FLORAPipeline

        with self._lock:
            if self._pipeline is None:
                self._pipeline = FLORAPipeline(config=self.config, workdir=self.workdir)
        return self._pipeline

    @property
    def db(self):
        return self.pipeline.db
