"""Download and log UI handlers."""

from __future__ import annotations

import logging
from pathlib import Path

from flora.ui.http import UiHttpError, json_success

logger = logging.getLogger("flora.ui.downloads")


def get_logs(log_buffer: list[str], params: dict):
    count = min(int(params.get("n", ["100"])[0]), 500)
    return json_success(data={"lines": log_buffer[-count:]})


def download_mgnify(state, body: dict):
    from flora.io.downloaders import MGnifyDownloader

    study = body.get("study_accession", "")
    if not study:
        raise UiHttpError("study_accession is required", code="missing_study_accession")

    biome = body.get("biome", "root:Environmental:Terrestrial")
    output_dir = body.get("output_dir", str(state.workdir / "raw"))
    max_samples = int(body.get("max_samples", 20))

    downloader = MGnifyDownloader(biome=biome)
    try:
        manifest = downloader.fetch(
            study_accession=study,
            output_dir=output_dir,
            max_samples=max_samples,
        )
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    return json_success(data={"manifest": str(manifest), "output_dir": output_dir})


def download_sra(state, body: dict):
    from flora.io.downloaders import NCBISRADownloader

    accessions = body.get("accessions", [])
    if not accessions:
        raise UiHttpError("accessions list is required", code="missing_accessions")

    output_dir = body.get("output_dir", str(state.workdir / "raw"))
    jobs = int(body.get("n_jobs", 4))

    downloader = NCBISRADownloader(n_jobs=jobs)
    try:
        manifest = downloader.fetch(accessions=accessions, output_dir=output_dir)
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    return json_success(data={"manifest": str(manifest), "accessions": accessions})


def download_emp(state, body: dict):
    from flora.io.downloaders import EMPDownloader

    output_dir = body.get("output_dir", str(state.workdir / "raw" / "emp"))
    biome = body.get("biome_filter") or None
    max_samples = int(body.get("max_samples", 200))

    downloader = EMPDownloader(biome_filter=biome)
    try:
        files = downloader.fetch(output_dir=output_dir, max_samples=max_samples)
    except Exception as exc:
        raise UiHttpError(str(exc), code="download_failed") from exc

    return json_success(
        data={
            "asv_table": str(files["asv_table"]),
            "taxonomy": str(files["taxonomy"]),
            "metadata": str(files["metadata"]),
        }
    )


def download_synthetic(state, body: dict):
    import numpy as np

    output_dir = Path(body.get("output_dir", str(state.workdir / "raw" / "synthetic")))

    sample_count = int(body.get("samples", 80))
    feature_count = int(body.get("features", 200))
    seed = int(body.get("seed", 42))

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    sample_ids = [f"S{i:03d}" for i in range(sample_count)]
    feature_ids = [f"ASV_{j:04d}" for j in range(feature_count)]
    biomes = (["Amazon", "Cerrado", "Atlantic_Forest", "Pantanal"] * (sample_count // 4 + 1))[
        :sample_count
    ]
    counts = rng.negative_binomial(n=5, p=0.3, size=(sample_count, feature_count)).astype(int)

    metadata_path = output_dir / "metadata.tsv"
    with open(metadata_path, "w", encoding="utf-8") as file:
        file.write("sample_id\tbiome\tlocation\n")
        for index, sample_id in enumerate(sample_ids):
            file.write(f"{sample_id}\t{biomes[index]}\tBrazil\n")

    asv_path = output_dir / "asv_table.tsv"
    with open(asv_path, "w", encoding="utf-8") as file:
        file.write("sample_id\t" + "\t".join(feature_ids) + "\n")
        for index, sample_id in enumerate(sample_ids):
            file.write(sample_id + "\t" + "\t".join(map(str, counts[index])) + "\n")

    phyla = [
        "Proteobacteria",
        "Firmicutes",
        "Bacteroidetes",
        "Actinobacteria",
        "Chloroflexi",
    ]
    taxonomy_path = output_dir / "taxonomy.tsv"
    with open(taxonomy_path, "w", encoding="utf-8") as file:
        file.write("feature_id\tkingdom\tphylum\tclass\torder\tfamily\tgenus\tspecies\n")
        for index, feature_id in enumerate(feature_ids):
            file.write(
                f"{feature_id}\tBacteria\t{phyla[index % len(phyla)]}\t"
                f"Class_{index % 6}\tOrder_{index % 8}\tFamily_{index % 10}\tGenus_{index % 15}\t\n"
            )

    logger.info(
        "Synthetic data generated: %d samples, %d features -> %s",
        sample_count,
        feature_count,
        output_dir,
    )
    return json_success(
        data={
            "asv_table": str(asv_path),
            "taxonomy": str(taxonomy_path),
            "metadata": str(metadata_path),
        }
    )
