"""FLORA command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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

    mg = dl_sub.add_parser("mgnify", help="Download from MGnify")
    mg.add_argument("study", help="MGnify study accession (e.g. MGYS00005116)")
    mg.add_argument("--outdir", default="data/raw", help="Output directory")
    mg.add_argument("--max-samples", type=int, default=50)
    mg.add_argument("--biome", default="root:Environmental:Terrestrial:Forest")

    sra = dl_sub.add_parser("sra", help="Download from NCBI SRA")
    sra.add_argument("accessions", nargs="+", help="SRR/ERR accession IDs")
    sra.add_argument("--outdir", default="data/raw", help="Output directory")
    sra.add_argument("--jobs", type=int, default=4)

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

        elif args.source == "sra":
            from flora.io.downloaders import NCBISRADownloader

            dl = NCBISRADownloader(n_jobs=args.jobs)
            manifest = dl.fetch(accessions=args.accessions, output_dir=args.outdir)
            print(f"Done. Manifest: {manifest}")

    elif args.command == "run":
        print("Pipeline run from config not yet implemented via CLI. Use FLORAPipeline in Python.")
        sys.exit(1)


if __name__ == "__main__":
    main()
