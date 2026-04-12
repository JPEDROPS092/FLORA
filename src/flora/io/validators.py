"""Input data validators for FLORA.

Validators check file integrity and schema compliance before any pipeline
step is executed. All validators return a ValidationReport rather than
raising immediately, allowing callers to collect all issues at once.
"""

from __future__ import annotations

import gzip
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from flora.core.exceptions import ValidationError

logger = logging.getLogger("flora.io.validators")

_QIIME2_MANIFEST_COLUMNS = {"sample-id", "forward-absolute-filepath", "reverse-absolute-filepath"}
_QIIME2_MANIFEST_SE_COLUMNS = {"sample-id", "absolute-filepath"}


@dataclass
class ValidationReport:
    """Container for validation results.

    Parameters
    ----------
    errors : list of str
        Fatal issues that prevent pipeline execution.
    warnings : list of str
        Non-fatal issues that may affect results.
    stats : dict
        Summary statistics collected during validation.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        """Return True if there are no errors (warnings are allowed)."""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        """Append an error message."""
        self.errors.append(msg)
        logger.error("Validation error: %s", msg)

    def add_warning(self, msg: str) -> None:
        """Append a warning message."""
        self.warnings.append(msg)
        logger.warning("Validation warning: %s", msg)

    def raise_if_invalid(self) -> None:
        """Raise ValidationError if any errors were collected.

        Raises
        ------
        ValidationError
            If ``self.errors`` is non-empty.
        """
        if not self.valid:
            joined = "; ".join(self.errors)
            raise ValidationError(f"Validation failed: {joined}")

    def __str__(self) -> str:
        lines = [f"ValidationReport: {'PASS' if self.valid else 'FAIL'}"]
        if self.errors:
            lines.append(f"  Errors ({len(self.errors)}):")
            lines.extend(f"    - {e}" for e in self.errors)
        if self.warnings:
            lines.append(f"  Warnings ({len(self.warnings)}):")
            lines.extend(f"    - {w}" for w in self.warnings)
        if self.stats:
            lines.append("  Stats:")
            lines.extend(f"    {k}: {v}" for k, v in self.stats.items())
        return "\n".join(lines)


def validate_fastq(
    path: str | Path,
    min_reads: int = 1000,
    check_pair: str | Path | None = None,
) -> ValidationReport:
    """Validate a FASTQ or gzipped FASTQ file.

    Checks:
    - File exists and is non-empty
    - FASTQ format (4-line record structure)
    - Sequence and quality line lengths match
    - Minimum read count threshold
    - Paired read count match (if check_pair is given)

    Parameters
    ----------
    path : str or Path
        Path to FASTQ or FASTQ.gz file.
    min_reads : int
        Minimum number of reads required to pass validation.
    check_pair : str or Path, optional
        If provided, also check that this paired file has the same read count.

    Returns
    -------
    ValidationReport
        Report with any detected errors and warnings.
    """
    report = ValidationReport()
    fpath = Path(path)

    if not fpath.exists():
        report.add_error(f"File not found: {fpath}")
        return report

    if fpath.stat().st_size == 0:
        report.add_error(f"File is empty: {fpath}")
        return report

    opener = gzip.open if fpath.suffix == ".gz" else open

    read_count = 0
    format_errors = 0

    try:
        with opener(fpath, "rt") as fh:
            while True:
                header = fh.readline()
                if not header:
                    break
                seq = fh.readline().strip()
                plus = fh.readline().strip()
                qual = fh.readline().strip()

                if not header.startswith("@"):
                    format_errors += 1
                    if format_errors > 5:
                        break
                    continue

                if plus != "+":
                    format_errors += 1

                if len(seq) != len(qual):
                    format_errors += 1

                read_count += 1
                if read_count > 1_000_000:
                    report.add_warning("Read count exceeds 1M; validation sampled first 1M reads")
                    break

    except Exception as exc:
        report.add_error(f"Failed to read FASTQ file {fpath.name}: {exc}")
        return report

    report.stats["read_count"] = read_count
    report.stats["format_errors_sampled"] = format_errors

    if format_errors > 0:
        report.add_error(f"{fpath.name}: {format_errors} malformed FASTQ records detected")

    if read_count < min_reads:
        report.add_error(
            f"{fpath.name}: only {read_count} reads found (minimum: {min_reads})"
        )
    elif read_count < min_reads * 2:
        report.add_warning(f"{fpath.name}: low read count ({read_count})")

    if check_pair is not None:
        pair_report = validate_fastq(check_pair, min_reads=min_reads)
        pair_count = pair_report.stats.get("read_count", 0)
        if read_count != pair_count:
            report.add_error(
                f"Paired read count mismatch: {fpath.name}={read_count} vs "
                f"{Path(check_pair).name}={pair_count}"
            )

    return report


def validate_manifest(
    manifest_path: str | Path,
    paired_end: bool = True,
    check_files_exist: bool = True,
) -> ValidationReport:
    """Validate a QIIME2 paired-end or single-end manifest file.

    Checks:
    - Required columns present
    - No duplicate sample IDs
    - No empty sample IDs
    - Referenced FASTQ files exist (optional)

    Parameters
    ----------
    manifest_path : str or Path
        Path to the manifest TSV file.
    paired_end : bool
        If True, validate as paired-end manifest (requires reverse column).
    check_files_exist : bool
        If True, check that FASTQ file paths in the manifest exist on disk.

    Returns
    -------
    ValidationReport
        Report with any detected errors and warnings.
    """
    report = ValidationReport()
    path = Path(manifest_path)

    if not path.exists():
        report.add_error(f"Manifest file not found: {path}")
        return report

    try:
        df = pl.read_csv(str(path), separator="\t")
    except Exception as exc:
        report.add_error(f"Cannot parse manifest: {exc}")
        return report

    required = _QIIME2_MANIFEST_COLUMNS if paired_end else _QIIME2_MANIFEST_SE_COLUMNS
    missing = required - set(df.columns)
    if missing:
        report.add_error(f"Manifest missing required columns: {missing}")
        return report

    report.stats["sample_count"] = len(df)

    if df["sample-id"].null_count() > 0:
        report.add_error("Manifest contains rows with null sample-id")

    dupes = df.filter(df["sample-id"].is_duplicated())["sample-id"].to_list()
    if dupes:
        report.add_error(f"Duplicate sample IDs: {list(set(dupes))[:10]}")

    if check_files_exist:
        missing_files: list[str] = []
        col = "forward-absolute-filepath" if paired_end else "absolute-filepath"
        for fpath in df[col].drop_nulls().to_list():
            if not Path(fpath).exists():
                missing_files.append(fpath)
        if missing_files:
            n = len(missing_files)
            report.add_error(f"{n} FASTQ files referenced in manifest do not exist")

        if paired_end:
            for fpath in df["reverse-absolute-filepath"].drop_nulls().to_list():
                if not Path(fpath).exists():
                    missing_files.append(fpath)

    return report


def validate_metadata(
    metadata_path: str | Path,
    sample_col: str = "sample_id",
    required_columns: list[str] | None = None,
    max_missing_fraction: float = 0.3,
) -> ValidationReport:
    """Validate a sample metadata file.

    Checks:
    - File exists and is parseable
    - Sample ID column is present and unique
    - Required columns are present
    - Missing value fraction per column is within threshold

    Parameters
    ----------
    metadata_path : str or Path
        Path to TSV or CSV metadata file.
    sample_col : str
        Name of the sample ID column.
    required_columns : list of str, optional
        Columns that must be present.
    max_missing_fraction : float
        Maximum allowed fraction of missing values per column.

    Returns
    -------
    ValidationReport
        Report with any detected errors and warnings.
    """
    report = ValidationReport()
    path = Path(metadata_path)

    if not path.exists():
        report.add_error(f"Metadata file not found: {path}")
        return report

    sep = "\t" if path.suffix in (".tsv", ".txt") else ","
    try:
        df = pl.read_csv(str(path), separator=sep, infer_schema_length=10000)
    except Exception as exc:
        report.add_error(f"Cannot parse metadata file: {exc}")
        return report

    report.stats["row_count"] = len(df)
    report.stats["column_count"] = len(df.columns)

    if sample_col not in df.columns:
        report.add_error(f"Sample ID column '{sample_col}' not found in metadata")
        return report

    if df[sample_col].null_count() > 0:
        report.add_error(f"Sample ID column '{sample_col}' contains null values")

    dupes = df.filter(df[sample_col].is_duplicated())[sample_col].to_list()
    if dupes:
        report.add_error(f"Duplicate sample IDs in metadata: {list(set(dupes))[:10]}")

    if required_columns:
        missing = set(required_columns) - set(df.columns)
        if missing:
            report.add_error(f"Required columns missing: {missing}")

    for col in df.columns:
        missing_frac = df[col].null_count() / len(df)
        report.stats[f"missing_frac_{col}"] = round(missing_frac, 3)
        if missing_frac > max_missing_fraction:
            report.add_warning(
                f"Column '{col}' has {missing_frac:.1%} missing values "
                f"(threshold: {max_missing_fraction:.1%})"
            )

    return report
