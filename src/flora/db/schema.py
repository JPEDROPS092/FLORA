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

# ---------------------------------------------------------------------------
# Download / ingestion catalog (source-aware data acquisition layer)
# ---------------------------------------------------------------------------
# These tables track WHAT was downloaded and FROM WHERE, independently of the
# analytical star schema above. They are populated by the download/ingest CLI
# commands and are the canonical registry of raw sequencing data per source.

_DDL_SOURCES = """
CREATE TABLE IF NOT EXISTS sources (
    source       TEXT PRIMARY KEY,   -- canonical key: 'sra','ena','mgnify','emp'
    full_name    TEXT,               -- human-readable repository name
    base_url     TEXT,               -- API / portal base URL
    description  TEXT
)
"""

_DDL_SAMPLE_CATALOG = """
CREATE TABLE IF NOT EXISTS sample_catalog (
    source            TEXT NOT NULL,          -- FK -> sources.source
    sample_accession  TEXT NOT NULL,          -- e.g. SRR7532201 / SRS.../ MGYS sample id
    study_accession   TEXT,                   -- parent study / project
    run_accession     TEXT,                   -- sequencing run (SRA/ENA)
    experiment_type   TEXT,                   -- e.g. amplicon / metagenomic (MGnify)
    library_strategy  TEXT,                   -- SRA: AMPLICON / WGS ...
    library_source    TEXT,                   -- SRA: METAGENOMIC ...
    organism          TEXT,                   -- organism label
    scientific_name   TEXT,                   -- ENA scientific_name
    tax_id            BIGINT,                  -- NCBI taxonomy id
    biome             TEXT,                    -- MGnify biome path
    ecosystem         TEXT,                    -- MGnify ecosystem
    location          TEXT,                    -- geo-loc label
    latitude          DOUBLE,
    longitude         DOUBLE,
    layout            TEXT,                    -- 'paired' | 'single'
    metadata          JSON,                    -- full source-specific metadata blob
    created_at        TIMESTAMP DEFAULT now(),
    updated_at        TIMESTAMP DEFAULT now(),
    PRIMARY KEY (source, sample_accession)
)
"""

_DDL_FILES = """
CREATE TABLE IF NOT EXISTS files (
    source            TEXT NOT NULL,
    sample_accession  TEXT NOT NULL,
    file_name         TEXT NOT NULL,
    file_path         TEXT,                    -- absolute path on local disk
    direction         TEXT,                    -- 'forward' | 'reverse' | 'single'
    file_format       TEXT,                    -- 'fastq' | 'fastq.gz' | 'biom' ...
    size_bytes        BIGINT,
    checksum          TEXT,                    -- optional content hash
    checksum_algo     TEXT,                    -- 'md5' | 'sha256'
    created_at        TIMESTAMP DEFAULT now(),
    PRIMARY KEY (source, sample_accession, file_name)
)
"""

