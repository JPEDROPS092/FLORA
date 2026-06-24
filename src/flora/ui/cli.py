"""FLORA command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl


def _ingest_download_to_duckdb(
    output_dir: str | Path,
    db_path: str | Path,
    source: str | None = None,
    compute_checksums: bool = False,
) -> int:
    """Ingest a downloaded directory into DuckDB.

    Populates both the analytical ``samples`` table and the source-aware
    catalog (``sample_catalog`` + ``files``). If metadata.tsv exists it is
    used; otherwise minimal sample records are derived from manifest.tsv.

    Returns the number of samples registered in the catalog.
    """
    from flora.db.connection import FloraDB
    from flora.db.ingestion import ingest_download_catalog, ingest_metadata

    out = Path(output_dir)
    metadata_path = out / "metadata.tsv"
    manifest_path = out / "manifest.tsv"

    if not metadata_path.exists() and not manifest_path.exists():
        raise FileNotFoundError(
            f"No metadata.tsv or manifest.tsv found in {out} for DuckDB ingestion"
        )

    with FloraDB.connect(path=db_path) as db:
        db.initialize_schema()

        # 1) Analytical 'samples' table (backward compatible).
        if metadata_path.exists():
            ingest_metadata(db, metadata_path, sample_col="sample_id")
        else:
            manifest_df = pl.read_csv(str(manifest_path), separator="\t")
            if "sample-id" not in manifest_df.columns:
                raise ValueError(f"Manifest missing 'sample-id' column: {manifest_path}")
            sample_ids = manifest_df["sample-id"].drop_nulls().unique().to_list()
            if sample_ids:
                samples_df = pl.DataFrame(
                    {
                        "sample_id": sample_ids,
                        "biome": [None] * len(sample_ids),
                        "location": [None] * len(sample_ids),
                        "latitude": [None] * len(sample_ids),
                        "longitude": [None] * len(sample_ids),
                        "sequencing_depth": [None] * len(sample_ids),
                    }
                )
                db.register_view("_tmp_new_samples", samples_df)
                db.execute(
                    """
                    INSERT INTO samples (sample_id, biome, location, latitude, longitude, sequencing_depth)
                    SELECT t.sample_id, t.biome, t.location, t.latitude, t.longitude, t.sequencing_depth
                    FROM _tmp_new_samples t
                    LEFT JOIN samples s USING (sample_id)
                    WHERE s.sample_id IS NULL
                    """
                )
                db.execute("DROP VIEW IF EXISTS _tmp_new_samples")

        # 2) Source-aware catalog (sample_catalog + files).
        return ingest_download_catalog(
            db, out, source=source, compute_checksums=compute_checksums
        )


def main() -> None:
    """Entry point for the ``flora`` command."""
    parser = argparse.ArgumentParser(
        prog="flora",
        description="FLORA — Feature Learning and Omics Research Analytics",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ui_cmd = sub.add_parser("ui", help="Start the web interface")
    ui_cmd.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui_cmd.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    ui_cmd.add_argument("--workdir", default="results", help="Working directory")
    ui_cmd.add_argument("--config", default=None, help="Path to config.yaml")
    ui_cmd.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    run_cmd = sub.add_parser("run", help="Run a pipeline from config")
    run_cmd.add_argument("config", help="Path to config.yaml")
    run_cmd.add_argument("--workdir", default="results", help="Working directory")

    download_cmd = sub.add_parser("download", help="Download public datasets")
    dl_sub = download_cmd.add_subparsers(dest="source", required=True)

    duckdb_parent = argparse.ArgumentParser(add_help=False)
    duckdb_parent.add_argument(
        "--to-duckdb",
        action="store_true",
        help="Ingest downloaded samples/metadata into DuckDB after download",
    )
    duckdb_parent.add_argument(
        "--duckdb-path",
        default="results/flora.duckdb",
        help="DuckDB file path used with --to-duckdb (default: results/flora.duckdb)",
    )
    duckdb_parent.add_argument(
        "--checksums",
        action="store_true",
        help="Compute MD5 checksums of downloaded files during DuckDB ingestion",
    )

    mg = dl_sub.add_parser("mgnify", parents=[duckdb_parent], help="Download from MGnify")
    mg.add_argument("study", help="MGnify study accession (e.g. MGYS00005116)")
    mg.add_argument("--outdir", default="data/raw", help="Output directory")
    mg.add_argument("--max-samples", type=int, default=50)
    mg.add_argument("--biome", default="root:Environmental:Terrestrial:Forest")

    sra = dl_sub.add_parser("sra", parents=[duckdb_parent], help="Download from NCBI SRA")
    sra.add_argument("accessions", nargs="+", help="SRR/ERR accession IDs")
    sra.add_argument("--outdir", default="data/raw", help="Output directory")
    sra.add_argument("--jobs", type=int, default=4)

    ingest_cmd = sub.add_parser(
        "ingest",
        help="Load an already-downloaded directory (metadata/manifest) into DuckDB",
    )
    ingest_cmd.add_argument(
        "path",
        nargs="?",
        default="data/raw",
        help="Directory containing metadata.tsv and/or manifest.tsv (default: data/raw)",
    )
    ingest_cmd.add_argument(
        "--duckdb-path",
        default="results/flora.duckdb",
        help="DuckDB file path (default: results/flora.duckdb)",
    )
    ingest_cmd.add_argument(
        "--source",
        default=None,
        choices=["sra", "ena", "mgnify", "emp"],
        help="Data source key. Auto-detected from accessions when omitted.",
    )
    ingest_cmd.add_argument(
        "--checksums",
        action="store_true",
        help="Compute MD5 checksums of local files during ingestion",
    )

    args = parser.parse_args()

    if args.command == "ui":
        from flora.ui.server import run_server
        from flora.config.settings import load_config

        cfg = load_config(args.config) if args.config else None
        run_server(
            host=args.host,
            port=args.port,
            config=cfg,
            workdir=args.workdir,
            open_browser=not args.no_browser,
        )

    elif args.command == "download":
        if args.source == "mgnify":
            from flora.io.downloaders import MGnifyDownloader

            dl = MGnifyDownloader(biome=args.biome)
            manifest = dl.fetch(
                study_accession=args.study,
                output_dir=args.outdir,
                max_samples=args.max_samples,
            )
            print(f"Done. Manifest: {manifest}")
            if args.to_duckdb:
                inserted = _ingest_download_to_duckdb(
                    args.outdir, args.duckdb_path,
                    source="mgnify", compute_checksums=args.checksums,
                )
                print(f"DuckDB ingest complete: {inserted} samples -> {args.duckdb_path}")

        elif args.source == "sra":
            from flora.io.downloaders import NCBISRADownloader

            dl = NCBISRADownloader(n_jobs=args.jobs)
            manifest = dl.fetch(accessions=args.accessions, output_dir=args.outdir)
            print(f"Done. Manifest: {manifest}")
            if args.to_duckdb:
                inserted = _ingest_download_to_duckdb(
                    args.outdir, args.duckdb_path,
                    source="sra", compute_checksums=args.checksums,
                )
                print(f"DuckDB ingest complete: {inserted} samples -> {args.duckdb_path}")

    elif args.command == "ingest":
        inserted = _ingest_download_to_duckdb(
            args.path, args.duckdb_path,
            source=args.source, compute_checksums=args.checksums,
        )
        print(f"DuckDB ingest complete: {inserted} samples -> {args.duckdb_path}")

    elif args.command == "run":
        print("Pipeline run from config not yet implemented via CLI. Use FLORAPipeline in Python.")
        sys.exit(1)


if __name__ == "__main__":
    main()
