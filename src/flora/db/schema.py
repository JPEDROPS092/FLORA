"""DDL definitions and schema initialization for the FLORA DuckDB database.

The schema uses a normalized star schema:
- ``samples`` is the dimension table (one row per biological sample)
- ``asv`` is the fact table (one row per sample x feature observation)
- ``taxonomy`` maps feature IDs to taxonomic lineages
- ``diversity_alpha`` and ``diversity_beta`` store computed diversity metrics
"""

from __future__ import annotations

import logging

logger = logging.getLogger("flora.db.schema")

_DDL_SAMPLES = """
CREATE TABLE IF NOT EXISTS samples (
    sample_id        TEXT PRIMARY KEY,
    biome            TEXT,
    location         TEXT,
    latitude         DOUBLE,
    longitude        DOUBLE,
    sequencing_depth INTEGER
)
"""

_DDL_SAMPLE_METADATA = """
CREATE TABLE IF NOT EXISTS sample_metadata (
    sample_id  TEXT REFERENCES samples(sample_id),
    key        TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (sample_id, key)
)
"""

_DDL_ASV = """
CREATE TABLE IF NOT EXISTS asv (
    sample_id  TEXT REFERENCES samples(sample_id),
    feature_id TEXT NOT NULL,
    abundance  DOUBLE NOT NULL DEFAULT 0.0,
    PRIMARY KEY (sample_id, feature_id)
)
"""

_DDL_TAXONOMY = """
CREATE TABLE IF NOT EXISTS taxonomy (
    feature_id TEXT PRIMARY KEY,
    kingdom    TEXT,
    phylum     TEXT,
    class      TEXT,
    "order"    TEXT,
    family     TEXT,
    genus      TEXT,
    species    TEXT,
    confidence DOUBLE
)
"""

_DDL_DIVERSITY_ALPHA = """
CREATE TABLE IF NOT EXISTS diversity_alpha (
    sample_id      TEXT REFERENCES samples(sample_id),
    metric         TEXT NOT NULL,
    value          DOUBLE NOT NULL,
    sampling_depth INTEGER,
    PRIMARY KEY (sample_id, metric)
)
"""

_DDL_DIVERSITY_BETA = """
CREATE TABLE IF NOT EXISTS diversity_beta (
    sample_a TEXT NOT NULL,
    sample_b TEXT NOT NULL,
    metric   TEXT NOT NULL,
    distance DOUBLE NOT NULL,
    PRIMARY KEY (sample_a, sample_b, metric)
)
"""

_DDL_DIM_REDUCTION = """
CREATE TABLE IF NOT EXISTS dim_reduction (
    sample_id TEXT REFERENCES samples(sample_id),
    method    TEXT NOT NULL,
    component INTEGER NOT NULL,
    value     DOUBLE NOT NULL,
    PRIMARY KEY (sample_id, method, component)
)
"""

_DDL_PIPELINE_LOG = """
CREATE TABLE IF NOT EXISTS pipeline_log (
    run_id      TEXT NOT NULL,
    step        TEXT NOT NULL,
    status      TEXT NOT NULL,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    params      TEXT,
    message     TEXT
)
"""

_ALL_DDL = [
    _DDL_SAMPLES,
    _DDL_SAMPLE_METADATA,
    _DDL_ASV,
    _DDL_TAXONOMY,
    _DDL_DIVERSITY_ALPHA,
    _DDL_DIVERSITY_BETA,
    _DDL_DIM_REDUCTION,
    _DDL_PIPELINE_LOG,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_asv_sample ON asv(sample_id)",
    "CREATE INDEX IF NOT EXISTS idx_asv_feature ON asv(feature_id)",
    "CREATE INDEX IF NOT EXISTS idx_alpha_metric ON diversity_alpha(metric)",
    "CREATE INDEX IF NOT EXISTS idx_beta_metric ON diversity_beta(metric)",
    "CREATE INDEX IF NOT EXISTS idx_tax_phylum ON taxonomy(phylum)",
    "CREATE INDEX IF NOT EXISTS idx_tax_genus ON taxonomy(genus)",
]


def initialize_schema(db: "FloraDB") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Create all FLORA tables and indexes in the target DuckDB connection.

    Safe to call on an existing database; all statements use
    ``CREATE TABLE/INDEX IF NOT EXISTS``.

    Parameters
    ----------
    db : FloraDB
        Active FloraDB connection.

    Raises
    ------
    DatabaseError
        If any DDL statement fails.
    """
    for ddl in _ALL_DDL:
        db.execute(ddl)
    for idx in _INDEXES:
        db.execute(idx)
    logger.info("Schema and indexes initialized (%d tables, %d indexes)", len(_ALL_DDL), len(_INDEXES))


def drop_schema(db: "FloraDB") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Drop all FLORA tables in reverse dependency order.

    Intended for test teardown. Use with caution in production.

    Parameters
    ----------
    db : FloraDB
        Active FloraDB connection.
    """
    tables = [
        "pipeline_log",
        "dim_reduction",
        "diversity_beta",
        "diversity_alpha",
        "sample_metadata",
        "asv",
        "taxonomy",
        "samples",
    ]
    for table in tables:
        db.execute(f"DROP TABLE IF EXISTS {table}")
    logger.warning("All FLORA tables dropped")
