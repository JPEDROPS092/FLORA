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


def test_status_reports_the_real_database_file_and_active_project(tmp_path):
    from types import SimpleNamespace

    class Info:
        def iter_rows(self, named=False):
            return []

    db = SimpleNamespace(table_info=lambda: Info(), path=str(tmp_path / "flora.duckdb"))
    project = SimpleNamespace(id="abc", name="Amazonia", stage="ingested")
    projects = SimpleNamespace(active_id=lambda: "abc", get=lambda _id: project)
    state = SimpleNamespace(workdir=tmp_path, config=SimpleNamespace(database=SimpleNamespace(path="x.duckdb")), db=db, projects=projects)

    payload = get_status(state)
    assert payload["db_path"].endswith("flora.duckdb") and payload["db_persistent"] is True
    assert payload["project"] == {"id": "abc", "name": "Amazonia", "stage": "ingested"}

    memory = SimpleNamespace(table_info=lambda: Info(), path=":memory:")
    state.db = memory
    assert get_status(state)["db_persistent"] is False
