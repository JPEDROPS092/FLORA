"""Engine detection, workflow command building, result conversion and job running with fake tools."""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from biom import Table

from flora.engines import registry
from flora.engines import workflows as wf
from flora.engines.jobs import EngineError, JobManager

FAKE_QIIME = """#!PYTHON
import shutil, sys
from pathlib import Path

a = sys.argv[1:]
TAXONOMY = "Feature ID\\tTaxon\\tConfidence\\nASV1\\td__Bacteria; p__Proteobacteria; g__Rhizobium\\t0.99\\nASV2\\tD_0__Bacteria;D_1__Firmicutes\\t0.9\\n"


def opt(name):
    return a[a.index(name) + 1] if name in a else None


if a[:1] == ["--version"]:
    print("q2cli version 2099.1")
    sys.exit(0)
if a[:2] == ["tools", "export"]:
    src, dst = Path(opt("--input-path")), Path(opt("--output-path"))
    dst.mkdir(parents=True, exist_ok=True)
    if src.name == "table.qza":
        shutil.copy(Path(__file__).with_name("fixture.biom"), dst / "feature-table.biom")
    elif src.name == "taxonomy.qza":
        (dst / "taxonomy.tsv").write_text(TAXONOMY)
    sys.exit(0)
manifest = opt("--input-path")
if manifest and Path(manifest).is_file() and "--fail" in Path(manifest).read_text():
    print("boom")
    sys.exit(3)
for i, token in enumerate(a):
    if token.startswith("--o-") or token == "--output-path":
        target = Path(a[i + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
print("ok", " ".join(a[:3]))
""".replace("PYTHON", sys.executable)


