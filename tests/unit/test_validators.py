"""Tests for IO validators."""

import gzip
import tempfile
from pathlib import Path

import polars as pl
import pytest

from flora.io.validators import (
    ValidationReport,
    validate_fastq,
    validate_manifest,
    validate_metadata,
)


def write_fastq(path: Path, n_reads: int = 100, corrupt: bool = False) -> None:
    with open(path, "w") as fh:
        for i in range(n_reads):
            fh.write(f"@read_{i}\n")
            fh.write("ACGTACGTACGT\n")
            if corrupt and i == 5:
                fh.write("BAD_LINE\n")
            else:
                fh.write("+\n")
            fh.write("IIIIIIIIIIII\n")


def test_validation_report_valid():
    r = ValidationReport()
    assert r.valid
    r.add_error("oops")
    assert not r.valid


def test_validation_report_raise_if_invalid():
    from flora.core.exceptions import ValidationError

    r = ValidationReport()
    r.add_error("bad")
    with pytest.raises(ValidationError):
        r.raise_if_invalid()


def test_validate_fastq_valid():
    with tempfile.NamedTemporaryFile(suffix=".fastq", delete=False) as f:
        path = Path(f.name)
    write_fastq(path, n_reads=50)
    report = validate_fastq(path, min_reads=10)
    assert report.valid
    assert report.stats["read_count"] == 50
    path.unlink()


def test_validate_fastq_missing_file():
    report = validate_fastq("/nonexistent/reads.fastq")
    assert not report.valid
    assert any("not found" in e for e in report.errors)


def test_validate_fastq_low_read_count():
    with tempfile.NamedTemporaryFile(suffix=".fastq", delete=False) as f:
        path = Path(f.name)
    write_fastq(path, n_reads=5)
    report = validate_fastq(path, min_reads=100)
    assert not report.valid
    path.unlink()


def test_validate_manifest_valid():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n")
        f.write("S1\t/tmp/r1.fastq\t/tmp/r2.fastq\n")
        path = Path(f.name)
    report = validate_manifest(path, check_files_exist=False)
    assert report.valid
    path.unlink()


def test_validate_manifest_missing_column():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("sample-id\tforward-absolute-filepath\n")
        f.write("S1\t/tmp/r1.fastq\n")
        path = Path(f.name)
    report = validate_manifest(path, check_files_exist=False)
    assert not report.valid
    path.unlink()


def test_validate_manifest_duplicate_ids():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n")
        f.write("S1\t/tmp/r1.fastq\t/tmp/r2.fastq\n")
        f.write("S1\t/tmp/r3.fastq\t/tmp/r4.fastq\n")
        path = Path(f.name)
    report = validate_manifest(path, check_files_exist=False)
    assert not report.valid
    assert any("Duplicate" in e for e in report.errors)
    path.unlink()


def test_validate_metadata_valid():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("sample_id\tbiome\tlocation\n")
        f.write("S1\tAmazon\tBrazil\n")
        f.write("S2\tCerrado\tBrazil\n")
        path = Path(f.name)
    report = validate_metadata(path)
    assert report.valid
    assert report.stats["row_count"] == 2
    path.unlink()


def test_validate_metadata_missing_sample_col():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("biome\tlocation\n")
        f.write("Amazon\tBrazil\n")
        path = Path(f.name)
    report = validate_metadata(path)
    assert not report.valid
    path.unlink()


def test_validate_metadata_missing_required_column():
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write("sample_id\tbiome\n")
        f.write("S1\tAmazon\n")
        path = Path(f.name)
    report = validate_metadata(path, required_columns=["latitude"])
    assert not report.valid
    assert any("latitude" in e for e in report.errors)
    path.unlink()
