"""Data ingestion utilities: BIOM, TSV ASV tables, and metadata into DuckDB.

All ingestion functions convert source data to Polars DataFrames and load
them via FloraDB.load_dataframe(). Intermediate Parquet files are written
when a parquet_dir is specified, enabling re-use without re-parsing.
"""

from __future__ import annotations

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
