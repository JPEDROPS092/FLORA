"""Workspace read-models and persisted ML/download records behind the SPA contract."""

from __future__ import annotations

import pytest

from flora.ui.handlers import downloads, ml, report, workspace
from flora.ui.http import UiHttpError
from flora.ui.server import create_app


@pytest.fixture()
def state(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    out = downloads.download_synthetic(st, {"output_dir": str(tmp_path / "raw"), "samples": 40, "features": 60, "seed": 3})
    st.pipeline.ingest_metadata(out["metadata"])
    st.pipeline.ingest_asv_table(out["asv_table"], wide_format=True)
    st.pipeline.ingest_taxonomy(out["taxonomy"])
    st.synthetic_files = out
    return st


def test_dashboard_reports_real_counts(state):
    data = workspace.get_dashboard(state, {"min_reads": ["10"]})
    assert data["samples"] == 40 and data["asvs"] == 60
    assert data["groups"] == 4 and sorted(data["group_names"]) == ["Amazon", "Atlantic_Forest", "Cerrado", "Pantanal"]
    assert data["quality"]["pass"] == 40 and data["quality"]["mean_reads"] > 0


def test_dashboard_degrades_on_empty_workspace(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    data = workspace.get_dashboard(st, {})
    assert data["samples"] == 0 and data["quality"]["pass"] == 0


def test_pipeline_flags_low_depth_samples(state):
    data = workspace.get_pipeline(state, {"min_reads": ["1000000"], "lang": ["en"]})
    assert data["ingested"] is True
    assert data["qc"]["summary"]["low_depth"] == 40
    row = data["qc"]["rows"][0]
    assert row["status"] == "warn" and "Below 1000000 reads" in row["issues"][0]
    assert data["steps"]["ingest_asv"]["status"] == "completed"


def test_ingest_preview_detects_mismatches(state, tmp_path):
    meta = tmp_path / "meta.tsv"
    meta.write_text("sample_id\tbiome\nA\tx\nB\tx\nC\t\n")
    asv = tmp_path / "asv.tsv"
    asv.write_text("sample_id\tf1\tf2\nA\t5\t5\nB\t0\t0\nD\t3\t3\n")
    res = workspace.preview_ingest(state, {"metadata_path": str(meta), "asv_path": str(asv), "wide_format": True, "min_reads": 7})
    summary = res["summary"]
    assert {k: summary[k] for k in ("matched", "metadata_only", "asv_only", "low_depth", "total_asvs")} == {
        "matched": 2, "metadata_only": 1, "asv_only": 1, "low_depth": 1, "total_asvs": 2,
    }
    assert summary["suggested_depth"] == 1 and summary["reads_max"] == 10 and summary["reads_min"] == 0
    by_id = {r["sample_id"]: r for r in res["rows"]}
    assert by_id["A"]["status"] == "pass"
    assert by_id["B"]["status"] == "fail"  # zero reads
    assert by_id["C"]["status"] == "fail"  # absent from the ASV table
    assert by_id["D"]["status"] == "fail"  # absent from the metadata


def test_ingest_preview_missing_sample_column(state, tmp_path):
    meta = tmp_path / "meta.tsv"
    meta.write_text("id\tbiome\nA\tx\n")
    res = workspace.preview_ingest(state, {"metadata_path": str(meta), "sample_col": "sample_id"})
    assert res["rows"] == [] and res["warnings"]


def test_explore_summary_shapes(state):
    data = workspace.explore_summary(state, {"rank": ["phylum"]})
    assert data["sample_count"] == 40 and data["asv_count"] == 60
    assert {c["group"] for c in data["comparisons"]} == {"Amazon", "Atlantic_Forest", "Cerrado", "Pantanal"}
    assert data["tree"][0]["label"] == "Bacteria"
    assert all(0 <= row["q_value"] <= 1 for row in data["differential"])


def test_explore_summary_rejects_unknown_rank(state):
    with pytest.raises(UiHttpError):
        workspace.explore_summary(state, {"rank": ["; DROP"]})


def _body(**over):
    return {"model": "random_forest", "target_column": "biome", "train_filter": "sample_id < 'S030'",
            "test_filter": "sample_id >= 'S030'", "normalize": "clr", "cv_folds": 3, "seed": 5, **over}


def test_classify_persists_full_experiment(state):
    res = ml.classify(state, _body())
    exp = res["experiment"]
    assert exp["train_n"] == 30 and exp["test_n"] == 10
    assert exp["provenance"]["seed"] == 5
    assert len(exp["matrix"]) == len(exp["labels"]) == 4
    assert exp["confusion"]["status"] == "ok" and exp["importance"]["status"] == "ok"
    assert "top_features" in res  # legacy keys kept
    stored = ml.list_experiments(state)["experiments"]
    assert [e["id"] for e in stored] == [exp["id"]]


def test_classify_is_reproducible_for_same_seed(state):
    a = ml.classify(state, _body())["experiment"]
    b = ml.classify(state, _body())["experiment"]
    assert (a["accuracy"], a["matrix"]) == (b["accuracy"], b["matrix"])


@pytest.mark.parametrize("field,value", [
    ("train_filter", "1=1; DROP TABLE samples"),
    ("test_filter", "1=1 -- comment"),
    ("target_column", "biome; select 1"),
    ("model", "nope"),
])
def test_classify_rejects_unsafe_input(state, field, value):
    with pytest.raises(UiHttpError):
        ml.classify(state, _body(**{field: value}))


def test_report_draft_uses_project_data(state):
    ml.classify(state, _body())
    draft = report.report_draft(state, {"lang": ["en"]})
    assert {s["id"] for s in draft["sections"]} == {"summary", "methods", "alpha", "beta", "taxonomy", "ml", "params"}
    assert "alpha" in draft["figures"] and "confusion" in draft["figures"]
    assert "40 samples" in draft["sections"][0]["narrative"]


def test_generate_report_writes_inside_workspace(state):
    res = report.generate_report(state, {"title": "t", "output_path": "results/report.html"})
    assert str(state.data_dir) in res["report_path"]
    assert report.preview_report(state, {"path": [res["report_path"]]})
    with pytest.raises(UiHttpError):
        report.preview_report(state, {"path": ["/etc/hostname.html"]})


def test_download_jobs_are_recorded(state, tmp_path):
    run = downloads.recorded("synthetic", downloads.download_synthetic)
    out = run(state, {"output_dir": str(tmp_path / "d1"), "samples": 8, "features": 5})
    assert out["job"]["status"] == "completed" and out["job"]["artifacts"]

    def boom(_state, _body):
        raise UiHttpError("nope")

    with pytest.raises(UiHttpError):
        downloads.recorded("emp", boom)(state, {"output_dir": "x"})
    jobs = downloads.list_downloads(state)["jobs"]
    assert sorted(j["status"] for j in jobs) == ["completed", "failed"]
