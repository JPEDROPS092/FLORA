"""Download and prepare a MGnify study for FLORA processing.

This example turns a MGnify study accession into FLORA-ready files:

- ``metadata.tsv``
- ``asv_table.tsv``
- ``taxonomy.tsv``

Optionally, it can also print the exact ``flora run`` command to execute next.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import polars as pl

from flora.io import MGnifyDownloader


def _summarize_tsvs(metadata_path: Path, asv_path: Path, taxonomy_path: Path) -> None:
    metadata = pl.read_csv(metadata_path, separator="\t")
    asv = pl.read_csv(asv_path, separator="\t")
    taxonomy = pl.read_csv(taxonomy_path, separator="\t")

    n_samples = metadata.height
    n_taxa = taxonomy.height
    n_features = max(asv.width - 1, 0)

    print("\nStudy prepared for FLORA")
    print("=" * 50)
    print(f"Samples in metadata : {n_samples}")
    print(f"ASV features        : {n_features}")
    print(f"Taxonomy rows       : {n_taxa}")

    if "biome" in metadata.columns:
        biome_counts = (
            metadata.group_by("biome")
            .len()
            .sort("len", descending=True)
            .head(5)
        )
        print("\nTop biome labels")
        for row in biome_counts.iter_rows(named=True):
            print(f"  {row['biome']}: {row['len']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download pre-computed MGnify analyses and prepare a FLORA-ready study dataset."
    )
    parser.add_argument("study", help="MGnify study accession, e.g. MGYS00005292")
    parser.add_argument(
        "--outdir",
        default=None,
        help="Output directory. Defaults to data/raw/<study>.",
    )
    parser.add_argument(
        "--biome",
        default="root:Environmental:Terrestrial",
        help="Biome label fallback for metadata rows.",
    )
    parser.add_argument(
        "--max-analyses",
        type=int,
        default=20,
        help="Maximum analyses to inspect for OTU/taxonomy files.",
    )
    parser.add_argument(
        "--print-run-command",
        action="store_true",
        help="Print the recommended flora run command at the end.",
    )
    parser.add_argument(
        "--workdir",
        default="results",
        help="Suggested workdir to use in the printed flora run command.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    outdir = Path(args.outdir) if args.outdir else Path("data/raw") / args.study
    logger = logging.getLogger("examples.process_mgnify_study")

    logger.info("Preparing MGnify study=%s", args.study)
    logger.info("Output directory: %s", outdir)
    logger.info("Max analyses to inspect: %d", args.max_analyses)

    downloader = MGnifyDownloader(biome=args.biome)
    logger.info("Starting MGnify analysis download")
    files = downloader.fetch_analyses(
        study_accession=args.study,
        output_dir=outdir,
        max_analyses=args.max_analyses,
    )
    logger.info("MGnify analysis download finished")

    print("Done.")
    for key, path in files.items():
        print(f"  {key}: {path}")

    logger.info("Reading generated TSV files for summary")
    _summarize_tsvs(
        metadata_path=files["metadata"],
        asv_path=files["asv_table"],
        taxonomy_path=files["taxonomy"],
    )

    if args.print_run_command:
        logger.info("Printing recommended flora run command")
        print("\nNext step")
        print(
            "  flora run config.yaml"
            f" --workdir {args.workdir}"
            f" --metadata {files['metadata']}"
            f" --asv-table {files['asv_table']}"
            f" --taxonomy {files['taxonomy']}"
        )


if __name__ == "__main__":
    main()
