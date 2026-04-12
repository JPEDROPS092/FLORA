"""Integration tests for the DuckDB analytics core.

All tests use in-memory DuckDB. Fixtures are defined in conftest.py.
"""

import numpy as np
import polars as pl
import pytest

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema, drop_schema


def test_db_connect_memory():
    with FloraDB.connect(":memory:") as db:
        result = db.query("SELECT 42 AS answer").to_polars()
        assert result["answer"][0] == 42


def test_schema_initialization(db):
    tables = db.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).to_polars()["table_name"].to_list()
    for t in ["samples", "asv", "taxonomy", "diversity_alpha", "diversity_beta"]:
        assert t in tables


def test_load_dataframe(db, metadata_df):
    db.load_dataframe("samples", metadata_df.select([
        "sample_id", "biome", "location", "latitude", "longitude", "sequencing_depth"
    ]))
    count = db.query("SELECT COUNT(*) AS n FROM samples").to_polars()["n"][0]
    assert count == len(metadata_df)


def test_load_parquet(db, metadata_df, tmp_path):
    parquet_path = tmp_path / "samples.parquet"
    sub = metadata_df.select([
        "sample_id", "biome", "location", "latitude", "longitude", "sequencing_depth"
    ])
    sub.write_parquet(parquet_path)
    n = db.load_parquet("samples", parquet_path)
    assert n == len(metadata_df)


def test_pivot_asv(populated_db):
    wide = populated_db.pivot_asv()
    assert "sample_id" in wide.columns
    assert len(wide.columns) > 1
    assert len(wide) > 0


def test_pivot_asv_tss(populated_db):
    wide = populated_db.pivot_asv(normalize="tss")
    feat_cols = [c for c in wide.columns if c != "sample_id"]
    row_sums = wide.select(feat_cols).sum_horizontal()
    for s in row_sums.to_list():
        assert abs(s - 1.0) < 1e-6 or s == pytest.approx(1.0, abs=1e-4)


def test_pivot_asv_clr(populated_db):
    wide = populated_db.pivot_asv(normalize="clr")
    assert "sample_id" in wide.columns


def test_aggregate_by_taxon(populated_db):
    result = populated_db.aggregate_by_taxon(level="phylum")
    assert "phylum" in result.columns
    assert "mean_abundance" in result.columns
    assert len(result) > 0


def test_aggregate_by_taxon_with_group(populated_db):
    result = populated_db.aggregate_by_taxon(level="phylum", group_by="biome")
    assert "biome" in result.columns
    assert "phylum" in result.columns


def test_aggregate_invalid_level(populated_db):
    with pytest.raises(ValueError):
        populated_db.aggregate_by_taxon(level="not_a_real_level")


def test_slice_by_biome(populated_db):
    train, test = populated_db.slice(
        train_filter="biome = 'Amazon'",
        test_filter="biome = 'Cerrado'",
    )
    assert len(train) > 0
    assert len(test) > 0


def test_create_views(populated_db):
    populated_db.create_views()
    result = populated_db.query("SELECT * FROM v_taxonomy_full LIMIT 5").to_polars()
    assert len(result) >= 0


def test_query_result_to_pandas(populated_db):
    pdf = populated_db.query("SELECT * FROM samples LIMIT 3").to_pandas()
    assert len(pdf) == 3


def test_query_result_to_arrow(populated_db):
    table = populated_db.query("SELECT * FROM samples LIMIT 3").to_arrow()
    assert table.num_rows == 3


def test_query_result_to_parquet(populated_db, tmp_path):
    out = tmp_path / "test.parquet"
    populated_db.query("SELECT * FROM samples").to_parquet(out)
    assert out.exists()
    loaded = pl.read_parquet(out)
    assert len(loaded) > 0


def test_drop_schema(db):
    drop_schema(db)
    tables = db.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).to_polars()["table_name"].to_list()
    for t in ["samples", "asv", "taxonomy"]:
        assert t not in tables


def test_table_info(populated_db):
    info = populated_db.table_info()
    assert "table_name" in info.columns
