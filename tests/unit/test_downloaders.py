"""Tests for all download sources: MGnify, NCBI SRA (sra-tools + ENA fallback), EMP.

Network access is fully mocked. These tests validate the orchestration logic of
each downloader (manifest/metadata generation, fallback selection, URL parsing),
not the remote services themselves.
"""

from __future__ import annotations

import polars as pl
import pytest

import flora.io.downloaders as dl_mod
from flora.core.exceptions import IngestionError
from flora.io.downloaders import (
    EMPDownloader,
    MGnifyDownloader,
    NCBISRADownloader,
)


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, *, text: str = "", json_data=None, content: bytes = b"", ok: bool = True):
        self.text = text
        self._json = json_data
        self.content = content
        self.ok = ok

    def raise_for_status(self) -> None:
        if not self.ok:
            import requests

            raise requests.RequestException("HTTP error")

    def json(self):
        return self._json


def _make_fastq(path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# MGnify
# ---------------------------------------------------------------------------

def test_mgnify_fetch_builds_paired_manifest(monkeypatch, tmp_path):
    outdir = tmp_path / "raw"
    downloader = MGnifyDownloader(biome="root:Environmental:Terrestrial:Forest")

    samples = [
        {"id": "SRS001", "attributes": {"biome": {"id": "forest"}, "geo-loc-name": "Brazil"}},
        {"id": "SRS002", "attributes": {"biome": {"id": "forest"}, "geo-loc-name": "Brazil"}},
    ]

    monkeypatch.setattr(downloader, "_iter_paginated", lambda session, url: iter(samples))

    def fake_runs(session, sample_acc):
        return [
            {"run_id": "R1", "sample_id": sample_acc, "url": f"https://x/{sample_acc}_1.fastq.gz", "description": "forward"},
            {"run_id": "R1", "sample_id": sample_acc, "url": f"https://x/{sample_acc}_2.fastq.gz", "description": "reverse"},
        ]

    monkeypatch.setattr(downloader, "_get_sample_runs", fake_runs)

    def fake_download(url, dest, session=None, **kwargs):
        _make_fastq(dest)
        return dest

    monkeypatch.setattr(dl_mod, "_download_file", fake_download)

    manifest = downloader.fetch("MGYS00005116", output_dir=outdir, max_samples=10)

    df = pl.read_csv(manifest, separator="\t")
    assert df.height == 2
    assert set(df["sample-id"].to_list()) == {"SRS001", "SRS002"}
    assert (outdir / "metadata.tsv").exists()


def test_mgnify_fetch_raises_when_no_samples(monkeypatch, tmp_path):
    downloader = MGnifyDownloader()
    monkeypatch.setattr(downloader, "_iter_paginated", lambda session, url: iter([]))

    with pytest.raises(IngestionError):
        downloader.fetch("MGYS_EMPTY", output_dir=tmp_path / "raw", max_samples=5)


# ---------------------------------------------------------------------------
# NCBI SRA — ENA fallback
# ---------------------------------------------------------------------------

def test_sra_uses_ena_fallback_when_tools_missing(monkeypatch, tmp_path):
    outdir = tmp_path / "raw"
    outdir.mkdir(parents=True)
    downloader = NCBISRADownloader(n_jobs=2)

    monkeypatch.setattr(downloader, "_check_tools", lambda: ["prefetch", "fasterq-dump"])

    def fake_ena(accessions, fastq_dir, skip_existing=True):
        rows = []
        for acc in accessions:
            fwd = fastq_dir / f"{acc}_1.fastq.gz"
            rev = fastq_dir / f"{acc}_2.fastq.gz"
            _make_fastq(fwd)
            _make_fastq(rev)
            rows.append({"sample_id": acc, "forward": str(fwd.resolve()), "reverse": str(rev.resolve())})
        return rows

    monkeypatch.setattr(downloader, "_download_via_ena", fake_ena)

    manifest = downloader.fetch(["SRR7532201", "SRR7532202"], output_dir=outdir)

    df = pl.read_csv(manifest, separator="\t")
    assert df.height == 2
    assert set(df["sample-id"].to_list()) == {"SRR7532201", "SRR7532202"}


def test_sra_raises_when_tools_missing_and_fallback_disabled(monkeypatch, tmp_path):
    downloader = NCBISRADownloader(allow_ena_fallback=False)
    monkeypatch.setattr(downloader, "_check_tools", lambda: ["prefetch"])

    with pytest.raises(IngestionError):
        downloader.fetch(["SRR000001"], output_dir=tmp_path / "raw")


def test_sra_ena_url_parsing_normalizes_ftp(monkeypatch, tmp_path):
    downloader = NCBISRADownloader()

    tsv = (
        "run_accession\tfastq_ftp\n"
        "SRR000001\tftp.sra.ebi.ac.uk/vol1/SRR000001_1.fastq.gz;"
        "ftp://ftp.sra.ebi.ac.uk/vol1/SRR000001_2.fastq.gz\n"
    )

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return FakeResponse(text=tsv)

    urls = downloader._fetch_ena_fastq_urls("SRR000001", FakeSession())
    assert urls == [
        "https://ftp.sra.ebi.ac.uk/vol1/SRR000001_1.fastq.gz",
        "https://ftp.sra.ebi.ac.uk/vol1/SRR000001_2.fastq.gz",
    ]


def test_sra_download_via_ena_pairs_reads(monkeypatch, tmp_path):
    fastq_dir = tmp_path / "fastq"
    fastq_dir.mkdir(parents=True)
    downloader = NCBISRADownloader()

    monkeypatch.setattr(
        downloader,
        "_fetch_ena_fastq_urls",
        lambda acc, session: [
            f"https://x/{acc}_1.fastq.gz",
            f"https://x/{acc}_2.fastq.gz",
        ],
    )

    def fake_download(url, dest, session=None, **kwargs):
        _make_fastq(dest)
        return dest

    monkeypatch.setattr(dl_mod, "_download_file", fake_download)

    rows = downloader._download_via_ena(["SRR123"], fastq_dir)
    assert len(rows) == 1
    assert rows[0]["sample_id"] == "SRR123"
    assert rows[0]["forward"].endswith("SRR123_1.fastq.gz")
    assert rows[0]["reverse"].endswith("SRR123_2.fastq.gz")


# ---------------------------------------------------------------------------
# NCBI SRA — sra-tools path
# ---------------------------------------------------------------------------

def test_sra_uses_sra_tools_when_available(monkeypatch, tmp_path):
    outdir = tmp_path / "raw"
    downloader = NCBISRADownloader(n_jobs=1)

    # Pretend sra-tools is installed.
    monkeypatch.setattr(downloader, "_check_tools", lambda: [])

    fastq_dir = outdir / "fastq"

    def fake_run(cmd, desc):
        # Simulate fasterq-dump producing split FASTQ files.
        if cmd[0] == "fasterq-dump":
            _make_fastq(fastq_dir / "SRR123_1.fastq")
            _make_fastq(fastq_dir / "SRR123_2.fastq")

        class R:
            returncode = 0
            stderr = ""

        return R()

    monkeypatch.setattr(downloader, "_run", fake_run)

    manifest = downloader.fetch(["SRR123"], output_dir=outdir, skip_existing=False)

    df = pl.read_csv(manifest, separator="\t")
    assert df.height == 1
    assert df["sample-id"][0] == "SRR123"


# ---------------------------------------------------------------------------
# EMP / Qiita
# ---------------------------------------------------------------------------

def test_emp_fetch_study_writes_metadata(monkeypatch, tmp_path):
    outdir = tmp_path / "emp"
    downloader = EMPDownloader()

    class FakeSession:
        def get(self, url, timeout=None):
            if url.endswith("/study/100"):
                return FakeResponse(json_data={"title": "EMP Soil"})
            if url.endswith("/artifacts"):
                return FakeResponse(json_data={})
            if url.endswith("/samples/info"):
                return FakeResponse(content=b"sample_id\tbiome\nS1\tsoil\n", ok=True)
            return FakeResponse(json_data={})

    monkeypatch.setattr(dl_mod, "_make_session", lambda *a, **k: FakeSession())

    result = downloader.fetch_study(100, output_dir=outdir)
    assert result == outdir
    assert (outdir / "metadata.tsv").exists()
    assert "sample_id" in (outdir / "metadata.tsv").read_text(encoding="utf-8")


def test_emp_fetch_study_raises_on_http_error(monkeypatch, tmp_path):
    downloader = EMPDownloader()

    class FakeSession:
        def get(self, url, timeout=None):
            return FakeResponse(ok=False)

    monkeypatch.setattr(dl_mod, "_make_session", lambda *a, **k: FakeSession())

    with pytest.raises(IngestionError):
        downloader.fetch_study(999, output_dir=tmp_path / "emp")


def test_emp_fetch_artifact_downloads_file(monkeypatch, tmp_path):
    downloader = EMPDownloader()

    monkeypatch.setattr(dl_mod, "_make_session", lambda *a, **k: object())

    def fake_download(url, dest, session=None, **kwargs):
        _make_fastq(dest, content="biomdata")
        return dest

    monkeypatch.setattr(dl_mod, "_download_file", fake_download)

    out = downloader.fetch_artifact(42, output_dir=tmp_path / "emp")
    assert out.exists()
    assert out.name == "artifact_42.biom"
