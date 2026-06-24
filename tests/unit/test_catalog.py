"""Tests for the source-aware download catalog (sample_catalog, files, views)."""

from __future__ import annotations

import json

from flora.db.connection import FloraDB
from flora.db.ingestion import detect_source, ingest_download_catalog
from flora.db.schema import initialize_schema


def _db():
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    return db


def test_detect_source_by_prefix():
    assert detect_source(["MGYS00005116"]) == "mgnify"
    assert detect_source(["SRR7532201"]) == "sra"
    assert detect_source(["ERR123456"]) == "ena"
    assert detect_source(["UNKNOWN123"]) == "sra"  # default


def test_schema_seeds_sources():
    db = _db()
    rows = db.query("SELECT source FROM sources ORDER BY source").to_polars()["source"].to_list()
    assert set(rows) == {"sra", "ena", "mgnify", "emp"}
    db.close()


def test_ingest_catalog_from_manifest_and_metadata(tmp_path):
    out = tmp_path / "raw"
    fastq = out / "fastq"
    fastq.mkdir(parents=True)
    fwd = fastq / "SRR1_1.fastq.gz"
    rev = fastq / "SRR1_2.fastq.gz"
    fwd.write_text("aaaa", encoding="utf-8")
    rev.write_text("bbbb", encoding="utf-8")

    (out / "manifest.tsv").write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        f"SRR1\t{fwd.resolve()}\t{rev.resolve()}\n",
        encoding="utf-8",
    )
    (out / "metadata.tsv").write_text(
        "sample_id\tbiome\tlocation\torganism\tstudy_accession\n"
        "SRR1\troot:Environmental:Terrestrial:Soil\tBrazil\tsoil metagenome\tSRP151124\n",
        encoding="utf-8",
    )

    db = _db()
    n = ingest_download_catalog(db, out, source="sra")
    assert n == 1

    cat = db.query("SELECT * FROM sample_catalog").to_polars()
    assert cat.height == 1
    assert cat["source"][0] == "sra"
    assert cat["biome"][0] == "root:Environmental:Terrestrial:Soil"
    assert cat["study_accession"][0] == "SRP151124"
    assert cat["layout"][0] == "paired"

    files = db.query("SELECT * FROM files ORDER BY file_name").to_polars()
    assert files.height == 2
    assert files["size_bytes"].to_list() == [4, 4]
    assert set(files["direction"].to_list()) == {"forward", "reverse"}
    db.close()


def test_ingest_catalog_checksums(tmp_path):
    out = tmp_path / "raw"
    fastq = out / "fastq"
    fastq.mkdir(parents=True)
    fwd = fastq / "SRR9_1.fastq"
    fwd.write_text("hello", encoding="utf-8")
    (out / "manifest.tsv").write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        f"SRR9\t{fwd.resolve()}\t\n",
        encoding="utf-8",
    )

    db = _db()
    ingest_download_catalog(db, out, source="sra", compute_checksums=True)
    files = db.query("SELECT checksum, checksum_algo, direction FROM files").to_polars()
    assert files["checksum_algo"][0] == "md5"
    assert files["checksum"][0] is not None
    assert files["direction"][0] == "single"
    db.close()


def test_ingest_catalog_is_incremental(tmp_path):
    out = tmp_path / "raw"
    out.mkdir(parents=True)
    (out / "manifest.tsv").write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        "SRR1\t/tmp/SRR1_1.fastq.gz\t/tmp/SRR1_2.fastq.gz\n",
        encoding="utf-8",
    )

    db = _db()
    ingest_download_catalog(db, out, source="sra")
    ingest_download_catalog(db, out, source="sra")  # re-run must not duplicate

    n = db.query("SELECT COUNT(*) AS n FROM sample_catalog").to_polars()["n"][0]
    assert n == 1
    nf = db.query("SELECT COUNT(*) AS n FROM files").to_polars()["n"][0]
    assert nf == 2
    db.close()


def test_metadata_extra_columns_go_to_json(tmp_path):
    out = tmp_path / "raw"
    out.mkdir(parents=True)
    (out / "metadata.tsv").write_text(
        "sample_id\tbiome\tcustom_field\tdepth_m\n"
        "S1\tsoil\tabc\t12\n",
        encoding="utf-8",
    )

    db = _db()
    ingest_download_catalog(db, out, source="mgnify")
    row = db.query(
        "SELECT json_extract_string(metadata, '$.custom_field') AS cf FROM sample_catalog"
    ).to_polars()
    assert row["cf"][0] == "abc"
    db.close()


def test_views_summary_and_aggregations(tmp_path):
    out = tmp_path / "raw"
    fastq = out / "fastq"
    fastq.mkdir(parents=True)
    f1 = fastq / "S1_1.fastq.gz"
    f1.write_text("xxxxxxxx", encoding="utf-8")  # 8 bytes
    (out / "manifest.tsv").write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        f"S1\t{f1.resolve()}\t\n",
        encoding="utf-8",
    )
    (out / "metadata.tsv").write_text(
        "sample_id\tbiome\tstudy_accession\n"
        "S1\tsoil\tMGYS1\n",
        encoding="utf-8",
    )

    db = _db()
    ingest_download_catalog(db, out, source="mgnify")

    summary = db.query("SELECT * FROM v_sample_summary").to_polars()
    assert summary.height == 1
    assert summary["n_files"][0] == 1
    assert summary["total_bytes"][0] == 8

    study = db.query("SELECT * FROM v_study_stats").to_polars()
    assert study["n_samples"][0] == 1

    biome = db.query("SELECT * FROM v_biome_aggregation").to_polars()
    assert biome["biome"][0] == "soil"
    assert biome["n_samples"][0] == 1
    db.close()
