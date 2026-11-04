"""Real cutadapt, VSEARCH, vegan, ALDEx2, ANCOM-BC2, DADA2 and scikit-bio, checked against FLORA's own results.

These skip until the tools are connected. Where possible FLORA's numbers are compared with the tool's: the
PERMANOVA F against vegan::adonis2 and scikit-bio, UniFrac against scikit-bio.
"""

from __future__ import annotations

import io
import random
import time
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from flora.analysis import stats
from flora.analysis.unifrac import parse_newick, unifrac
from flora.engines import registry
from flora.engines import workflows as wf
from flora.engines.jobs import JobManager

from .conftest import require


def _wait(mgr: JobManager, job_id: str, timeout: float = 900):
    end = time.time() + timeout
    while time.time() < end:
        job = mgr.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.5)
    raise AssertionError("job timed out")


def _ok(job):
    assert job["status"] == "completed", f"{job['error']}\n" + "\n".join(job["log"][-25:])
    return job


def _dna(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("ACGT") for _ in range(n))


def _grouped_table(tmp_path: Path, n_per_group=12, n_features=20, effect_feature=0, fold=12, seed=3):
    """Samples x features counts with one feature much higher in group b, plus the matching metadata."""
    rng = np.random.default_rng(seed)
    rows, meta = [], []
    for g in ("a", "b"):
        for i in range(n_per_group):
            counts = rng.poisson(30, n_features).astype(int)
            if g == "b":
                counts[effect_feature] *= fold
            rows.append([f"{g}{i:02d}", *counts.tolist()])
            meta.append((f"{g}{i:02d}", g))
    asv = tmp_path / "asv.tsv"
    pl.DataFrame(rows, schema=["sample_id", *[f"F{j}" for j in range(n_features)]], orient="row").write_csv(asv, separator="\t")
    meta_path = tmp_path / "meta.tsv"
    pl.DataFrame(meta, schema=["sample_id", "group"], orient="row").write_csv(meta_path, separator="\t")
    return {"asv": str(asv), "metadata": str(meta_path)}, np.array([r[1:] for r in rows], dtype=float), [m[1] for m in meta]


# ---------------------------------------------------------------------------
@require("cutadapt")
def test_cutadapt_removes_the_primer_from_real_reads(tmp_path):
    rng = random.Random(1)
    primer = "GTGYCAGCMGCCGCGGTAA"
    concrete = "GTGCCAGCAGCCGCGGTAA"  # one IUPAC-compatible instance of the primer
    fq = tmp_path / "fq"
    fq.mkdir()
    bodies = []
    with open(fq / "S1_R1.fastq", "w") as fh:
        for i in range(20):
            body = _dna(rng, 120)
            bodies.append(body)
            fh.write(f"@r{i}\n{concrete}{body}\n+\n{'I' * (len(concrete) + len(body))}\n")
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("cutadapt-trim", {"fastq_dir": str(fq), "fwd_primer": primer})["id"]))
    out = (tmp_path / "engines" / job["id"] / "trimmed" / "S1_R1.fastq").read_text().splitlines()
    assert out[1::4] == bodies  # primer gone, reads intact
    assert Path(job["artifacts"]["manifest"]).read_text().splitlines()[1].startswith("S1\t")


@require("vsearch")
def test_vsearch_clusters_near_identical_asvs_into_one_otu(tmp_path):
    rng = random.Random(2)
    a = _dna(rng, 200)
    a_mut = a[:100] + ("A" if a[100] != "A" else "C") + a[101:]  # 1 mismatch in 200 bp = 99.5 % identity
    other = _dna(rng, 200)
    fasta = tmp_path / "asvs.fasta"
    fasta.write_text(f">F0\n{a}\n>F1\n{a_mut}\n>F2\n{other}\n")
    files = {"asv": str(tmp_path / "asv.tsv")}
    Path(files["asv"]).write_text("sample_id\tF0\tF1\tF2\nS1\t5\t3\t0\nS2\t1\t0\t7\n")
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("vsearch-otu", {"fasta": str(fasta), "identity": 0.97}, files)["id"]))
    otu = pl.read_csv(job["artifacts"]["otu_table"], separator="\t")
    assert otu.width == 3  # sample_id + 2 OTUs
    assert otu.drop("sample_id").sum_horizontal().to_list() == [8, 8]  # reads conserved
    mapping = dict(pl.read_csv(job["artifacts"]["asv_to_otu"], separator="\t").iter_rows())
    assert mapping["F0"] == mapping["F1"] != mapping["F2"]


