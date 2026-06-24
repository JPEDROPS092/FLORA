"""FloraDB: DuckDB connection manager and analytics API.

FloraDB is a context-manager-compatible singleton for a DuckDB connection.
It provides:
- schema initialization
- Parquet ingestion
- DataFrame ingestion
- analytical query helpers (PIVOT, aggregations, slicing)
- zero-copy export to pandas, Polars, and PyArrow
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pyarrow as pa

from flora.core.exceptions import DatabaseError

logger = logging.getLogger("flora.db.connection")


class FloraDB:
    """Central DuckDB analytics engine for FLORA.

    Parameters
    ----------
    path : str or Path
        DuckDB file path. Use ``:memory:`` for in-process ephemeral storage.
    threads : int
        Number of DuckDB execution threads.
    memory_limit : str
        DuckDB memory limit (e.g. ``"4GB"``).
    read_only : bool
        Open the database in read-only mode.

    Examples
    --------
    File-backed database:

    >>> db = FloraDB("results/flora.duckdb")
    >>> db.initialize_schema()
    >>> db.close()

    In-memory (tests):

    >>> with FloraDB(":memory:") as db:
    ...     db.initialize_schema()
    ...     db.execute("INSERT INTO samples VALUES ('S1', 'Amazon', NULL, NULL, NULL, NULL)")
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        threads: int = 4,
        memory_limit: str = "4GB",
        read_only: bool = False,
    ) -> None:
        self._path = str(path)
        self._threads = threads
        self._memory_limit = memory_limit
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._connect()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        try:
            if self._path != ":memory:":
                parent = Path(self._path).parent
                if parent and not parent.exists():
                    parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(
                database=self._path,
                read_only=self._read_only,
            )
            self._conn.execute(f"SET threads = {self._threads}")
            self._conn.execute(f"SET memory_limit = '{self._memory_limit}'")
            logger.debug("DuckDB connected: path=%s threads=%d", self._path, self._threads)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to connect to DuckDB: {exc}",
                context={"path": self._path},
            ) from exc

    @classmethod
    def connect(
        cls,
        path: str | Path = ":memory:",
        threads: int = 4,
        memory_limit: str = "4GB",
        read_only: bool = False,
    ) -> "FloraDB":
        """Factory method alternative to direct instantiation.

        Parameters
        ----------
        path : str or Path
            DuckDB file path or ``:memory:``.
        threads : int
            DuckDB execution threads.
        memory_limit : str
            Memory cap string understood by DuckDB.
        read_only : bool
            Open in read-only mode.

        Returns
        -------
        FloraDB
            Initialized and connected database instance.
        """
        return cls(path=path, threads=threads, memory_limit=memory_limit, read_only=read_only)

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("DuckDB connection closed")

    def __enter__(self) -> "FloraDB":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def _c(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise DatabaseError("DuckDB connection is closed")
        return self._conn

    # ------------------------------------------------------------------
    # Core query API
    # ------------------------------------------------------------------

    def execute(self, sql: str, parameters: list[Any] | None = None) -> None:
        """Execute a SQL statement without returning results.

        Parameters
        ----------
        sql : str
            SQL statement to execute.
        parameters : list, optional
            Positional parameters for the statement.

        Raises
        ------
        DatabaseError
            If the statement fails.
        """
        try:
            if parameters:
                self._c.execute(sql, parameters)
            else:
                self._c.execute(sql)
        except Exception as exc:
            raise DatabaseError(str(exc), query=sql) from exc

    def query(self, sql: str, parameters: list[Any] | None = None) -> "QueryResult":
        """Execute a SQL query and return a QueryResult.

        Parameters
        ----------
        sql : str
            SELECT statement.
        parameters : list, optional
            Positional query parameters.

        Returns
        -------
        QueryResult
            Lazy result container with .to_df(), .to_polars(), .to_arrow()
            conversion methods.

        Raises
        ------
        DatabaseError
            If the query fails.
        """
        try:
            if parameters:
                rel = self._c.execute(sql, parameters)
            else:
                rel = self._c.execute(sql)
            return QueryResult(rel)
        except Exception as exc:
            raise DatabaseError(str(exc), query=sql) from exc

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def initialize_schema(self) -> None:
        """Create all FLORA tables if they do not already exist.

        Safe to call on an existing database; uses CREATE TABLE IF NOT EXISTS.

        Raises
        ------
        DatabaseError
            If any DDL statement fails.
        """
        from flora.db.schema import initialize_schema

        initialize_schema(self)
        logger.info("Schema initialized on %s", self._path)

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def load_parquet(self, table: str, parquet_path: str | Path) -> int:
        """Load a Parquet file into a DuckDB table.

        The Parquet file must have columns compatible with ``table``'s schema.
        Rows are appended; existing rows are not deduplicated.

        Parameters
        ----------
        table : str
            Target table name.
        parquet_path : str or Path
            Path to the Parquet file.

        Returns
        -------
        int
            Number of rows inserted.

        Raises
        ------
        DatabaseError
            If the COPY command fails.
        FileNotFoundError
            If the Parquet file does not exist.
        """
        path = Path(parquet_path)
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")

        sql = f"INSERT INTO {table} SELECT * FROM read_parquet('{path}')"
        self.execute(sql)
        result = self.query(f"SELECT COUNT(*) FROM {table}").to_polars()
        count = int(result[result.columns[0]][0])
        logger.info("Loaded %d rows into table '%s' from %s", count, table, path)
        return count

    def load_dataframe(
        self,
        table: str,
        df: pl.DataFrame,
        if_exists: str = "append",
    ) -> int:
        """Load a Polars DataFrame into a DuckDB table.

        Parameters
        ----------
        table : str
            Target table name.
        df : polars.DataFrame
            Data to insert.
        if_exists : str
            ``"append"`` adds rows, ``"replace"`` truncates first.

        Returns
        -------
        int
            Number of rows inserted.

        Raises
        ------
        DatabaseError
            If the insert fails.
        ValueError
            If ``if_exists`` is not a supported value.
        """
        if if_exists not in ("append", "replace"):
            raise ValueError(f"if_exists must be 'append' or 'replace', got '{if_exists}'")

        if if_exists == "replace":
            self.execute(f"DELETE FROM {table}")

        arrow = df.to_arrow()
        self._c.register("_tmp_load_frame", arrow)
        self.execute(f"INSERT INTO {table} SELECT * FROM _tmp_load_frame")
        self._c.unregister("_tmp_load_frame")
        logger.info("Loaded %d rows into table '%s'", len(df), table)
        return len(df)

    def register_view(self, name: str, df: pl.DataFrame) -> None:
        """Register a Polars DataFrame as a DuckDB view.

        Parameters
        ----------
        name : str
            View name accessible in subsequent SQL queries.
        df : polars.DataFrame
            Data to expose as a view.
        """
        arrow = df.to_arrow()
        self._c.register(name, arrow)
        logger.debug("Registered view '%s' (%d rows)", name, len(df))

    # ------------------------------------------------------------------
    # Analytical helpers
    # ------------------------------------------------------------------

    def pivot_asv(
        self,
        normalize: str | None = None,
        min_prevalence: float = 0.0,
    ) -> pl.DataFrame:
        """Return a wide feature matrix (samples x ASVs) for ML.

        Parameters
        ----------
        normalize : str, optional
            Normalization to apply before pivoting. One of:
            ``"tss"`` (Total Sum Scaling), ``"clr"`` (Centered Log-Ratio),
            ``None`` (raw counts).
        min_prevalence : float
            Minimum fraction of samples in which a feature must be present.
            Features below this threshold are dropped. Range [0, 1].

        Returns
        -------
        polars.DataFrame
            Wide DataFrame with ``sample_id`` as the first column, followed
            by one column per ASV feature.

        Raises
        ------
        DatabaseError
            If the underlying query fails.
        """
        if normalize == "tss":
            abundance_expr = (
                "a.abundance / SUM(a.abundance) OVER (PARTITION BY a.sample_id)"
            )
        elif normalize == "clr":
            abundance_expr = (
                "LN((a.abundance + 0.5) / "
                "EXP(AVG(LN(a.abundance + 0.5)) OVER (PARTITION BY a.sample_id)))"
            )
        else:
            abundance_expr = "a.abundance"

        prevalence_filter = ""
        if min_prevalence > 0:
            total_samples = self.query("SELECT COUNT(DISTINCT sample_id) FROM samples").to_polars()
            n = int(total_samples[total_samples.columns[0]][0])
            min_count = int(n * min_prevalence)
            prevalence_filter = f"""
            WHERE a.feature_id IN (
                SELECT feature_id FROM asv
                WHERE abundance > 0
                GROUP BY feature_id
                HAVING COUNT(DISTINCT sample_id) >= {min_count}
            )
            """

        sql = f"""
        PIVOT (
            SELECT a.sample_id, a.feature_id, {abundance_expr} AS abundance
            FROM asv a
            {prevalence_filter}
        )
        ON feature_id
        USING SUM(abundance)
        GROUP BY sample_id
        ORDER BY sample_id
        """
        logger.debug("pivot_asv: normalize=%s min_prevalence=%s", normalize, min_prevalence)
        return self.query(sql).to_polars().fill_null(0.0)

    def aggregate_by_taxon(
        self,
        level: str = "phylum",
        group_by: str | None = None,
        metric: str = "mean",
    ) -> pl.DataFrame:
        """Aggregate ASV abundances by taxonomic rank.

        Parameters
        ----------
        level : str
            Taxonomic level to aggregate to. One of: kingdom, phylum, class,
            order, family, genus, species.
        group_by : str, optional
            Sample metadata column to group by (e.g. ``"biome"``).
        metric : str
            Aggregation function. One of: ``"mean"``, ``"sum"``, ``"median"``.

        Returns
        -------
        polars.DataFrame
            Aggregated abundance table.

        Raises
        ------
        ValueError
            If ``level`` is not a valid taxonomic rank.
        DatabaseError
            If the query fails.
        """
        valid_levels = {"kingdom", "phylum", "class", "order", "family", "genus", "species"}
        if level not in valid_levels:
            raise ValueError(f"Invalid taxonomic level '{level}'. Choose from {valid_levels}")

        agg_func = {"mean": "AVG", "sum": "SUM", "median": "MEDIAN"}.get(metric)
        if agg_func is None:
            raise ValueError(f"Invalid metric '{metric}'. Choose from mean, sum, median")

        group_cols = f"t.{level}"
        select_extra = ""
        if group_by:
            group_cols = f"t.{level}, s.{group_by}"
            select_extra = f", s.{group_by}"

        sql = f"""
        SELECT t.{level}{select_extra},
               {agg_func}(a.abundance) AS {metric}_abundance,
               COUNT(DISTINCT a.sample_id) AS n_samples
        FROM asv a
        JOIN taxonomy t USING(feature_id)
        JOIN samples s USING(sample_id)
        WHERE t.{level} IS NOT NULL
        GROUP BY {group_cols}
        ORDER BY {metric}_abundance DESC
        """
        return self.query(sql).to_polars()

    def slice(
        self,
        train_filter: str,
        test_filter: str,
        features: str = "asv",
        target_column: str | None = None,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Generate train/test splits from DuckDB via SQL filters.

        Parameters
        ----------
        train_filter : str
            SQL WHERE clause selecting training samples from the ``samples``
            table (e.g. ``"biome = 'Amazon'``).
        test_filter : str
            SQL WHERE clause selecting test samples.
        features : str
            ``"asv"`` for raw ASV pivot, ``"clr"`` for CLR-normalized pivot,
            ``"tss"`` for TSS-normalized pivot.
        target_column : str, optional
            Metadata column to include as the target label.

        Returns
        -------
        tuple of (train DataFrame, test DataFrame)
            Both DataFrames have ``sample_id`` as first column, followed by
            feature columns, optionally followed by the target column.

        Raises
        ------
        DatabaseError
            If any query fails.
        """
        normalize = None if features == "asv" else features

        def _build_split(where_clause: str) -> pl.DataFrame:
            sample_sql = f"SELECT sample_id FROM samples WHERE {where_clause}"
            samples = self.query(sample_sql).to_polars()
            sample_ids = samples["sample_id"].to_list()

            if not sample_ids:
                raise DatabaseError(
                    f"No samples matched filter: {where_clause}",
                    context={"filter": where_clause},
                )

            ids_str = ", ".join(f"'{s}'" for s in sample_ids)
            norm_expr = self._normalize_expr(normalize)

            feat_sql = f"""
            PIVOT (
                SELECT a.sample_id, a.feature_id, {norm_expr} AS abundance
                FROM asv a
                WHERE a.sample_id IN ({ids_str})
            )
            ON feature_id
            USING SUM(abundance)
            GROUP BY sample_id
            ORDER BY sample_id
            """
            feat_df = self.query(feat_sql).to_polars().fill_null(0.0)

            if target_column:
                meta_sql = (
                    f"SELECT sample_id, {target_column} FROM samples WHERE sample_id IN ({ids_str})"
                )
                meta_df = self.query(meta_sql).to_polars()
                feat_df = feat_df.join(meta_df, on="sample_id", how="left")

            return feat_df

        train = _build_split(train_filter)
        test = _build_split(test_filter)
        logger.info(
            "Dataset slice: train=%d samples, test=%d samples",
            len(train),
            len(test),
        )
        return train, test

    def create_views(self) -> None:
        """Create standard analytical views for common query patterns.

        Creates the following views if they do not already exist:
        - ``v_asv_tss``: TSS-normalized long-format abundance
        - ``v_asv_clr``: CLR-normalized long-format abundance
        - ``v_taxonomy_full``: ASV joined with full taxonomic lineage
        - ``v_diversity_wide``: Diversity metrics pivoted to wide format

        Raises
        ------
        DatabaseError
            If any view creation fails.
        """
        views = {
            "v_asv_tss": """
                SELECT sample_id, feature_id,
                    abundance / SUM(abundance) OVER (PARTITION BY sample_id) AS abundance
                FROM asv
            """,
            "v_asv_clr": """
                SELECT sample_id, feature_id,
                    LN((abundance + 0.5) /
                       EXP(AVG(LN(abundance + 0.5)) OVER (PARTITION BY sample_id))) AS abundance
                FROM asv
            """,
            "v_taxonomy_full": """
                SELECT a.sample_id, a.feature_id, a.abundance,
                       t.kingdom, t.phylum, t.class, t."order",
                       t.family, t.genus, t.species, t.confidence
                FROM asv a
                LEFT JOIN taxonomy t USING(feature_id)
            """,
            "v_diversity_wide": """
                SELECT
                    sample_id,
                    AVG(CASE WHEN metric = 'shannon' THEN value END) AS shannon,
                    AVG(CASE WHEN metric = 'observed_features' THEN value END)
                        AS observed_features,
                    AVG(CASE WHEN metric = 'chao1' THEN value END) AS chao1,
                    AVG(CASE WHEN metric = 'simpson' THEN value END) AS simpson,
                    AVG(CASE WHEN metric = 'faith_pd' THEN value END) AS faith_pd
                FROM diversity_alpha
                GROUP BY sample_id
            """,
        }
        for name, body in views.items():
            self.execute(f"CREATE OR REPLACE VIEW {name} AS {body}")
        logger.info("Standard views created/updated")

    def table_info(self) -> pl.DataFrame:
        """Return row counts for all FLORA tables.

        Returns
        -------
        polars.DataFrame
            Table with columns ``table_name`` and ``row_count``.
        """
        sql = """
        SELECT table_name, estimated_size AS row_count
        FROM duckdb_tables()
        WHERE schema_name = 'main'
        ORDER BY table_name
        """
        try:
            return self.query(sql).to_polars()
        except Exception:
            tables = ["samples", "asv", "taxonomy", "diversity_alpha", "diversity_beta"]
            rows = []
            for t in tables:
                try:
                    cnt = self.query(f"SELECT COUNT(*) AS n FROM {t}").to_polars()["n"][0]
                    rows.append({"table_name": t, "row_count": cnt})
                except Exception:
                    rows.append({"table_name": t, "row_count": -1})
            return pl.DataFrame(rows)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_expr(self, normalize: str | None) -> str:
        if normalize == "tss":
            return "a.abundance / SUM(a.abundance) OVER (PARTITION BY a.sample_id)"
        if normalize == "clr":
            return (
                "LN((a.abundance + 0.5) / "
                "EXP(AVG(LN(a.abundance + 0.5)) OVER (PARTITION BY a.sample_id)))"
            )
        return "a.abundance"


class QueryResult:
    """Thin wrapper around a DuckDB relation providing typed conversions.

    Parameters
    ----------
    relation : duckdb.DuckDBPyRelation
        The relation returned by duckdb execute.
    """

    def __init__(self, relation: Any) -> None:
        self._rel = relation

    def to_df(self) -> "pl.DataFrame":
        """Convert result to a Polars DataFrame.

        Returns
        -------
        polars.DataFrame
        """
        return pl.from_arrow(self._rel.to_arrow_table())

    def to_polars(self) -> pl.DataFrame:
        """Alias for to_df().

        Returns
        -------
        polars.DataFrame
        """
        return self.to_df()

    def to_pandas(self) -> "Any":
        """Convert result to a pandas DataFrame.

        Returns
        -------
        pandas.DataFrame
        """
        return self._rel.df()

    def to_arrow(self) -> pa.Table:
        """Convert result to a PyArrow Table (zero-copy where possible).

        Returns
        -------
        pyarrow.Table
        """
        return self._rel.to_arrow_table()

    def to_parquet(self, path: str | Path) -> None:
        """Write result directly to a Parquet file.

        Parameters
        ----------
        path : str or Path
            Destination file path.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        import pyarrow.parquet as pq

        pq.write_table(self._rel.to_arrow_table(), dest)
        logger.debug("Query result written to %s", dest)
