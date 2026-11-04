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


# ---------------------------------------------------------------------------
# R workflows, cutadapt and VSEARCH with fake executables
# ---------------------------------------------------------------------------
FAKE_RSCRIPT = """#!PYTHON
import sys
from pathlib import Path

a = sys.argv[1:]
if "-e" in a:
    print("9.9.9")
    sys.exit(0)
script = Path(a[1]).name
out = Path(a[-1])
if script in ("ancombc2.R", "aldex2.R"):
    out.write_text("feature_id\\tdiff_btw\\teffect\\tp\\tq\\nF1\\t1.5\\t1.2\\t0.001\\t0.01\\nF2\\t-0.2\\t-0.1\\t0.5\\t0.6\\nF3\\t2.0\\t1.0\\t0.01\\t0.04\\n")
elif script == "vegan.R":
    out.write_text("test\\tstatistic\\tr2\\tp\\nPERMANOVA (adonis2)\\t12.3\\t0.4\\t0.001\\nPERMDISP (betadisper)\\t1.1\\tNA\\t0.3\\n")
print("ran", script)
""".replace("PYTHON", sys.executable)

FAKE_CUTADAPT = """#!PYTHON
import shutil, sys
from pathlib import Path

a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("4.9")
    sys.exit(0)
o = a[a.index("-o") + 1]
inputs = a[-2:] if "-p" in a else a[-1:]  # positional FASTQ files come last
Path(o).parent.mkdir(parents=True, exist_ok=True)
shutil.copy(inputs[0], o)
if "-p" in a:
    shutil.copy(inputs[1], a[a.index("-p") + 1])
print("trimmed", Path(o).name)
""".replace("PYTHON", sys.executable)

FAKE_VSEARCH = """#!PYTHON
import sys
from pathlib import Path

a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("vsearch v2.28")
    sys.exit(0)
Path(a[a.index("--centroids") + 1]).write_text(">F1\\nACGT\\n>F3\\nTTTT\\n")
Path(a[a.index("--uc") + 1]).write_text("S\\t0\\t4\\t*\\t*\\t*\\t*\\t*\\tF1\\t*\\nH\\t0\\t4\\t99.0\\t+\\t0\\t0\\t*\\tF2\\tF1\\nS\\t1\\t4\\t*\\t*\\t*\\t*\\t*\\tF3\\t*\\n")
print("clustered")
""".replace("PYTHON", sys.executable)


@pytest.fixture()
def fake_tools(tmp_path, monkeypatch):
    bindir = tmp_path / "tools"
    bindir.mkdir()
    for name, body in (("Rscript", FAKE_RSCRIPT), ("cutadapt", FAKE_CUTADAPT), ("vsearch", FAKE_VSEARCH)):
        f = bindir / name
        f.write_text(body)
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    registry._cache.clear()
    yield bindir
    registry._cache.clear()


def _project_files(tmp_path):
    asv = tmp_path / "asv.tsv"
    asv.write_text("sample_id\tF1\tF2\tF3\nS1\t5\t3\t0\nS2\t1\t0\t7\nS3\t2\t2\t2\n")
    meta = tmp_path / "meta.tsv"
    meta.write_text("sample_id\tbiome\nS1\ta\nS2\tb\nS3\tb\n")
    return {"asv": str(asv), "metadata": str(meta)}


