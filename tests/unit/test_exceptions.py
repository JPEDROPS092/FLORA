"""Tests for the FLORA exception hierarchy."""

import pytest

from flora.core.exceptions import (
    DatabaseError,
    FloraError,
    IngestionError,
    MLError,
    PipelineError,
    ValidationError,
)


def test_flora_error_base():
    err = FloraError("base error")
    assert "base error" in str(err)
    assert err.message == "base error"
    assert err.context == {}


def test_flora_error_with_context():
    err = FloraError("with context", context={"key": "value"})
    assert "key='value'" in str(err)


def test_pipeline_error_inherits():
    err = PipelineError("pipeline failed", step="dada2")
    assert isinstance(err, FloraError)
    assert err.step == "dada2"
    assert "step='dada2'" in str(err)


def test_validation_error_field():
    err = ValidationError("bad field", field="sample_id")
    assert isinstance(err, FloraError)
    assert err.field == "sample_id"


def test_database_error_truncates_long_query():
    long_query = "SELECT " + "a," * 300 + " FROM t"
    err = DatabaseError("query failed", query=long_query)
    assert "..." in str(err)


def test_ingestion_error_source():
    err = IngestionError("download failed", source="https://example.com/data.fastq")
    assert err.source == "https://example.com/data.fastq"


def test_ml_error():
    err = MLError("training failed", model="random_forest")
    assert err.model == "random_forest"
    assert isinstance(err, FloraError)


def test_all_errors_are_catchable_as_flora_error():
    errors = [
        PipelineError("p"),
        ValidationError("v"),
        DatabaseError("d"),
        IngestionError("i"),
        MLError("m"),
    ]
    for err in errors:
        assert isinstance(err, FloraError)
        assert isinstance(err, Exception)