_DDL_QUALITY_STATS = """
CREATE TABLE IF NOT EXISTS quality_stats (
    source            TEXT NOT NULL,
    sample_accession  TEXT NOT NULL,
    n_reads           BIGINT,
    n_bases           BIGINT,
    gc_content        DOUBLE,
    mean_quality      DOUBLE,
    mean_read_length  DOUBLE,
    q30_rate          DOUBLE,
    created_at        TIMESTAMP DEFAULT now(),
    PRIMARY KEY (source, sample_accession)
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
    _DDL_SOURCES,
    _DDL_SAMPLE_CATALOG,
    _DDL_FILES,
    _DDL_QUALITY_STATS,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_asv_sample ON asv(sample_id)",
    "CREATE INDEX IF NOT EXISTS idx_asv_feature ON asv(feature_id)",
    "CREATE INDEX IF NOT EXISTS idx_alpha_metric ON diversity_alpha(metric)",
    "CREATE INDEX IF NOT EXISTS idx_beta_metric ON diversity_beta(metric)",
    "CREATE INDEX IF NOT EXISTS idx_tax_phylum ON taxonomy(phylum)",
    "CREATE INDEX IF NOT EXISTS idx_tax_genus ON taxonomy(genus)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_study ON sample_catalog(study_accession)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_biome ON sample_catalog(biome)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_organism ON sample_catalog(organism)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_source ON sample_catalog(source)",
    "CREATE INDEX IF NOT EXISTS idx_files_sample ON files(source, sample_accession)",
]

# Standard catalog views for common acquisition-layer queries.
_VIEWS = {
    "v_sample_summary": """
        SELECT
            c.source,
            c.sample_accession,
            c.study_accession,
            c.organism,
            c.scientific_name,
            c.biome,
            c.ecosystem,
            c.location,
            c.layout,
            COUNT(f.file_name)              AS n_files,
            COALESCE(SUM(f.size_bytes), 0)  AS total_bytes,
            c.created_at,
            c.updated_at
        FROM sample_catalog c
        LEFT JOIN files f
            ON f.source = c.source AND f.sample_accession = c.sample_accession
        GROUP BY
            c.source, c.sample_accession, c.study_accession, c.organism,
            c.scientific_name, c.biome, c.ecosystem, c.location, c.layout,
            c.created_at, c.updated_at
    """,
    "v_study_stats": """
        SELECT
            c.source,
            c.study_accession,
            COUNT(DISTINCT c.sample_accession) AS n_samples,
            COUNT(f.file_name)                 AS n_files,
            COALESCE(SUM(f.size_bytes), 0)     AS total_bytes
        FROM sample_catalog c
        LEFT JOIN files f
            ON f.source = c.source AND f.sample_accession = c.sample_accession
        GROUP BY c.source, c.study_accession
    """,
    "v_biome_aggregation": """
        SELECT
            c.biome,
            COUNT(DISTINCT c.sample_accession) AS n_samples,
            COUNT(DISTINCT c.study_accession)  AS n_studies
        FROM sample_catalog c
        WHERE c.biome IS NOT NULL
        GROUP BY c.biome
    """,
}

# Seed rows for the known data sources (idempotent upsert).
_SOURCE_SEED = [
    ("sra", "NCBI Sequence Read Archive", "https://www.ncbi.nlm.nih.gov/sra",
     "Raw high-throughput sequencing reads (FASTQ)."),
    ("ena", "European Nucleotide Archive", "https://www.ebi.ac.uk/ena",
     "ENA portal; direct FASTQ downloads (SRA mirror)."),
    ("mgnify", "MGnify (EMBL-EBI)", "https://www.ebi.ac.uk/metagenomics",
     "Analyzed metagenomics/amplicon studies with biome metadata."),
    ("emp", "Earth Microbiome Project", "https://earthmicrobiome.org",
     "EMP feature tables and metadata via the Qiita portal."),
]


def initialize_schema(db: "FloraDB") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Create all FLORA tables, indexes, views and seed data.

    Safe to call on an existing database; all statements use
    ``CREATE TABLE/INDEX/VIEW IF NOT EXISTS`` or idempotent upserts.

    Parameters
    ----------
    db : FloraDB
        Active FloraDB connection.

    Raises
    ------
    DatabaseError
        If any DDL statement fails.
    """
    # Best-effort: ensure the JSON extension is available for the JSON column
    # and json_extract() helpers. JSON ships bundled with modern DuckDB, so
    # LOAD succeeds without network access; ignore failures gracefully.
    try:
        db.execute("LOAD json")
    except Exception:  # noqa: BLE001 - optional capability
        logger.debug("JSON extension not loaded; JSON helpers may be unavailable")

    for ddl in _ALL_DDL:
        db.execute(ddl)
    for idx in _INDEXES:
        db.execute(idx)
    for name, body in _VIEWS.items():
        db.execute(f"CREATE OR REPLACE VIEW {name} AS {body}")

    for source, full_name, base_url, description in _SOURCE_SEED:
        db.execute(
            "INSERT INTO sources (source, full_name, base_url, description) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (source) DO NOTHING",
            [source, full_name, base_url, description],
        )

    logger.info(
        "Schema initialized (%d tables, %d indexes, %d views)",
        len(_ALL_DDL), len(_INDEXES), len(_VIEWS),
    )


def drop_schema(db: "FloraDB") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Drop all FLORA tables in reverse dependency order.

    Intended for test teardown. Use with caution in production.

    Parameters
    ----------
    db : FloraDB
        Active FloraDB connection.
    """
    for view in _VIEWS:
        db.execute(f"DROP VIEW IF EXISTS {view}")
    tables = [
        "pipeline_log",
        "dim_reduction",
        "diversity_beta",
        "diversity_alpha",
        "sample_metadata",
        "asv",
        "taxonomy",
        "samples",
        "quality_stats",
        "files",
        "sample_catalog",
        "sources",
    ]
    for table in tables:
        db.execute(f"DROP TABLE IF EXISTS {table}")
    logger.warning("All FLORA tables dropped")