@pytest.fixture()
def fake_bin(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    q = bindir / "qiime"
    q.write_text(FAKE_QIIME)
    q.chmod(q.stat().st_mode | stat.S_IEXEC)
    table = Table(np.array([[5, 0], [1, 7], [0, 2]]), ["ASV1", "ASV2", "ASV3"], ["S1", "S2"])
    from biom.util import biom_open

    with biom_open(str(bindir / "fixture.biom"), "w") as fh:
        table.to_hdf5(fh, "test")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    registry._cache.clear()
    yield bindir
    registry._cache.clear()


def test_detect_reports_missing_tool_with_install_hint(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    registry._cache.clear()
    by = {e["id"]: e for e in registry.detect_all(fresh=True)}
    assert not by["qiime2"]["available"] and "conda" in by["qiime2"]["install"] and by["qiime2"]["version"] == ""
    assert by["skbio"]["kind"] == "python"


def test_detect_finds_fake_qiime(fake_bin):
    by = {e["id"]: e for e in registry.detect_all(fresh=True)}
    assert by["qiime2"]["available"] and "2099.1" in by["qiime2"]["version"] and by["qiime2"]["install"] == ""


def test_qiime_commands_paired_and_single(tmp_path):
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("sample-id\tforward-absolute-filepath\n")
    cmds = wf.qiime2_dada2_commands(str(manifest), tmp_path / "o", True, {"trunc_len_f": 240, "trunc_len_r": 200}, None, 4)
    assert cmds[0][:3] == ["qiime", "tools", "import"] and "PairedEndFastqManifestPhred33V2" in cmds[0]
    assert cmds[1][2] == "denoise-paired" and "--p-trunc-len-r" in cmds[1] and cmds[1][cmds[1].index("--p-trunc-len-f") + 1] == "240"
    single = wf.qiime2_dada2_commands(str(manifest), tmp_path / "o", False, {}, None, 2)
    assert single[1][2] == "denoise-single" and "--p-trunc-len-r" not in single[1]
    clf = tmp_path / "clf.qza"
    clf.write_text("x")
    with_tax = wf.qiime2_dada2_commands(str(manifest), tmp_path / "o", True, {}, str(clf), 2, build_tree=True)
    assert any(c[1:3] == ["feature-classifier", "classify-sklearn"] for c in with_tax) and any(c[1] == "phylogeny" for c in with_tax)


def test_workflow_parameter_validation(tmp_path):
    with pytest.raises(wf.WorkflowError):
        wf.qiime2_dada2_commands(str(tmp_path / "missing.tsv"), tmp_path, True, {}, None, 1)
    m = tmp_path / "m.tsv"
    m.write_text("x")
    with pytest.raises(wf.WorkflowError):
        wf.qiime2_dada2_commands(str(m), tmp_path, True, {"trunc_len_f": "abc"}, None, 1)
    with pytest.raises(wf.WorkflowError):
        wf.qiime2_dada2_commands(str(m), tmp_path, True, {"trunc_len_f": 99999999}, None, 1)
    with pytest.raises(wf.WorkflowError):
        wf.dada2_r_command(str(tmp_path / "nofastq"), tmp_path, "ref.fa", {}, 1)


def test_parse_lineage_handles_modern_and_silva_old_formats():
    assert wf.parse_lineage("d__Bacteria; p__Proteobacteria; c__Alpha; g__Rhizobium")["genus"] == "Rhizobium"
    old = wf.parse_lineage("D_0__Bacteria;D_1__Firmicutes;D_5__Bacillus")
    assert (old["kingdom"], old["phylum"], old["genus"]) == ("Bacteria", "Firmicutes", "Bacillus")
    assert wf.parse_lineage("")["kingdom"] == ""


def _wait(mgr, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        job = mgr.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_qiime_job_runs_converts_and_ingests(fake_bin, tmp_path):
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("sample-id\tforward-absolute-filepath\n")
    classifier = tmp_path / "clf.qza"
    classifier.write_text("x")
    ingested = {}
    mgr = JobManager(tmp_path / "engines", ingest=lambda paths: ingested.update(paths) or {"samples": 2})
    job = mgr.start("qiime2-dada2", {"manifest": str(manifest), "paired": False, "classifier": str(classifier), "ingest": True})
    done = _wait(mgr, job["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-5:]
    asv = pl.read_csv(done["artifacts"]["asv_table"], separator="\t")
    assert asv["sample_id"].to_list() == ["S1", "S2"] and asv.columns == ["sample_id", "ASV1", "ASV2", "ASV3"]
    assert asv.filter(pl.col("sample_id") == "S2")["ASV2"].item() == 7
    tax = pl.read_csv(done["artifacts"]["taxonomy"], separator="\t")
    assert tax.filter(pl.col("feature_id") == "ASV1")["genus"].item() == "Rhizobium"
    assert tax.filter(pl.col("feature_id") == "ASV2")["phylum"].item() == "Firmicutes"
    assert done["ingest"] == {"samples": 2} and set(ingested) == {"metadata", "asv_table", "taxonomy"}
    assert done["progress"] == 100 and any("denoise-single" in line for line in done["log"])
    assert mgr.list()[0]["id"] == job["id"]


def test_job_fails_clearly_when_a_step_fails(fake_bin, tmp_path):
    bad = tmp_path / "manifest.tsv"
    bad.write_text("--fail")
    mgr = JobManager(tmp_path / "engines")
    done = _wait(mgr, mgr.start("qiime2-dada2", {"manifest": str(bad), "paired": False})["id"])
    assert done["status"] == "failed" and "código 3" in done["error"] and any("boom" in line for line in done["log"])


def test_unavailable_engine_is_refused_before_any_job_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    registry._cache.clear()
    mgr = JobManager(tmp_path / "engines")
    with pytest.raises(EngineError) as err:
        mgr.start("qiime2-dada2", {"manifest": "x"})
    assert err.value.code == "engine_unavailable" and err.value.status == 409 and "conda" in str(err.value)
    assert mgr.list() == []
    with pytest.raises(EngineError):
        mgr.start("nope", {})


def test_recover_marks_stale_running_jobs_failed(tmp_path):
    mgr = JobManager(tmp_path / "engines")
    mgr._save({"id": "a" * 12, "status": "running", "created_at": "2026-01-01T00:00:00+00:00", "error": "", "finished_at": ""})
    mgr.recover()
    assert mgr.get("a" * 12)["status"] == "failed"
    with pytest.raises(EngineError):
        mgr.get("../../etc/passwd")