@require("vegan")
def test_vegan_permanova_f_equals_floras(tmp_path):
    files, X, groups = _grouped_table(tmp_path)
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("vegan", {"group_by": "group", "metric": "bray_curtis", "permutations": 999}, files)["id"]))
    rows = wf.parse_diff_results(Path(job["artifacts"]["results"]))["rows"]
    vegan_f = float(rows[0]["statistic"])
    mine = stats.permanova(stats.distance_matrix(X, "bray_curtis"), groups, permutations=999)
    assert vegan_f == pytest.approx(mine["f"], rel=1e-6)
    assert float(rows[0]["p"]) < 0.05 and mine["p"] < 0.05


@require("aldex2")
def test_aldex2_finds_the_differential_feature(tmp_path):
    files, _X, _g = _grouped_table(tmp_path, effect_feature=3)
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("aldex2", {"group_by": "group", "a": "a", "b": "b"}, files)["id"]))
    rows = wf.parse_diff_results(Path(job["artifacts"]["results"]))["rows"]
    assert rows[0]["feature_id"] == "F3" and float(rows[0]["q"]) < 0.05 and float(rows[0]["diff_btw"]) > 0


@require("ancombc2")
def test_ancombc2_finds_the_differential_feature(tmp_path):
    files, _X, _g = _grouped_table(tmp_path, effect_feature=3)
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("ancombc2", {"group_by": "group", "a": "a", "b": "b"}, files)["id"]))
    rows = wf.parse_diff_results(Path(job["artifacts"]["results"]))["rows"]
    assert "F3" in [r["feature_id"] for r in rows[:3]] and float(rows[0]["diff_btw"]) != 0


@require("skbio")
def test_skbio_agrees_with_floras_permanova_and_unifrac(tmp_path):
    import json
    import subprocess

    from flora.engines.skbio_bridge import __file__ as bridge

    python = registry.skbio_python()

    def skbio(op: str, spec: dict) -> dict:
        path = tmp_path / f"{op}.json"
        path.write_text(json.dumps(spec))
        done = subprocess.run([python, bridge, op, str(path)], capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    rng = np.random.default_rng(0)
    X = rng.poisson(20, (16, 8)).astype(int)
    X[8:, :3] *= 5
    ids = [f"S{i}" for i in range(16)]
    groups = ["a"] * 8 + ["b"] * 8
    D = stats.distance_matrix(X, "bray_curtis")
    theirs = skbio("permanova", {"distances": D.tolist(), "ids": ids, "groups": groups, "permutations": 99})
    assert stats.permanova(D, groups, permutations=99)["f"] == pytest.approx(theirs["f"], rel=1e-9)

    newick = "(((F0:0.1,F1:0.2):0.3,(F2:0.1,F3:0.4):0.2):0.1,((F4:0.2,F5:0.1):0.3,(F6:0.3,F7:0.1):0.2):0.4);"
    features = [f"F{j}" for j in range(8)]
    for weighted in (False, True):
        ref = np.array(skbio("unifrac", {"counts": X.tolist(), "features": features, "newick": newick, "weighted": weighted})["distances"])
        mine, _ = unifrac(X.astype(float), features, parse_newick(newick), weighted=weighted)
        assert np.allclose(mine, ref, atol=1e-8), "weighted" if weighted else "unweighted"


@require("dada2")
def test_dada2_runs_on_simulated_amplicon_reads(tmp_path):
    """Four samples of simulated 200 bp amplicons from 4 true sequences, with sequencing errors."""
    rng = random.Random(5)
    truth = [_dna(rng, 200) for _ in range(4)]
    fq = tmp_path / "fastq"
    fq.mkdir()
    for s in range(4):
        with open(fq / f"S{s}_R1.fastq", "w") as fh:
            for i in range(6000):
                seq = list(truth[(i + s) % 4])
                qual = []
                for k in range(len(seq)):
                    q = max(20, 38 - k // 12 - rng.randint(0, 3))
                    qual.append(chr(33 + q))
                    if rng.random() < 10 ** (-q / 10):
                        seq[k] = rng.choice("ACGT")
                fh.write(f"@r{i}\n{''.join(seq)}\n+\n{''.join(qual)}\n")
    ref = tmp_path / "ref.fa"
    with open(ref, "w") as fh:
        for i, t in enumerate(truth):
            for j in range(3):  # a few copies so assignTaxonomy has something to learn from
                fh.write(f">Bacteria;Phylum{i};Class{i};Order{i};Family{i};Genus{i};\n{t}\n")
    mgr = JobManager(tmp_path / "engines")
    job = _ok(_wait(mgr, mgr.start("dada2-r", {"fastq_dir": str(fq), "ref_fasta": str(ref), "trunc_len_f": 0, "trunc_len_r": 0, "threads": 2})["id"]))
    asv = pl.read_csv(job["artifacts"]["asv_table"], separator="\t")
    assert asv.height == 4 and asv.width - 1 == 4  # 4 samples, exactly the 4 true variants recovered
    assert registry.detect("dada2") is not None
