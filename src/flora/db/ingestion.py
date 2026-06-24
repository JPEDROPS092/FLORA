"""Data ingestion utilities: BIOM, TSV ASV tables, and metadata into DuckDB.

All ingestion functions convert source data to Polars DataFrames and load
them via FloraDB.load_dataframe(). Intermediate Parquet files are written
when a parquet_dir is specified, enabling re-use without re-parsing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pyarrow.parquet as pq

from flora.core.exceptions import IngestionError, ValidationError

if TYPE_CHECKING:
    from flora.db.connection import FloraDB

logger = logging.getLogger("flora.db.ingestion")


def ingest_biom(
    db: "FloraDB",
    biom_path: str | Path,
    parquet_dir: str | Path | None = None,
) -> int:
    """Ingest a BIOM feature table into the DuckDB ``asv`` table.

    The BIOM file is converted to long format (sample_id, feature_id,
    abundance) before insertion. Samples referenced must already exist in
    the ``samples`` table.

    Parameters
    ----------
    db : FloraDB
        Active database connection with initialized schema.
    biom_path : str or Path
        Path to the ``.biom`` file.
    parquet_dir : str or Path, optional
        If provided, write the long-format Parquet to this directory for
        caching. The filename is derived from the BIOM file name.

    Returns
    -------
    int
        Number of (sample, feature) observation rows inserted.

    Raises
    ------
    IngestionError
        If the BIOM file cannot be parsed or inserted.
    FileNotFoundError
        If ``biom_path`` does not exist.
    """
    path = Path(biom_path)
    if not path.exists():
        raise FileNotFoundError(f"BIOM file not found: {path}")

    try:
        import biom
    except ImportError as exc:
        raise IngestionError(
            "biom-format package is required for BIOM ingestion. "
            "Install it with: pip install biom-format",
            source=str(path),
        ) from exc

    try:
        table = biom.load_table(str(path))
    except Exception as exc:
        raise IngestionError(f"Failed to parse BIOM file: {exc}", source=str(path)) from exc

    rows = []
    for feature_id, sample_id, abundance in table.iter_data(dense=True, axis="sample"):
        if abundance > 0:
            rows.append(
                {"sample_id": str(sample_id), "feature_id": str(feature_id), "abundance": float(abundance)}
            )

    if not rows:
        logger.warning("BIOM file %s produced 0 non-zero observations", path)
        return 0

    df = pl.DataFrame(rows, schema={"sample_id": pl.Utf8, "feature_id": pl.Utf8, "abundance": pl.Float64})

    if parquet_dir is not None:
        pdir = Path(parquet_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        out = pdir / f"{path.stem}_asv.parquet"
        df.write_parquet(out)
        logger.debug("ASV Parquet cached at %s", out)

    count = db.load_dataframe("asv", df)
    logger.info("Ingested %d ASV observations from %s", count, path.name)
    return count


def ingest_tsv_asv(
    db: "FloraDB",
    tsv_path: str | Path,
    sample_col: str = "sample_id",
    feature_col: str = "feature_id",
    abundance_col: str = "abundance",
    wide_format: bool = False,
    parquet_dir: str | Path | None = None,
) -> int:
    """Ingest a TSV ASV table into the DuckDB ``asv`` table.

    Supports both long format (sample_id, feature_id, abundance) and
    wide format (samples as rows, features as columns).

    Parameters
    ----------
    db : FloraDB
        Active database connection.
    tsv_path : str or Path
        Path to the TSV file.
    sample_col : str
        Column name for sample IDs (long format or index column for wide).
    feature_col : str
        Column name for feature IDs (long format only).
    abundance_col : str
        Column name for abundance values (long format only).
    wide_format : bool
        If True, the TSV is wide (samples x features). It will be melted
        to long format before insertion.
    parquet_dir : str or Path, optional
        Cache long-format data as Parquet.

    Returns
    -------
    int
        Number of rows inserted.

    Raises
    ------
    IngestionError
        If parsing or insertion fails.
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(tsv_path)
    if not path.exists():
        raise FileNotFoundError(f"TSV file not found: {path}")

    try:
        df = pl.read_csv(str(path), separator="\t", infer_schema_length=10000)
    except Exception as exc:
        raise IngestionError(f"Failed to read TSV file: {exc}", source=str(path)) from exc

    if wide_format:
        value_vars = [c for c in df.columns if c != sample_col]
        df = df.unpivot(
            index=sample_col,
            on=value_vars,
            variable_name="feature_id",
            value_name="abundance",
        ).rename({sample_col: "sample_id"})
    else:
        required = {sample_col, feature_col, abundance_col}
        missing = required - set(df.columns)
        if missing:
            raise ValidationError(
                f"TSV missing required columns: {missing}",
                context={"file": str(path)},
            )
        df = df.select([
            pl.col(sample_col).alias("sample_id"),
            pl.col(feature_col).alias("feature_id"),
            pl.col(abundance_col).cast(pl.Float64).alias("abundance"),
        ])

    df = df.filter(pl.col("abundance") > 0)

    if parquet_dir is not None:
        pdir = Path(parquet_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        out = pdir / f"{path.stem}_asv.parquet"
        df.write_parquet(out)

    count = db.load_dataframe("asv", df)
    logger.info("Ingested %d ASV observations from TSV %s", count, path.name)
    return count


def ingest_metadata(
    db: "FloraDB",
    metadata_path: str | Path,
    sample_col: str = "sample_id",
    parquet_dir: str | Path | None = None,
) -> int:
    """Ingest sample metadata into the DuckDB ``samples`` table.

    Standard columns (biome, location, latitude, longitude,
    sequencing_depth) are mapped directly. All remaining columns are
    inserted into the ``sample_metadata`` key-value store.

    Parameters
    ----------
    db : FloraDB
        Active database connection.
    metadata_path : str or Path
        Path to TSV or CSV metadata file.
    sample_col : str
        Name of the column containing sample IDs.
    parquet_dir : str or Path, optional
        Cache ingested data as Parquet.

    Returns
    -------
    int
        Number of sample rows inserted into the ``samples`` table.

    Raises
    ------
    IngestionError
        If parsing or insertion fails.
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(metadata_path)
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    sep = "\t" if path.suffix in (".tsv", ".txt") else ","
    try:
        df = pl.read_csv(str(path), separator=sep, infer_schema_length=10000)
    except Exception as exc:
        raise IngestionError(f"Failed to read metadata file: {exc}", source=str(path)) from exc

    if sample_col not in df.columns:
        raise ValidationError(
            f"Metadata file missing sample column '{sample_col}'",
            field=sample_col,
            context={"columns": df.columns},
        )

    df = df.rename({sample_col: "sample_id"})

    standard_cols = {
        "biome": pl.Utf8,
        "location": pl.Utf8,
        "latitude": pl.Float64,
        "longitude": pl.Float64,
        "sequencing_depth": pl.Int64,
    }

    samples_data: dict[str, list] = {"sample_id": df["sample_id"].to_list()}
    for col, dtype in standard_cols.items():
        if col in df.columns:
            samples_data[col] = df[col].cast(dtype, strict=False).to_list()
        else:
            samples_data[col] = [None] * len(df)

    samples_df = pl.DataFrame(samples_data)

    if parquet_dir is not None:
        pdir = Path(parquet_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        samples_df.write_parquet(pdir / "samples.parquet")

    count = db.load_dataframe("samples", samples_df)

    extra_cols = [c for c in df.columns if c not in standard_cols and c != "sample_id"]
    if extra_cols:
        kv_rows: list[dict] = []
        for row in df.select(["sample_id"] + extra_cols).iter_rows(named=True):
            sid = row["sample_id"]
            for col in extra_cols:
                val = row.get(col)
                if val is not None:
                    kv_rows.append({"sample_id": sid, "key": col, "value": str(val)})

        if kv_rows:
            kv_df = pl.DataFrame(kv_rows, schema={"sample_id": pl.Utf8, "key": pl.Utf8, "value": pl.Utf8})
            db.load_dataframe("sample_metadata", kv_df)
            logger.debug("Inserted %d extra metadata key-value pairs", len(kv_rows))

    logger.info("Ingested %d samples from %s", count, path.name)
    return count


def ingest_taxonomy(
    db: "FloraDB",
    taxonomy_path: str | Path,
    parquet_dir: str | Path | None = None,
) -> int:
    """Ingest a taxonomy assignment file into the DuckDB ``taxonomy`` table.

    Expected columns: feature_id and one or more of kingdom, phylum, class,
    order, family, genus, species. A ``confidence`` column is optional.
    Also accepts QIIME2-style ``Taxon`` string columns (semicolon-separated).

    Parameters
    ----------
    db : FloraDB
        Active database connection.
    taxonomy_path : str or Path
        Path to TSV taxonomy file.
    parquet_dir : str or Path, optional
        Cache ingested data as Parquet.

    Returns
    -------
    int
        Number of taxonomy rows inserted.

    Raises
    ------
    IngestionError
        If parsing fails.
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(taxonomy_path)
    if not path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {path}")

    try:
        df = pl.read_csv(str(path), separator="\t", infer_schema_length=10000)
    except Exception as exc:
        raise IngestionError(f"Failed to read taxonomy file: {exc}", source=str(path)) from exc

    if "feature-id" in df.columns:
        df = df.rename({"feature-id": "feature_id"})
    if "Feature ID" in df.columns:
        df = df.rename({"Feature ID": "feature_id"})

    if "Taxon" in df.columns:
        df = _parse_qiime2_taxon(df)

    ranks = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    for rank in ranks:
        if rank not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(rank))

    if "confidence" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("confidence"))

    df = df.select(["feature_id"] + ranks + ["confidence"])

    if parquet_dir is not None:
        pdir = Path(parquet_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        df.write_parquet(pdir / "taxonomy.parquet")

    count = db.load_dataframe("taxonomy", df)
    logger.info("Ingested %d taxonomy assignments from %s", count, path.name)
    return count


def _parse_qiime2_taxon(df: pl.DataFrame) -> pl.DataFrame:
    """Parse QIIME2-style semicolon-separated Taxon strings into rank columns.

    QIIME2 taxonomy strings follow the pattern:
    ``d__Bacteria; p__Proteobacteria; c__Gammaproteobacteria; ...``

    Parameters
    ----------
    df : polars.DataFrame
        DataFrame with a ``Taxon`` column.

    Returns
    -------
    polars.DataFrame
        DataFrame with individual rank columns added.
    """
    prefix_to_rank = {
        "d__": "kingdom",
        "k__": "kingdom",
        "p__": "phylum",
        "c__": "class",
        "o__": "order",
        "f__": "family",
        "g__": "genus",
        "s__": "species",
    }

    def parse_taxon(taxon: str) -> dict[str, str | None]:
        result: dict[str, str | None] = {r: None for r in prefix_to_rank.values()}
        if not taxon:
            return result
        for part in taxon.split(";"):
            part = part.strip()
            for prefix, rank in prefix_to_rank.items():
                if part.startswith(prefix):
                    val = part[len(prefix):].strip()
                    result[rank] = val if val else None
                    break
        return result

    parsed = [parse_taxon(t or "") for t in df["Taxon"].to_list()]
    ranks = list(prefix_to_rank.values())
    for rank in ranks:
        df = df.with_columns(
            pl.Series(rank, [p[rank] for p in parsed], dtype=pl.Utf8)
        )
    return df.drop("Taxon")


# ---------------------------------------------------------------------------
# Download catalog ingestion (source-aware acquisition layer)
# ---------------------------------------------------------------------------

_SOURCE_PREFIXES = {
    "mgnify": ("MGYS",),
    "ena": ("ERR", "ERS", "ERP", "ERX"),
    "sra": ("SRR", "SRS", "SRP", "SRX", "DRR", "DRS", "DRP", "DRX"),
}

_STD_META_COLS = {"sample_id", "biome", "ecosystem", "location", "latitude", "longitude"}


def detect_source(accessions: list[str]) -> str:
    """Infer the data source from accession ID prefixes.

    Parameters
    ----------
    accessions : list of str
        Sample/run accession identifiers.

    Returns
    -------
    str
        One of ``"mgnify"``, ``"ena"``, ``"sra"``. Defaults to ``"sra"`` when
        no known prefix matches.
    """
    for acc in accessions:
        up = str(acc).upper()
        for source, prefixes in _SOURCE_PREFIXES.items():
            if up.startswith(prefixes):
                return source
    return "sra"


def _md5(path: Path, chunk_size: int = 1 << 20) -> str:
    """Compute the MD5 checksum of a file."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_format(name: str) -> str:
    """Return a normalized file-format label from a file name."""
    lower = name.lower()
    for ext in (".fastq.gz", ".fq.gz", ".fastq", ".fq", ".biom", ".tsv", ".qza"):
        if lower.endswith(ext):
            return ext.lstrip(".")
    return Path(name).suffix.lstrip(".") or "unknown"


def ingest_download_catalog(
    db: "FloraDB",
    output_dir: str | Path,
    source: str | None = None,
    compute_checksums: bool = False,
) -> int:
    """Ingest a downloaded directory into the source-aware catalog tables.

    Reads ``manifest.tsv`` (QIIME2 paired/single format) and, when present,
    ``metadata.tsv`` from ``output_dir`` and upserts rows into ``sample_catalog``
    and ``files``. Re-running is safe: existing rows are updated in place
    (incremental updates), enabling repeated downloads of the same study.

    Parameters
    ----------
    db : FloraDB
        Active database connection with the schema initialized.
    output_dir : str or Path
        Directory containing ``manifest.tsv`` and optionally ``metadata.tsv``.
    source : str, optional
        Data source key (``"sra"``, ``"ena"``, ``"mgnify"``, ``"emp"``). When
        omitted, it is inferred from the sample accessions.
    compute_checksums : bool
        When True, compute the MD5 of each local FASTQ file (slower).

    Returns
    -------
    int
        Number of samples upserted into ``sample_catalog``.

    Raises
    ------
    FileNotFoundError
        If neither ``manifest.tsv`` nor ``metadata.tsv`` is present.
    """
    out = Path(output_dir)
    manifest_path = out / "manifest.tsv"
    metadata_path = out / "metadata.tsv"

    if not manifest_path.exists() and not metadata_path.exists():
        raise FileNotFoundError(
            f"No manifest.tsv or metadata.tsv found in {out} for catalog ingestion"
        )

    # ---- Load manifest (files + sample ids + layout) --------------------
    manifest_rows: list[dict] = []
    sample_ids: list[str] = []
    if manifest_path.exists():
        man = pl.read_csv(str(manifest_path), separator="\t", infer_schema_length=10000)
        rev_col = "reverse-absolute-filepath"
        for row in man.iter_rows(named=True):
            sid = row.get("sample-id")
            if sid is None:
                continue
            sample_ids.append(str(sid))
            fwd = row.get("forward-absolute-filepath") or row.get("absolute-filepath")
            rev = row.get(rev_col) if rev_col in man.columns else None
            manifest_rows.append({"sample_id": str(sid), "forward": fwd, "reverse": rev})

    # ---- Load metadata (biome, location, extra -> JSON) -----------------
    meta_by_sample: dict[str, dict] = {}
    if metadata_path.exists():
        meta = pl.read_csv(str(metadata_path), separator="\t", infer_schema_length=10000)
        sample_col = "sample_id" if "sample_id" in meta.columns else meta.columns[0]
        for row in meta.iter_rows(named=True):
            sid = row.get(sample_col)
            if sid is None:
                continue
            sid = str(sid)
            meta_by_sample[sid] = dict(row)
            if sid not in sample_ids:
                sample_ids.append(sid)

    if not sample_ids:
        return 0

    resolved_source = source or detect_source(sample_ids)

    def _clean(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text == "" or text.lower() in {"none", "nan", "null"}:
            return None
        return text

    def _to_float(value) -> float | None:
        text = _clean(value)
        if text is None:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    # ---- Build catalog rows --------------------------------------------
    catalog_rows: list[dict] = []
    layout_by_sample: dict[str, str] = {}
    for mrow in manifest_rows:
        layout_by_sample[mrow["sample_id"]] = "paired" if _clean(mrow.get("reverse")) else "single"

    for sid in sample_ids:
        meta = meta_by_sample.get(sid, {})
        extra = {k: v for k, v in meta.items() if k not in _STD_META_COLS and v is not None}
        catalog_rows.append(
            {
                "source": resolved_source,
                "sample_accession": sid,
                "study_accession": _clean(meta.get("study_accession") or meta.get("study")),
                "run_accession": _clean(meta.get("run_accession") or meta.get("run_id")),
                "experiment_type": _clean(meta.get("experiment_type")),
                "library_strategy": _clean(meta.get("library_strategy")),
                "library_source": _clean(meta.get("library_source")),
                "organism": _clean(meta.get("organism")),
                "scientific_name": _clean(meta.get("scientific_name")),
                "tax_id": int(_clean(meta.get("tax_id"))) if _clean(meta.get("tax_id")) and str(meta.get("tax_id")).isdigit() else None,
                "biome": _clean(meta.get("biome")),
                "ecosystem": _clean(meta.get("ecosystem")),
                "location": _clean(meta.get("location")),
                "latitude": _to_float(meta.get("latitude")),
                "longitude": _to_float(meta.get("longitude")),
                "layout": layout_by_sample.get(sid),
                "metadata": json.dumps(extra, default=str) if extra else None,
            }
        )

    # ---- Build file rows ------------------------------------------------
    file_rows: list[dict] = []
    for mrow in manifest_rows:
        sid = mrow["sample_id"]
        for direction, key in (("forward", "forward"), ("reverse", "reverse")):
            fp = _clean(mrow.get(key))
            if fp is None:
                continue
            p = Path(fp)
            size = p.stat().st_size if p.exists() else None
            checksum = _md5(p) if (compute_checksums and p.exists()) else None
            dir_label = direction if layout_by_sample.get(sid) == "paired" else "single"
            file_rows.append(
                {
                    "source": resolved_source,
                    "sample_accession": sid,
                    "file_name": p.name,
                    "file_path": str(p),
                    "direction": dir_label,
                    "file_format": _file_format(p.name),
                    "size_bytes": size,
                    "checksum": checksum,
                    "checksum_algo": "md5" if checksum else None,
                }
            )

    # ---- Upsert catalog -------------------------------------------------
    catalog_df = pl.DataFrame(
        catalog_rows,
        schema={
            "source": pl.Utf8, "sample_accession": pl.Utf8, "study_accession": pl.Utf8,
            "run_accession": pl.Utf8, "experiment_type": pl.Utf8, "library_strategy": pl.Utf8,
            "library_source": pl.Utf8, "organism": pl.Utf8, "scientific_name": pl.Utf8,
            "tax_id": pl.Int64, "biome": pl.Utf8, "ecosystem": pl.Utf8, "location": pl.Utf8,
            "latitude": pl.Float64, "longitude": pl.Float64, "layout": pl.Utf8, "metadata": pl.Utf8,
        },
    )
    db.register_view("_tmp_catalog", catalog_df)
    db.execute(
        """
        INSERT INTO sample_catalog (
            source, sample_accession, study_accession, run_accession, experiment_type,
            library_strategy, library_source, organism, scientific_name, tax_id,
            biome, ecosystem, location, latitude, longitude, layout, metadata
        )
        SELECT
            source, sample_accession, study_accession, run_accession, experiment_type,
            library_strategy, library_source, organism, scientific_name, tax_id,
            biome, ecosystem, location, latitude, longitude, layout,
            CAST(metadata AS JSON)
        FROM _tmp_catalog
        ON CONFLICT (source, sample_accession) DO UPDATE SET
            study_accession  = COALESCE(EXCLUDED.study_accession, sample_catalog.study_accession),
            run_accession    = COALESCE(EXCLUDED.run_accession, sample_catalog.run_accession),
            experiment_type  = COALESCE(EXCLUDED.experiment_type, sample_catalog.experiment_type),
            library_strategy = COALESCE(EXCLUDED.library_strategy, sample_catalog.library_strategy),
            library_source   = COALESCE(EXCLUDED.library_source, sample_catalog.library_source),
            organism         = COALESCE(EXCLUDED.organism, sample_catalog.organism),
            scientific_name  = COALESCE(EXCLUDED.scientific_name, sample_catalog.scientific_name),
            tax_id           = COALESCE(EXCLUDED.tax_id, sample_catalog.tax_id),
            biome            = COALESCE(EXCLUDED.biome, sample_catalog.biome),
            ecosystem        = COALESCE(EXCLUDED.ecosystem, sample_catalog.ecosystem),
            location         = COALESCE(EXCLUDED.location, sample_catalog.location),
            latitude         = COALESCE(EXCLUDED.latitude, sample_catalog.latitude),
            longitude        = COALESCE(EXCLUDED.longitude, sample_catalog.longitude),
            layout           = COALESCE(EXCLUDED.layout, sample_catalog.layout),
            metadata         = COALESCE(EXCLUDED.metadata, sample_catalog.metadata),
            updated_at       = now()
        """
    )
    db.execute("DROP VIEW IF EXISTS _tmp_catalog")

    # ---- Upsert files ---------------------------------------------------
    if file_rows:
        files_df = pl.DataFrame(
            file_rows,
            schema={
                "source": pl.Utf8, "sample_accession": pl.Utf8, "file_name": pl.Utf8,
                "file_path": pl.Utf8, "direction": pl.Utf8, "file_format": pl.Utf8,
                "size_bytes": pl.Int64, "checksum": pl.Utf8, "checksum_algo": pl.Utf8,
            },
        )
        db.register_view("_tmp_files", files_df)
        db.execute(
            """
            INSERT INTO files (
                source, sample_accession, file_name, file_path, direction,
                file_format, size_bytes, checksum, checksum_algo
            )
            SELECT
                source, sample_accession, file_name, file_path, direction,
                file_format, size_bytes, checksum, checksum_algo
            FROM _tmp_files
            ON CONFLICT (source, sample_accession, file_name) DO UPDATE SET
                file_path     = EXCLUDED.file_path,
                direction     = EXCLUDED.direction,
                file_format   = EXCLUDED.file_format,
                size_bytes    = COALESCE(EXCLUDED.size_bytes, files.size_bytes),
                checksum      = COALESCE(EXCLUDED.checksum, files.checksum),
                checksum_algo = COALESCE(EXCLUDED.checksum_algo, files.checksum_algo)
            """
        )
        db.execute("DROP VIEW IF EXISTS _tmp_files")

    logger.info(
        "Catalog ingest: %d samples, %d files from %s (source=%s)",
        len(catalog_rows), len(file_rows), out, resolved_source,
    )
    return len(catalog_rows)