@pytest.mark.parametrize("kind", ["aldex2", "ancombc2"])
def test_differential_r_workflows_produce_a_sorted_result_table(fake_tools, tmp_path, kind):
    mgr = JobManager(tmp_path / "engines")
    job = mgr.start(kind, {"group_by": "biome", "a": "a", "b": "b"}, _project_files(tmp_path))
    done = _wait(mgr, job["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-4:]
    table = wf.parse_diff_results(Path(done["artifacts"]["results"]))
    assert [r["feature_id"] for r in table["rows"]] == ["F1", "F3", "F2"] and table["total"] == 3  # sorted by q


def test_vegan_workflow_and_metric_validation(fake_tools, tmp_path):
    mgr = JobManager(tmp_path / "engines")
    done = _wait(mgr, mgr.start("vegan", {"group_by": "biome", "metric": "aitchison", "permutations": 199}, _project_files(tmp_path))["id"])
    assert done["status"] == "completed"
    rows = wf.parse_diff_results(Path(done["artifacts"]["results"]))["rows"]
    assert rows[0]["test"].startswith("PERMANOVA") and rows[1]["test"].startswith("PERMDISP")
    with pytest.raises(EngineError) as err:
        mgr.start("vegan", {"group_by": "biome", "metric": "unifrac"}, _project_files(tmp_path))
    assert err.value.code == "invalid_params"


def test_cutadapt_trims_pairs_and_writes_a_qiime_manifest(fake_tools, tmp_path):
    fq = tmp_path / "fastq"
    fq.mkdir()
    for sample in ("S1", "S2"):
        (fq / f"{sample}_R1.fastq").write_text("@r\nACGT\n+\nIIII\n")
        (fq / f"{sample}_R2.fastq").write_text("@r\nTTTT\n+\nIIII\n")
    mgr = JobManager(tmp_path / "engines")
    params = {"fastq_dir": str(fq), "fwd_primer": "GTGYCAGCMGCCGCGGTAA", "rev_primer": "GGACTACNVGGGTWTCTAAT"}
    job = mgr.start("cutadapt-trim", params)
    assert job["steps"] == ["cutadapt S1", "cutadapt S2"]
    done = _wait(mgr, job["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-4:]
    lines = Path(done["artifacts"]["manifest"]).read_text().splitlines()
    assert lines[0] == "sample-id\tforward-absolute-filepath\treverse-absolute-filepath" and len(lines) == 3
    assert all(Path(c).is_absolute() for c in lines[1].split("\t")[1:])
    assert any("-g GTGYCAGCMGCCGCGGTAA" in line for line in done["log"])


@pytest.mark.parametrize("fwd", ["", "ACGT", "ACGT; rm -rf /xxxxxxxx", "GTGY CAGC"])
def test_cutadapt_rejects_bad_primers(fake_tools, tmp_path, fwd):
    (tmp_path / "fq").mkdir()
    (tmp_path / "fq" / "S_R1.fastq").write_text("x")
    with pytest.raises(EngineError):
        JobManager(tmp_path / "engines").start("cutadapt-trim", {"fastq_dir": str(tmp_path / "fq"), "fwd_primer": fwd})


def test_vsearch_collapses_asvs_into_otus(fake_tools, tmp_path):
    files = _project_files(tmp_path)
    fasta = tmp_path / "asvs.fasta"
    fasta.write_text(">F1\nACGT\n>F2\nACGA\n>F3\nTTTT\n")
    mgr = JobManager(tmp_path / "engines")
    done = _wait(mgr, mgr.start("vsearch-otu", {"fasta": str(fasta), "identity": 0.97}, files)["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-4:]
    otu = pl.read_csv(done["artifacts"]["otu_table"], separator="\t")
    assert otu.columns == ["sample_id", "F1", "F3"]
    assert otu.filter(pl.col("sample_id") == "S1")["F1"].item() == 8  # F1 + F2 joined cluster F1
    assert pl.read_csv(done["artifacts"]["asv_to_otu"], separator="\t").filter(pl.col("asv") == "F2")["otu"].item() == "F1"
    with pytest.raises(EngineError):
        mgr.start("vsearch-otu", {"fasta": str(fasta), "identity": 2}, files)


def test_job_results_endpoint_builds_a_volcano(fake_tools, tmp_path):
    from types import SimpleNamespace

    from flora.db.connection import FloraDB
    from flora.db.schema import initialize_schema
    from flora.ui.handlers import engines as handler
    from flora.ui.http import UiHttpError

    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    db.load_dataframe("taxonomy", pl.DataFrame({"feature_id": ["F1"], "kingdom": ["B"], "phylum": ["P"], "class": ["c"], "order": ["o"], "family": ["f"], "genus": ["Rhizobium"],
                                                "species": [None], "confidence": [None]}, schema_overrides={"species": pl.Utf8, "confidence": pl.Float64}))
    state = SimpleNamespace(data_dir=tmp_path / "proj", db=db, pipeline=None)
    mgr = handler.manager(state)
    done = _wait(mgr, mgr.start("ancombc2", {"group_by": "biome", "a": "a", "b": "b"}, _project_files(tmp_path))["id"])
    out = handler.job_results(state, {"id": [done["id"]]})
    assert out["rows"][0]["taxon"] == "Rhizobium" and out["plot"]["data"][0]["x"]
    other = mgr.start("vegan", {"group_by": "biome", "metric": "bray_curtis"}, _project_files(tmp_path))
    _wait(mgr, other["id"])
    assert handler.job_results(state, {"id": [other["id"]]})["plot"] is None
    with pytest.raises(UiHttpError):
        handler.job_results(state, {"id": ["0" * 12]})


def test_skbio_crosscheck_with_a_stand_in_module(monkeypatch):
    import types

    from flora.ui.handlers import analysis
    from flora.ui.http import UiHttpError

    monkeypatch.setitem(sys.modules, "skbio", None)  # not installed -> clear, actionable error
    with pytest.raises(UiHttpError) as err:
        analysis._skbio_permanova(np.zeros((2, 2)), ["a", "b"], ["x", "y"], 99)
    assert err.value.code == "engine_unavailable"

    skbio = types.ModuleType("skbio")
    skbio.DistanceMatrix = lambda d, ids: (d, ids)
    stats_mod = types.ModuleType("skbio.stats")
    dist_mod = types.ModuleType("skbio.stats.distance")
    dist_mod.permanova = lambda dm, grouping, permutations: {"test statistic": 4.2, "p-value": 0.01}
    monkeypatch.setitem(sys.modules, "skbio", skbio)
    monkeypatch.setitem(sys.modules, "skbio.stats", stats_mod)
    monkeypatch.setitem(sys.modules, "skbio.stats.distance", dist_mod)
    assert analysis._skbio_permanova(np.zeros((2, 2)), ["a", "b"], ["x", "y"], 99) == {"backend": "scikit-bio", "f": 4.2, "p": 0.01}
