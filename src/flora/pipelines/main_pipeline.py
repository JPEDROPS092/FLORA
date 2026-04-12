"""FLORAPipeline: orchestrates the full FLORA analysis workflow.

The pipeline chains QIIME2/DADA2 processing, DuckDB ingestion, feature
engineering, ML, and visualization into a unified interface. Each step
updates the DuckDB database and can be run independently or as part of
a complete run.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from flora.config.settings import FloraConfig, load_config
from flora.core.exceptions import PipelineError
from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema

logger = logging.getLogger("flora.pipelines")


class FLORAPipeline:
    """End-to-end FLORA analysis pipeline.

    Parameters
    ----------
    config : FloraConfig or str or Path
        Configuration object or path to a YAML config file.
        If None, uses default configuration.
    workdir : str or Path
        Working directory for results and intermediate files.

    Examples
    --------
    >>> pipeline = FLORAPipeline(config="config.yaml", workdir="results/")
    >>> pipeline.ingest_metadata("data/raw/metadata.tsv")
    >>> pipeline.ingest_asv_table("data/raw/asv_table.tsv", wide_format=True)
    >>> pipeline.ingest_taxonomy("data/raw/taxonomy.tsv")
    >>> pipeline.compute_diversity(sampling_depth=10000)
    >>> asv_clr = pipeline.get_feature_matrix(normalize="clr")
    """

    def __init__(
        self,
        config: FloraConfig | str | Path | None = None,
        workdir: str | Path = "results",
    ) -> None:
        if isinstance(config, (str, Path)):
            self.config = load_config(config)
        elif isinstance(config, FloraConfig):
            self.config = config
        else:
            self.config = load_config()

        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

        self._run_id = str(uuid.uuid4())[:8]
        self._db: FloraDB | None = None

        from flora.core.logging import setup_logging
        setup_logging(
            level=self.config.logging.level,
            log_file=self.config.logging.log_file,
            rich_output=self.config.logging.rich_output,
        )

        logger.info("FLORAPipeline initialized [run_id=%s]", self._run_id)

    @property
    def db(self) -> FloraDB:
        """Lazy-initialize and return the DuckDB connection."""
        if self._db is None:
            db_path = self.config.database.path
            if db_path != ":memory:":
                db_path = str(self.workdir / db_path)
            self._db = FloraDB.connect(
                path=db_path,
                threads=self.config.database.threads,
                memory_limit=self.config.database.memory_limit,
            )
            initialize_schema(self._db)
            self._db.create_views()
            logger.info("DuckDB initialized at %s", db_path)
        return self._db

    def ingest_metadata(
        self,
        metadata_path: str | Path,
        sample_col: str = "sample_id",
    ) -> int:
        """Ingest sample metadata into DuckDB.

        Parameters
        ----------
        metadata_path : str or Path
            Path to TSV or CSV metadata file.
        sample_col : str
            Column name for sample IDs.

        Returns
        -------
        int
            Number of samples ingested.
        """
        from flora.db.ingestion import ingest_metadata

        self._log_step("ingest_metadata", "started")
        try:
            n = ingest_metadata(
                self.db,
                metadata_path,
                sample_col=sample_col,
                parquet_dir=self.workdir / "parquet",
            )
            self._log_step("ingest_metadata", "completed", params={"file": str(metadata_path)})
            return n
        except Exception as exc:
            self._log_step("ingest_metadata", "failed", message=str(exc))
            raise PipelineError(str(exc), step="ingest_metadata") from exc

    def ingest_asv_table(
        self,
        path: str | Path,
        wide_format: bool = False,
    ) -> int:
        """Ingest an ASV feature table (BIOM or TSV) into DuckDB.

        Parameters
        ----------
        path : str or Path
            Path to BIOM file or TSV ASV table.
        wide_format : bool
            If True, treat TSV as wide format (samples x features).

        Returns
        -------
        int
            Number of observations ingested.
        """
        fpath = Path(path)
        self._log_step("ingest_asv", "started")
        try:
            if fpath.suffix == ".biom":
                from flora.db.ingestion import ingest_biom

                n = ingest_biom(self.db, fpath, parquet_dir=self.workdir / "parquet")
            else:
                from flora.db.ingestion import ingest_tsv_asv

                n = ingest_tsv_asv(
                    self.db,
                    fpath,
                    wide_format=wide_format,
                    parquet_dir=self.workdir / "parquet",
                )
            self._log_step("ingest_asv", "completed", params={"file": str(fpath)})
            return n
        except Exception as exc:
            self._log_step("ingest_asv", "failed", message=str(exc))
            raise PipelineError(str(exc), step="ingest_asv") from exc

    def ingest_taxonomy(self, path: str | Path) -> int:
        """Ingest taxonomy assignments into DuckDB.

        Parameters
        ----------
        path : str or Path
            Path to taxonomy TSV file.

        Returns
        -------
        int
            Number of taxonomy rows ingested.
        """
        from flora.db.ingestion import ingest_taxonomy

        self._log_step("ingest_taxonomy", "started")
        try:
            n = ingest_taxonomy(self.db, path, parquet_dir=self.workdir / "parquet")
            self._log_step("ingest_taxonomy", "completed")
            return n
        except Exception as exc:
            self._log_step("ingest_taxonomy", "failed", message=str(exc))
            raise PipelineError(str(exc), step="ingest_taxonomy") from exc

    def compute_diversity(
        self,
        sampling_depth: int | None = None,
        metrics: list[str] | None = None,
    ) -> pl.DataFrame:
        """Compute alpha diversity metrics and store results in DuckDB.

        Parameters
        ----------
        sampling_depth : int, optional
            Rarefaction depth. If None, auto-selected.
        metrics : list of str, optional
            Diversity metrics to compute. Defaults to shannon, observed_features,
            chao1.

        Returns
        -------
        polars.DataFrame
            Wide-format diversity table (sample_id x metric).
        """
        from flora.diversity.alpha import compute_alpha_diversity

        metrics = metrics or ["shannon", "observed_features", "chao1"]
        depth = sampling_depth or self.config.pipeline.sampling_depth

        self._log_step("compute_diversity", "started")
        try:
            wide = self.db.pivot_asv()
            diversity_df = compute_alpha_diversity(wide, metrics=metrics, sampling_depth=depth)

            long = diversity_df.unpivot(
                index="sample_id",
                on=[c for c in diversity_df.columns if c != "sample_id"],
                variable_name="metric",
                value_name="value",
            ).with_columns(pl.lit(depth).alias("sampling_depth"))

            self.db.load_dataframe("diversity_alpha", long)
            self._log_step("compute_diversity", "completed", params={"metrics": metrics})
            return diversity_df
        except Exception as exc:
            self._log_step("compute_diversity", "failed", message=str(exc))
            raise PipelineError(str(exc), step="compute_diversity") from exc

    def get_feature_matrix(
        self,
        normalize: str | None = "clr",
        min_prevalence: float = 0.05,
    ) -> pl.DataFrame:
        """Return the feature matrix for ML from DuckDB.

        Parameters
        ----------
        normalize : str or None
            ``"clr"``, ``"tss"``, or None for raw counts.
        min_prevalence : float
            Minimum sample prevalence for feature inclusion.

        Returns
        -------
        polars.DataFrame
            Wide feature matrix (samples x ASVs).
        """
        return self.db.pivot_asv(normalize=normalize, min_prevalence=min_prevalence)

    def close(self) -> None:
        """Close the DuckDB connection and release resources."""
        if self._db is not None:
            self._db.close()
            self._db = None

    def __enter__(self) -> "FLORAPipeline":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _log_step(
        self,
        step: str,
        status: str,
        params: dict | None = None,
        message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        try:
            self.db.execute(
                """
                INSERT INTO pipeline_log (run_id, step, status, started_at, params, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    self._run_id,
                    step,
                    status,
                    now,
                    str(params) if params else None,
                    message,
                ],
            )
        except Exception:
            pass
        logger.debug("[%s] step=%s status=%s", self._run_id, step, status)
