"""Explorer schema and table viewer against a real in-memory DuckDB."""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.ui.handlers import explore
from flora.ui.http import UiHttpError


@pytest.fixture()
def state():
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    db.load_dataframe("samples", pl.DataFrame({
        "sample_id": ["S1", "S2", "S3", "S4"], "biome": ["Amazon", "Amazon", "Cerrado", "Cerrado"],
        "location": ["BR", "BR", "BR", "BR"], "latitude": [None] * 4, "longitude": [None] * 4, "sequencing_depth": [None] * 4,
    }, schema_overrides={"latitude": pl.Float64, "longitude": pl.Float64, "sequencing_depth": pl.Int64}))
    db.load_dataframe("sample_metadata", pl.DataFrame({"sample_id": ["S1", "S2", "S3", "S4"], "key": ["host"] * 4, "value": ["a", "b", "a", "b"]}))
    db.load_dataframe("asv", pl.DataFrame({
        "sample_id": ["S1", "S1", "S2", "S3", "S4"], "feature_id": ["A1", "A2", "A1", "A2", "A1"], "abundance": [5.0, 3.0, 2.0, 7.0, 1.0],
    }))
    db.load_dataframe("taxonomy", pl.DataFrame({
        "feature_id": ["A1", "A2"], "kingdom": ["Bacteria"] * 2, "phylum": ["Proteobacteria", "Firmicutes"], "class": ["x", "y"],
        "order": ["o", "p"], "family": ["f", "g"], "genus": ["Gen1", "Gen2"], "species": [None, None], "confidence": [None, None],
    }, schema_overrides={"species": pl.Utf8, "confidence": pl.Float64}))
    projects = SimpleNamespace(active_id=lambda: None)
    return SimpleNamespace(db=db, projects=projects)


def test_schema_lists_real_group_columns(state):
    out = explore.get_schema(state)
    assert out["counts"] == {"samples": 4, "asvs": 2, "observations": 5, "taxa": 2}
    names = [c["name"] for c in out["group_columns"]]
    assert names[0] == "biome" and "host" in names and "location" not in names  # location has a single value
    assert {v["value"]: v["count"] for v in out["group_columns"][0]["values"]} == {"Amazon": 2, "Cerrado": 2}
    assert out["reads"]["max"] == 8.0 and out["project"] is None


def test_table_samples_with_metadata_and_search(state):
    out = explore.get_table(state, {"name": ["samples"], "q": ["cerrado"]})
    assert out["total"] == 2 and "host" in out["columns"] and out["rows"][0][0] == "S3"


def test_table_features_ordered_by_abundance_and_paged(state):
    out = explore.get_table(state, {"name": ["features"], "limit": ["1"]})
    assert out["total"] == 2 and len(out["rows"]) == 1 and out["rows"][0][0] == "A2"  # A2 sums 10 vs A1 8
    second = explore.get_table(state, {"name": ["features"], "limit": ["1"], "offset": ["1"]})
    assert second["rows"][0][0] == "A1"


def test_table_rejects_unknown_name_and_bad_numbers(state):
    with pytest.raises(UiHttpError):
        explore.get_table(state, {"name": ["pg_catalog"]})
    with pytest.raises(UiHttpError):
        explore.get_table(state, {"name": ["samples"], "limit": ["x"]})


def test_empty_workspace(state):
    empty = FloraDB.connect(":memory:")
    initialize_schema(empty)
    out = explore.get_schema(SimpleNamespace(db=empty, projects=state.projects))
    assert out["counts"]["samples"] == 0 and out["group_columns"] == []
