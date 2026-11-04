"""Connecting FLORA to QIIME 2 / DADA2 living in another environment, including the Python API bridge."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from flora.engines import envs, registry
from flora.engines.jobs import EngineError, JobManager
from flora.ui.handlers import engines as handler
from flora.ui.http import UiHttpError


def _exe(path: Path, body: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture(autouse=True)
def clean_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # discovery also looks in ./.engines, which exists in the real repository
    registry.configure({})
    yield
    registry.configure({})


def _conda_env(root: Path, name: str, qiime=True, q2_api=True, dada2=True, rscript=True) -> Path:
    prefix = root / "envs" / name
    for tool, flag in (("qiime", qiime), ("python", True), ("Rscript", rscript)):
        if flag:
            _exe(prefix / "bin" / tool)
    if q2_api:
        (prefix / "lib" / "python3.10" / "site-packages" / "qiime2").mkdir(parents=True)
    if dada2:
        (prefix / "lib" / "R" / "library" / "dada2").mkdir(parents=True)
    return prefix


def test_discover_finds_only_environments_with_qiime2_or_dada2(tmp_path, monkeypatch):
    for var in ("CONDA_PREFIX", "CONDA_EXE", "MAMBA_ROOT_PREFIX"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "miniconda3"
    _conda_env(root, "qiime2-amplicon")
    _conda_env(root, "only-r", qiime=False, q2_api=False)
    (root / "envs" / "empty" / "bin").mkdir(parents=True)
    found = {e["name"]: e for e in envs.discover(tmp_path)}
    assert set(found) == {"qiime2-amplicon", "only-r"}
    q = found["qiime2-amplicon"]
    assert q["qiime"].endswith("bin/qiime") and q["python"].endswith("bin/python") and q["qiime2_python_api"] and q["dada2_r_package"]
    assert found["only-r"]["qiime"] is None and found["only-r"]["python"] is None and found["only-r"]["dada2_r_package"]


def test_config_is_validated_saved_and_reloaded(tmp_path):
    good = _exe(tmp_path / "e" / "qiime")
    saved = envs.save(tmp_path, {"qiime": str(good), "junk": "/etc/passwd", "rscript": ""})
    assert saved == {"qiime": str(good)} and envs.load(tmp_path) == {"qiime": str(good)}
    for bad in ({"qiime": "qiime"}, {"qiime": str(tmp_path / "missing")}, {"python": str(tmp_path)}):
        with pytest.raises(envs.EnvError):
            envs.save(tmp_path, bad)
    plain = tmp_path / "plain.txt"
    plain.write_text("x")
    with pytest.raises(envs.EnvError):
        envs.save(tmp_path, {"qiime": str(plain)})  # exists but is not executable
    good.unlink()
    assert envs.load(tmp_path) == {}  # a vanished executable is dropped, not trusted


def test_registry_uses_a_configured_qiime_that_is_not_on_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    registry.configure({})
    assert not any(e["available"] for e in registry.detect_all(fresh=True) if e["id"] == "qiime2")
    q = _exe(tmp_path / "env" / "bin" / "qiime", f"#!{sys.executable}\nimport sys\nprint('q2cli 2042.1') if sys.argv[1:] == ['--version'] else None\n")
    registry.configure({"qiime": str(q)})
    by = {e["id"]: e for e in registry.detect_all(fresh=True)}
    assert by["qiime2"]["available"] and "2042.1" in by["qiime2"]["version"]
    assert registry.resolve_cmd(["qiime", "tools", "import"]) == [str(q), "tools", "import"]
    assert registry.resolve_cmd(["vsearch", "-v"]) == ["vsearch", "-v"]
    registry.configure({})
    assert registry.resolve_cmd(["qiime"]) == ["qiime"]


FAKE_Q2 = {
    "qiime2/__init__.py": '''
        import json, os
        from pathlib import Path
        __version__ = "9.9"
        LOG = os.environ.get("FAKE_Q2_LOG")

        def record(*item):
            if LOG:
                with open(LOG, "a") as fh:
                    fh.write(json.dumps(item, default=str) + "\\n")

        class Artifact:
            def __init__(self, kind, source=None):
                self.kind, self.source = kind, source

            @classmethod
            def import_data(cls, type, source, view_type=None):
                record("import", type, view_type, source)
                return cls("demux", source)

            @classmethod
            def load(cls, path):
                return cls("classifier", path)

            def export_data(self, out):
                out = Path(out); out.mkdir(parents=True, exist_ok=True)
                if self.kind == "table":
                    import numpy as np
                    from biom import Table
                    from biom.util import biom_open
                    t = Table(np.array([[5, 0], [1, 7]]), ["ASV1", "ASV2"], ["S1", "S2"])
                    with biom_open(str(out / "feature-table.biom"), "w") as fh:
                        t.to_hdf5(fh, "fake")
                elif self.kind == "taxonomy":
                    (out / "taxonomy.tsv").write_text("Feature ID\\tTaxon\\tConfidence\\nASV1\\td__Bacteria; p__Firmicutes; g__Bacillus\\t0.9\\nASV2\\td__Bacteria; p__Proteobacteria\\t0.8\\n")
                elif self.kind == "tree":
                    (out / "tree.nwk").write_text("(ASV1:0.1,ASV2:0.2);")
                else:
                    (out / f"{self.kind}.txt").write_text("x")
    ''',
    "qiime2/plugins/__init__.py": "",
    "qiime2/plugins/dada2.py": '''
        from types import SimpleNamespace
        from qiime2 import Artifact, record

        def _result(**kw):
            record("dada2", kw)
            return SimpleNamespace(table=Artifact("table"), representative_sequences=Artifact("seqs"), denoising_stats=Artifact("stats"))

        def denoise_paired(demultiplexed_seqs, trunc_len_f, trunc_len_r, trim_left_f=0, trim_left_r=0, n_threads=1):
            return _result(paired=True, trunc_len_f=trunc_len_f, trunc_len_r=trunc_len_r, trim_left_f=trim_left_f, trim_left_r=trim_left_r, n_threads=n_threads)

        def denoise_single(demultiplexed_seqs, trunc_len, trim_left=0, n_threads=1):
            return _result(paired=False, trunc_len=trunc_len, trim_left=trim_left, n_threads=n_threads)

        methods = SimpleNamespace(denoise_paired=denoise_paired, denoise_single=denoise_single)  # same signatures as q2-dada2
    ''',
    "qiime2/plugins/feature_classifier.py": '''
        from types import SimpleNamespace
        from qiime2 import Artifact
        methods = SimpleNamespace(classify_sklearn=lambda reads, classifier: SimpleNamespace(classification=Artifact("taxonomy")))
    ''',
    "qiime2/plugins/phylogeny.py": '''
        from types import SimpleNamespace
        from qiime2 import Artifact
        pipelines = SimpleNamespace(align_to_tree_mafft_fasttree=lambda sequences: SimpleNamespace(rooted_tree=Artifact("tree")))
    ''',
}


@pytest.fixture()
def fake_qiime2(tmp_path, monkeypatch):
    root = tmp_path / "fakeq2"
    for rel, body in FAKE_Q2.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(textwrap.dedent(body))
    log = tmp_path / "q2calls.jsonl"
    monkeypatch.setenv("PYTHONPATH", f"{root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")
    monkeypatch.setenv("FAKE_Q2_LOG", str(log))
    monkeypatch.setenv("PATH", "/nonexistent")  # no qiime CLI at all: only the Python API is reachable
    registry.configure({})
    yield log
    registry.configure({})


def _wait(mgr, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = mgr.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_qiime2_is_detected_through_the_python_api_when_there_is_no_cli(fake_qiime2):
    registry.configure({"python": sys.executable})
    by = {e["id"]: e for e in registry.detect_all(fresh=True)}
    assert by["qiime2"]["available"] and "API Python" in by["qiime2"]["version"] and "9.9" in by["qiime2"]["version"]
    assert registry.qiime_python() == sys.executable


def test_python_backend_runs_dada2_via_the_api_and_converts_the_export(fake_qiime2, tmp_path):
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("sample-id\tforward-absolute-filepath\n")
    classifier = tmp_path / "clf.qza"
    classifier.write_text("x")
    registry.configure({"python": sys.executable})
    mgr = JobManager(tmp_path / "engines")
    job = mgr.start("qiime2-dada2", {"backend": "python", "manifest": str(manifest), "paired": True, "classifier": str(classifier),
                                     "build_tree": True, "trunc_len_f": 230, "trunc_len_r": 180, "trim_left_f": 17, "threads": 3})
    assert job["steps"] == ["qiime2 (API Python)"]
    done = _wait(mgr, job["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-6:]
    calls = [json.loads(line) for line in fake_qiime2.read_text().splitlines()]
    assert calls[0][:3] == ["import", "SampleData[PairedEndSequencesWithQuality]", "PairedEndFastqManifestPhred33V2"]
    dada = next(c for c in calls if c[0] == "dada2")[1]
    assert dada["paired"] is True and (dada["trunc_len_f"], dada["trunc_len_r"], dada["trim_left_f"], dada["n_threads"]) == (230, 180, 17, 3)
    asv = pl.read_csv(done["artifacts"]["asv_table"], separator="\t")
    assert asv["sample_id"].to_list() == ["S1", "S2"] and asv.filter(pl.col("sample_id") == "S2")["ASV2"].item() == 7
    tax = pl.read_csv(done["artifacts"]["taxonomy"], separator="\t")
    assert tax.filter(pl.col("feature_id") == "ASV1")["genus"].item() == "Bacillus"
    assert Path(done["artifacts"]["tree"]).read_text() == "(ASV1:0.1,ASV2:0.2);"
    assert any("API Python" not in line and "DADA2" in line for line in done["log"])


def test_python_backend_single_end_and_no_optional_steps(fake_qiime2, tmp_path):
    manifest = tmp_path / "m.tsv"
    manifest.write_text("x")
    registry.configure({"python": sys.executable})
    mgr = JobManager(tmp_path / "engines")
    done = _wait(mgr, mgr.start("qiime2-dada2", {"backend": "python", "manifest": str(manifest), "paired": False})["id"])
    assert done["status"] == "completed", done["error"] or done["log"][-6:]
    calls = [json.loads(line) for line in fake_qiime2.read_text().splitlines()]
    single = next(c for c in calls if c[0] == "dada2")[1]
    assert calls[0][1] == "SampleData[SequencesWithQuality]" and single["paired"] is False and "trunc_len" in single and "trunc_len_f" not in single
    assert "taxonomy" not in done["artifacts"] and "tree" not in done["artifacts"]


def test_python_backend_without_any_qiime2_python_is_refused_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    registry.configure({"python": _exe(tmp_path / "py" / "python", "#!/bin/sh\nexit 1\n").as_posix()})
    manifest = tmp_path / "m.tsv"
    manifest.write_text("x")
    with pytest.raises(EngineError) as err:
        JobManager(tmp_path / "engines").start("qiime2-dada2", {"backend": "python", "manifest": str(manifest)})
    assert err.value.code == "engine_unavailable" and "Ambientes" in str(err.value)


def test_cli_job_uses_the_configured_qiime_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    q = _exe(tmp_path / "env" / "bin" / "qiime", f"""#!{sys.executable}
import sys
from pathlib import Path
a = sys.argv[1:]
if a == ["--version"]:
    print("q2cli 1.0"); sys.exit(0)
