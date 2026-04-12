"""FLORA: Feature Learning and Omics Research Analytics.

A Python library for microbiome 16S rRNA amplicon data analysis,
combining QIIME2/DADA2 processing, DuckDB analytics, Polars-based
feature engineering, and scikit-learn/XGBoost ML pipelines.

Quick start
-----------
>>> from flora.db import FloraDB
>>> from flora.pipelines import FLORAPipeline
>>> from flora.ml import MicrobiomeClassifier

>>> pipeline = FLORAPipeline(workdir="results/")
>>> pipeline.ingest_metadata("data/metadata.tsv")
>>> pipeline.ingest_asv_table("data/asv_table.tsv", wide_format=True)
>>> pipeline.ingest_taxonomy("data/taxonomy.tsv")
>>> feature_matrix = pipeline.get_feature_matrix(normalize="clr")
"""

from flora.core.exceptions import (
    DatabaseError,
    FloraError,
    IngestionError,
    MLError,
    PipelineError,
    ValidationError,
)
from flora.core.logging import get_logger, setup_logging
from flora.config.settings import FloraConfig, load_config
from flora.db.connection import FloraDB
from flora.pipelines.main_pipeline import FLORAPipeline

__version__ = "0.1.0"
__author__ = "FLORA Contributors"

__all__ = [
    "__version__",
    "FloraError",
    "PipelineError",
    "ValidationError",
    "DatabaseError",
    "IngestionError",
    "MLError",
    "get_logger",
    "setup_logging",
    "FloraConfig",
    "load_config",
    "FloraDB",
    "FLORAPipeline",
]
