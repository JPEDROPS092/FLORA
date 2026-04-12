"""DuckDB analytics core for FLORA.

FloraDB is the central query engine between data ingestion and ML/viz layers.
All analytical operations (aggregations, feature matrices, dataset slicing)
are executed via SQL on DuckDB, with data persisted in Parquet.
"""

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.db.ingestion import ingest_biom, ingest_tsv_asv, ingest_metadata

__all__ = [
    "FloraDB",
    "initialize_schema",
    "ingest_biom",
    "ingest_tsv_asv",
    "ingest_metadata",
]
