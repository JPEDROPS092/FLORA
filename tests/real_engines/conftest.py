"""Tests that run the *real* external tools. Each one skips itself until its tool is installed and connected
(``scripts/setup_engines.sh`` or ``flora engines connect``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flora.engines import envs, registry

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def connected_environment():
    """Use the environment saved by ``flora engines connect`` (in ./results), if any."""
    registry.configure(envs.load(REPO / "results"))
    yield
    registry.configure({})


def require(engine_id: str):
    """Skip marker for tests that need *engine_id* to be installed."""
    registry.configure(envs.load(REPO / "results"))
    return pytest.mark.skipif(registry.detect(engine_id, fresh=True) is None, reason=f"{engine_id} is not installed or connected")