for i, t in enumerate(a):
    if t.startswith("--o-") or t == "--output-path":
        Path(a[i + 1]).parent.mkdir(parents=True, exist_ok=True); Path(a[i + 1]).write_text("x")
print("ran", " ".join(a[:2]))
""")
    registry.configure({"qiime": str(q)})
    manifest = tmp_path / "m.tsv"
    manifest.write_text("x")
    mgr = JobManager(tmp_path / "engines")
    job = _wait(mgr, mgr.start("qiime2-dada2", {"manifest": str(manifest), "paired": False})["id"])
    # the fake CLI cannot export a BIOM, so conversion fails -- but only after the *configured* binary ran every step
    assert any(line.startswith(f"$ {q} tools import") for line in job["log"]), job["log"][:3]
    assert any(line == "ran tools import" for line in job["log"]) and "feature-table.biom" in job["error"]


def test_environment_endpoints(tmp_path, monkeypatch):
    for var in ("CONDA_PREFIX", "CONDA_EXE", "MAMBA_ROOT_PREFIX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", "/nonexistent")
    state = SimpleNamespace(workdir=tmp_path / "wd", data_dir=tmp_path / "wd")
    prefix = _conda_env(tmp_path / "home" / "miniconda3", "qiime2")
    out = handler.get_environments(state)
    assert [e["name"] for e in out["environments"]] == ["qiime2"] and out["config"] == {}

    q = _exe(prefix / "bin" / "qiime", f"#!{sys.executable}\nprint('q2cli 7.7')\n")
    saved = handler.save_environment(state, {"qiime": str(q), "rscript": str(prefix / "bin" / "Rscript")})
    assert saved["config"]["qiime"] == str(q)
    assert {e["id"]: e["available"] for e in saved["engines"]}["qiime2"] is True
    assert handler.get_environments(state)["effective"]["qiime"] == str(q)
    assert envs.load(tmp_path / "wd")["qiime"] == str(q)  # survives a restart

    with pytest.raises(UiHttpError) as err:
        handler.save_environment(state, {"python": "relative/python"})
    assert err.value.code == "invalid_environment"
