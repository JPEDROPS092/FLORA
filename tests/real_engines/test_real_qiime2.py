"""Real QIIME 2 (2024.10): the CLI workflow and the Python API bridge, on simulated amplicon reads."""

from __future__ import annotations

import gzip
import random
import time
from pathlib import Path

import polars as pl
import pytest

from flora.analysis.unifrac import parse_newick, unifrac
from flora.engines.jobs import JobManager

from .conftest import require


def _dna(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("ACGT") for _ in range(n))


def _reads(tmp_path: Path, samples=4, reads=5000, n_true=4, length=200, seed=11) -> tuple[Path, list[str]]:
    """Gzipped single-end FASTQ with a QIIME 2 manifest; every sample carries the same ``n_true`` variants."""
    rng = random.Random(seed)
    truth = [_dna(rng, length) for _ in range(n_true)]
    fq = tmp_path / "fastq"
    fq.mkdir()
    manifest = tmp_path / "manifest.tsv"
    rows = ["sample-id\tabsolute-filepath"]
    for s in range(samples):
        path = fq / f"S{s}.fastq.gz"
        with gzip.open(path, "wt") as fh:
            for i in range(reads):
                seq, qual = list(truth[(i + s) % n_true]), []
                for k in range(length):
                    q = max(20, 38 - k // 12 - rng.randint(0, 3))
                    qual.append(chr(33 + q))
                    if rng.random() < 10 ** (-q / 10):
                        seq[k] = rng.choice("ACGT")
                fh.write(f"@r{i}\n{''.join(seq)}\n+\n{''.join(qual)}\n")
        rows.append(f"S{s}\t{path}")
    manifest.write_text("\n".join(rows) + "\n")
    return manifest, truth


def _wait(mgr: JobManager, job_id: str, timeout: float = 1500):
    end = time.time() + timeout
    while time.time() < end:
        job = mgr.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(1)
    raise AssertionError("job timed out")


@pytest.mark.parametrize("backend", ["cli", "python"])
@require("qiime2")
def test_qiime2_dada2_workflow_recovers_the_true_variants(tmp_path, backend):
    manifest, _truth = _reads(tmp_path)
    mgr = JobManager(tmp_path / "engines")
    job = _wait(mgr, mgr.start("qiime2-dada2", {"manifest": str(manifest), "paired": False, "backend": backend, "build_tree": True,
                                                  "trunc_len_f": 0, "trim_left_f": 0, "threads": 2})["id"])
    assert job["status"] == "completed", f"{job['error']}\n" + "\n".join(job["log"][-30:])
    asv = pl.read_csv(job["artifacts"]["asv_table"], separator="\t")
    assert sorted(asv["sample_id"].to_list()) == ["S0", "S1", "S2", "S3"]
    assert asv.width - 1 == 4  # exactly the 4 true sequences, no spurious ones
    assert (asv.drop("sample_id").sum_horizontal() > 4000).all()  # most reads survive filtering and denoising

    # QIIME 2's own tree plugs straight into FLORA's UniFrac: tips are the feature ids of the table
    tree = parse_newick(Path(job["artifacts"]["tree"]).read_text())
    features = [c for c in asv.columns if c != "sample_id"]
    assert set(features) <= set(tree.tips)
    D, missing = unifrac(asv.drop("sample_id").to_numpy().astype(float), features, tree, weighted=True)
    assert missing == 0 and D.shape == (4, 4) and (D >= 0).all()
