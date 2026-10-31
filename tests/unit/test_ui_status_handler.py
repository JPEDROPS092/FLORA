"""Tests for UI status handler compatibility with GET dispatch."""

from __future__ import annotations

from flora.ui.handlers.status import get_status


def test_get_status_accepts_query_params(tmp_path):
    class DummyInfo:
        def iter_rows(self, named: bool = False):
            assert named is True
            return [{"table_name": "samples", "row_count": 3}]

    class DummyDb:
        def table_info(self):
            return DummyInfo()

    class DummyDatabaseConfig:
        path = ":memory:"

    class DummyConfig:
        database = DummyDatabaseConfig()

    class DummyState:
        workdir = tmp_path
        config = DummyConfig()
        db = DummyDb()

    payload = get_status(DummyState(), {"refresh": ["1"]})

    assert payload["success"] is True
    assert payload["status"] == "connected"
    assert payload["tables"] == {"samples": 3}
