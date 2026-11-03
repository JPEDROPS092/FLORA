"""Reproducibility metadata shared by experiments, dashboard entries and reports."""

from __future__ import annotations

import platform
from importlib import metadata
from typing import Any

_PACKAGES = ["numpy", "polars", "duckdb", "scikit-learn", "xgboost", "plotly", "scipy"]


def package_versions() -> list[dict[str, str]]:
    found = []
    for name in _PACKAGES:
        try:
            found.append({"name": name, "version": metadata.version(name)})
        except metadata.PackageNotFoundError:
            continue
    return found


def build_provenance(
    state,
    *,
    seed: int = 0,
    parameters: list[dict[str, str]] | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    from flora import __version__

    inputs: list[str] = []
    active = state.projects.active_id()
    if active:
        try:
            for src in state.projects.get(active).sources:
                inputs.append(f"{src.type}:{src.accession}" if src.accession else src.type)
        except Exception:  # noqa: BLE001 - provenance must never break the request
            pass
    return {
        "pipeline_version": f"FLORA {__version__} · Python {platform.python_version()}",
        "seed": seed,
        "parameters": parameters or [],
        "packages": package_versions(),
        "inputs": inputs,
        "history": history or [],
    }
