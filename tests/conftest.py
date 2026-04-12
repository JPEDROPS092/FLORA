"""Shared pytest fixtures for FLORA tests.

All database fixtures use DuckDB in-memory to avoid file system dependencies.
Synthetic datasets are generated deterministically with fixed random seeds.
"""

import numpy as np
import polars as pl
import pytest

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema


@pytest.fixture
def db():
    """In-memory DuckDB instance with initialized schema."""
    conn = FloraDB.connect(":memory:")
    initialize_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_ids():
    return [f"S{i:03d}" for i in range(20)]


@pytest.fixture
def feature_ids():
    return [f"ASV_{i:04d}" for i in range(50)]


@pytest.fixture
def asv_wide_df(sample_ids, feature_ids):
    """Wide-format ASV count table with 20 samples x 50 features."""
    rng = np.random.default_rng(42)
    counts = rng.negative_binomial(n=5, p=0.3, size=(len(sample_ids), len(feature_ids))).astype(float)
    data = {"sample_id": sample_ids}
    data.update({fid: counts[:, i].tolist() for i, fid in enumerate(feature_ids)})
    return pl.DataFrame(data)


@pytest.fixture
def asv_long_df(asv_wide_df):
    """Long-format ASV table derived from asv_wide_df."""
    feature_cols = [c for c in asv_wide_df.columns if c != "sample_id"]
    return asv_wide_df.unpivot(
        index="sample_id",
        on=feature_cols,
        variable_name="feature_id",
        value_name="abundance",
    ).filter(pl.col("abundance") > 0)


@pytest.fixture
def metadata_df(sample_ids):
    """Sample metadata with biome and location columns."""
    biomes = ["Amazon", "Cerrado", "Amazon", "Atlantic_Forest"] * 5
    return pl.DataFrame({
        "sample_id": sample_ids,
        "biome": biomes,
        "location": ["Brazil"] * 20,
        "latitude": [-3.0 + i * 0.1 for i in range(20)],
        "longitude": [-60.0 + i * 0.1 for i in range(20)],
        "sequencing_depth": [15000 + i * 500 for i in range(20)],
    })


@pytest.fixture
def taxonomy_df(feature_ids):
    """Taxonomy assignments for 50 ASVs."""
    phyla = ["Proteobacteria", "Firmicutes", "Bacteroidetes", "Actinobacteria", "Chloroflexi"]
    genera = [f"Genus_{i % 15}" for i in range(len(feature_ids))]
    return pl.DataFrame({
        "feature_id": feature_ids,
        "kingdom": ["Bacteria"] * len(feature_ids),
        "phylum": [phyla[i % len(phyla)] for i in range(len(feature_ids))],
        "class": [f"Class_{i % 8}" for i in range(len(feature_ids))],
        "order": [f"Order_{i % 10}" for i in range(len(feature_ids))],
        "family": [f"Family_{i % 12}" for i in range(len(feature_ids))],
        "genus": genera,
        "species": [f"species_{i % 20}" for i in range(len(feature_ids))],
        "confidence": [0.9 - (i % 5) * 0.05 for i in range(len(feature_ids))],
    })


@pytest.fixture
def populated_db(db, metadata_df, asv_long_df, taxonomy_df):
    """DB with samples, ASVs, and taxonomy pre-loaded."""
    db.load_dataframe("samples", metadata_df.select([
        "sample_id", "biome", "location", "latitude", "longitude", "sequencing_depth"
    ]))
    db.load_dataframe("asv", asv_long_df)
    db.load_dataframe("taxonomy", taxonomy_df)
    db.create_views()
    return db
