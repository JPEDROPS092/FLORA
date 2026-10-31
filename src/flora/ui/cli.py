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
    ui_cmd.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], dest="log_level")

    run_cmd = sub.add_parser("run", help="Run a pipeline from config")
    run_cmd.add_argument("config", help="Path to config.yaml")
    run_cmd.add_argument("--workdir", default=None, help="Override workdir from config")
    run_cmd.add_argument("--metadata", default=None, help="Path to metadata.tsv (overrides storage.raw_dir)")
    run_cmd.add_argument("--asv-table", default=None, dest="asv_table", help="Path to asv_table.tsv")
    run_cmd.add_argument("--taxonomy", default=None, help="Path to taxonomy.tsv")
    run_cmd.add_argument("--sampling-depth", type=int, default=None, dest="sampling_depth")

    download_cmd = sub.add_parser("download", help="Download public datasets")
    dl_sub = download_cmd.add_subparsers(dest="source", required=True)

    mg = dl_sub.add_parser("mgnify", help="Download from MGnify")
    mg.add_argument("study", help="MGnify study accession (e.g. MGYS00005116)")
    mg.add_argument("--outdir", default="data/raw", help="Output directory")
    mg.add_argument("--max-samples", type=int, default=50)
    mg.add_argument("--biome", default="root:Environmental:Terrestrial:Forest")
    mg.add_argument(
        "--analyses",
        action="store_true",
        help="Download pre-computed OTU table and taxonomy instead of raw FASTQs",
    )

    sra = dl_sub.add_parser("sra", help="Download from NCBI SRA")
    sra.add_argument("accessions", nargs="+", help="SRR/ERR accession IDs")
    sra.add_argument("--outdir", default="data/raw", help="Output directory")
    sra.add_argument("--jobs", type=int, default=4)

    emp = dl_sub.add_parser("emp", help="Download from Earth Microbiome Project (Release 1)")
    emp.add_argument("--outdir", default="data/raw/emp", help="Output directory")
    emp.add_argument("--biome", default=None, help="Biome filter string (e.g. 'forest', 'soil')")
    emp.add_argument("--max-samples", type=int, default=200, dest="max_samples")

    syn = dl_sub.add_parser("synthetic", help="Generate synthetic microbiome data for testing (no internet required)")
    syn.add_argument("--outdir", default="data/raw/synthetic", help="Output directory")
    syn.add_argument("--samples", type=int, default=80, help="Number of samples (default: 80)")
    syn.add_argument("--features", type=int, default=200, help="Number of ASV features (default: 200)")
    syn.add_argument("--seed", type=int, default=42)

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
            log_level=args.log_level,
        )

    elif args.command == "download":
        if args.source == "mgnify":
            from flora.io.downloaders import MGnifyDownloader

            dl = MGnifyDownloader(biome=args.biome)
            if args.analyses:
                files = dl.fetch_analyses(
                    study_accession=args.study,
                    output_dir=args.outdir,
                    max_analyses=args.max_samples,
                )
                print(f"Done.")
                for key, path in files.items():
                    print(f"  {key}: {path}")
            else:
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

        elif args.source == "emp":
            from flora.io.downloaders import EMPDownloader

            dl = EMPDownloader(biome_filter=args.biome)
            files = dl.fetch(output_dir=args.outdir, max_samples=args.max_samples)
            print("Done.")
            for key, path in files.items():
                print(f"  {key}: {path}")

        elif args.source == "synthetic":
            import numpy as np
            from pathlib import Path

            rng = np.random.default_rng(args.seed)
            n, f = args.samples, args.features
            out = Path(args.outdir)
            out.mkdir(parents=True, exist_ok=True)

            sids = [f"S{i:03d}" for i in range(n)]
            fids = [f"ASV_{j:04d}" for j in range(f)]
            biomes = ["Amazon", "Cerrado", "Atlantic_Forest", "Pantanal"] * (n // 4) + \
                     ["Amazon"] * (n % 4)
            counts = rng.negative_binomial(n=5, p=0.3, size=(n, f)).astype(int)

            # metadata.tsv
            meta_path = out / "metadata.tsv"
            with open(meta_path, "w") as fh:
                fh.write("sample_id\tbiome\tlocation\tlatitude\tlongitude\n")
                for i, sid in enumerate(sids):
                    fh.write(f"{sid}\t{biomes[i]}\tBrazil\t{-3.0 + i * 0.15:.4f}\t{-60.0 + i * 0.15:.4f}\n")

            # asv_table.tsv (wide: samples x features)
            asv_path = out / "asv_table.tsv"
            with open(asv_path, "w") as fh:
                fh.write("sample_id\t" + "\t".join(fids) + "\n")
                for i, sid in enumerate(sids):
                    fh.write(sid + "\t" + "\t".join(map(str, counts[i])) + "\n")

            # taxonomy.tsv
            phyla = ["Proteobacteria", "Firmicutes", "Bacteroidetes", "Actinobacteria", "Chloroflexi"]
            tax_path = out / "taxonomy.tsv"
            with open(tax_path, "w") as fh:
                fh.write("feature_id\tkingdom\tphylum\tclass\torder\tfamily\tgenus\tspecies\n")
                for j, fid in enumerate(fids):
                    fh.write(f"{fid}\tBacteria\t{phyla[j % len(phyla)]}\tClass_{j % 6}\tOrder_{j % 8}\tFamily_{j % 10}\tGenus_{j % 15}\t\n")

            print(f"Done. {n} samples, {f} features.")
            print(f"  metadata:  {meta_path}")
            print(f"  asv_table: {asv_path}")
            print(f"  taxonomy:  {tax_path}")
            print(f"\nNext step:")
            print(f"  flora run config.yaml --metadata {meta_path} --asv-table {asv_path} --taxonomy {tax_path}")

    elif args.command == "run":
        from flora.config.settings import load_config
        from flora.pipelines.main_pipeline import FLORAPipeline
        from pathlib import Path

        cfg = load_config(args.config)
        workdir = Path(args.workdir) if args.workdir else Path(cfg.storage.results_dir)
        raw_dir = Path(cfg.storage.raw_dir)

        metadata  = Path(args.metadata)  if args.metadata  else raw_dir / "metadata.tsv"
        asv_table = Path(args.asv_table) if args.asv_table else raw_dir / "asv_table.tsv"
        taxonomy  = Path(args.taxonomy)  if args.taxonomy  else raw_dir / "taxonomy.tsv"
        depth     = args.sampling_depth or cfg.pipeline.sampling_depth

        missing = [p for p in (metadata, asv_table, taxonomy) if not p.exists()]
        if missing:
            for p in missing:
                print(f"File not found: {p}")
            sys.exit(1)

        print(f"Config:    {args.config}")
        print(f"Workdir:   {workdir}")
        print(f"Metadata:  {metadata}")
        print(f"ASV table: {asv_table}")
        print(f"Taxonomy:  {taxonomy}")
        print(f"Depth:     {depth}")
        print()

        with FLORAPipeline(config=cfg, workdir=workdir) as pipeline:
            n_samples = pipeline.ingest_metadata(metadata)
            print(f"Samples ingested:     {n_samples}")

            n_obs = pipeline.ingest_asv_table(asv_table, wide_format=True)
            print(f"ASV observations:     {n_obs}")

            n_tax = pipeline.ingest_taxonomy(taxonomy)
            print(f"Taxonomy rows:        {n_tax}")

            diversity_df = pipeline.compute_diversity(sampling_depth=depth)
            print(f"Diversity computed:   {len(diversity_df)} samples")

            feature_matrix = pipeline.get_feature_matrix(
                normalize=cfg.pipeline.__dict__.get("normalization", "clr"),
                min_prevalence=0.1,
            )
            print(f"Feature matrix:       {feature_matrix.shape[0]} samples x {feature_matrix.shape[1] - 1} ASVs")

        db_path = workdir / "flora.duckdb"
        print(f"\nDone. Database: {db_path}")


if __name__ == "__main__":
    main()
