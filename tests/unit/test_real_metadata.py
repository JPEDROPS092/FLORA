"""Real MGnify sample descriptions -> usable columns, and the default grouping column."""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.io.sources import _from_description, _sample_row
from flora.ui.handlers import explore


def test_descriptions_from_the_colombian_amazon_study():
    assert _from_description("soil Belén 800 – 1000 m.a.s.l forest R4 1.1.1.4") == {"substrate": "soil", "land_cover": "forest", "site": "Belén"}
    assert _from_description("litter Belén 600 – 800 m.a.s.l forest R3 2.4.3")["substrate"] == "litter"
    assert _from_description("soil Belén 400 – 600 m.a.s.l regeneration R4 1.1.8.4")["land_cover"] == "regeneration"
    assert _from_description("soil Solano pasture R2 3.4.2")["land_cover"] == "pasture" and _from_description("soil Solano pasture R2")["site"] == "Solano"


def test_descriptions_from_the_deforestation_study():
    row = _from_description("Replicate ''A'' from deforested site 3")
    assert row == {"substrate": "", "land_cover": "deforested", "site": "site 3"}
    assert _from_description("Replicate ''C'' from forest site 1")["land_cover"] == "forest"
    assert _from_description("") == {"substrate": "", "land_cover": "", "site": ""}


def test_sample_row_keeps_the_raw_text_and_cleans_nulls_and_quotes():
    row = _sample_row({"id": "ERS1", "attributes": {"sample-desc": "Replicate ''A'' from forest site 2", "sample-name": "forest", "collection-date": "None",
                                                       "latitude": -3.2, "longitude": -60.1, "environment-feature": "forest"}})
    assert row["sample_desc"] == "Replicate 'A' from forest site 2" and row["collection_date"] == "" and row["sample_name"] == "forest"
    assert row["land_cover"] == "forest" and row["site"] == "site 2" and row["latitude"] == -3.2


def _db(biome):
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    n = len(biome)
    db.load_dataframe("samples", pl.DataFrame({"sample_id": [f"S{i}" for i in range(n)], "biome": biome, "location": [None] * n, "latitude": [None] * n,
                                                "longitude": [None] * n, "sequencing_depth": [None] * n},
                                               schema_overrides={"location": pl.Utf8, "latitude": pl.Float64, "longitude": pl.Float64, "sequencing_depth": pl.Int64}))
    return db


def test_default_group_prefers_biome_then_the_first_categorical_column():
    assert explore.default_group(_db(["a", "a", "b", "b"])) == "biome"
    db = _db([None, None, None, None])
    db.load_dataframe("sample_metadata", pl.DataFrame({"sample_id": [f"S{i}" for i in range(4)], "key": ["land_cover"] * 4, "value": ["forest", "forest", "pasture", "pasture"]}))
    assert explore.default_group(db) == "land_cover"
    assert explore.default_group(FloraDB.connect(":memory:")) == "biome"  # no schema yet -> the old default
