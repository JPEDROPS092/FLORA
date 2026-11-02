"""Tests for downloader fallback and CLI DuckDB ingestion helper."""

import polars as pl

from flora.db.connection import FloraDB
from flora.io.downloaders import NCBISRADownloader
from flora.ui import cli
from flora.ui.cli import _ingest_download_to_duckdb


def test_sra_fetch_uses_ena_fallback_when_tools_missing(monkeypatch, tmp_path):
    outdir = tmp_path / "raw"
    outdir.mkdir(parents=True, exist_ok=True)

    downloader = NCBISRADownloader(n_jobs=2)

    monkeypatch.setattr(downloader, "_check_tools", lambda: ["prefetch", "fasterq-dump"])

    def _fake_ena(accessions, fastq_dir, skip_existing=True):
        fwd = fastq_dir / "SRR000001_1.fastq.gz"
        rev = fastq_dir / "SRR000001_2.fastq.gz"
        fwd.parent.mkdir(parents=True, exist_ok=True)
        fwd.write_text("x", encoding="utf-8")
        rev.write_text("x", encoding="utf-8")
        return [{"sample_id": "SRR000001", "forward": str(fwd.resolve()), "reverse": str(rev.resolve())}]

    monkeypatch.setattr(downloader, "_download_via_ena", _fake_ena)

    manifest = downloader.fetch(["SRR000001"], output_dir=outdir)

    manifest_df = pl.read_csv(manifest, separator="\t")
    assert manifest_df.height == 1
    assert manifest_df["sample-id"][0] == "SRR000001"


def test_ingest_download_to_duckdb_from_manifest(tmp_path):
    outdir = tmp_path / "raw"
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = outdir / "manifest.tsv"
    manifest.write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        "S1\t/tmp/S1_1.fastq.gz\t/tmp/S1_2.fastq.gz\n"
        "S2\t/tmp/S2_1.fastq.gz\t/tmp/S2_2.fastq.gz\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "flora.duckdb"
    inserted = _ingest_download_to_duckdb(outdir, db_path)
    assert inserted == 2

    with FloraDB.connect(path=db_path) as db:
        n = db.query("SELECT COUNT(*) AS n FROM samples").to_polars()["n"][0]
        assert n == 2


def test_ingest_download_to_duckdb_prefers_metadata(tmp_path):
    outdir = tmp_path / "raw"
    outdir.mkdir(parents=True, exist_ok=True)

    (outdir / "metadata.tsv").write_text(
        "sample_id\tbiome\tlocation\n"
        "S10\tAmazon\tBrazil\n",
        encoding="utf-8",
    )
    (outdir / "manifest.tsv").write_text(
        "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n"
        "IGNORED\t/tmp/a\t/tmp/b\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "flora_meta.duckdb"
    inserted = _ingest_download_to_duckdb(outdir, db_path)
    # Return value reflects the source catalog, which registers samples from
    # both metadata.tsv (S10) and manifest.tsv (IGNORED).
    assert inserted == 2

    with FloraDB.connect(path=db_path) as db:
        # The analytical 'samples' table still prefers metadata.tsv.
        df = db.query("SELECT sample_id, biome, location FROM samples").to_polars()
        assert df.height == 1
        assert df["sample_id"][0] == "S10"
        assert df["biome"][0] == "Amazon"
        assert df["location"][0] == "Brazil"


def test_cli_ingest_subcommand(monkeypatch, tmp_path, capsys):
    outdir = tmp_path / "raw"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "metadata.tsv").write_text(
        "sample_id\tbiome\nS1\tAmazon\nS2\tCerrado\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "ingest.duckdb"
    monkeypatch.setattr(
        "sys.argv",
        ["flora", "ingest", str(outdir), "--duckdb-path", str(db_path)],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "DuckDB ingest complete: 2 samples" in out

    with FloraDB.connect(path=db_path) as db:
        n = db.query("SELECT COUNT(*) AS n FROM samples").to_polars()["n"][0]
        assert n == 2
