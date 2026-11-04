"""Fixes for real MGnify studies: grouping columns live in sample_metadata, not samples.biome."""

from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from flora.ui.handlers import downloads, explore, ingest, ml, projects, report, viz, workspace
from flora.ui.handlers import analysis
from flora.ui.server import GET_ROUTES, create_app


def _seed(state):
    """Eight samples shaped like a MGnify amplicon study: empty biome, land_cover in metadata, one tiny library."""
    db = state.db
    db.execute(
        "INSERT INTO samples (sample_id, biome, location, latitude, longitude) VALUES "
        "('S1', NULL, 'Brazil', -13.38, -54.94), ('S2', '', 'Brazil', -13.39, -54.93),"
        "('S3', NULL, 'Brazil', -13.40, -54.92), ('S4', NULL, 'Brazil', -13.41, -54.91),"
        "('S5', NULL, 'Brazil', -13.42, -54.90), ('S6', NULL, 'Brazil', -13.43, -54.89),"
        "('S7', NULL, 'Brazil', -13.44, -54.88), ('S8', NULL, 'Brazil', -13.45, -54.87)"
    )
    pairs = ",".join(f"('{sid}','land_cover','{cover}')" for sid, cover in (
        ("S1", "forest"), ("S2", "forest"), ("S3", "forest"), ("S4", "forest"),
        ("S5", "pasture"), ("S6", "pasture"), ("S7", "pasture"), ("S8", "pasture"),
    ))
    db.execute(f"INSERT INTO sample_metadata VALUES {pairs}")
    db.execute(
        "INSERT INTO asv VALUES "
        "('S1','f1',2000),('S1','f2',10),('S2','f1',1900),('S2','f2',12),"
        "('S3','f1',2100),('S3','f2',8),('S4','f1',1800),('S4','f2',15),"
        "('S5','f1',12),('S5','f2',2000),('S6','f1',9),('S6','f2',1900),"
        "('S7','f1',11),('S7','f2',2100),('S8','f1',1),('S8','f2',2)"
    )
    db.execute(
        "INSERT INTO taxonomy (feature_id, kingdom, phylum, genus) VALUES "
        "('f1','Bacteria','Proteobacteria','Rhodoplanes'),('f2','Bacteria','Acidobacteria','')"
    )


@pytest.fixture()
def state(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    project = st.projects.create("Amazônia")
    st.projects.set_active(project.id)
    _seed(st)
    return st


def test_group_columns_come_from_metadata_when_biome_is_empty(state):
    assert explore.default_group(state.db) == "land_cover"
    dash = workspace.get_dashboard(state, {})
    assert dash["group_by"] == "land_cover"
    assert dash["groups"] == 2
    assert sorted(dash["group_names"]) == ["forest", "pasture"]
    assert dash["quality"]["pass"] == 7
    assert dash["quality"]["warn"] == 1
    assert dash["quality"]["pass"] + dash["quality"]["warn"] + dash["quality"]["fail"] == 8


def test_qc_flags_a_three_read_library(state):
    qc = analysis.get_qc(state, {})
    by_id = {row["sample_id"]: row for row in qc["samples"]}
    assert by_id["S8"]["reads"] == 3
    assert by_id["S8"]["status"] != "pass"
    assert qc["summary"]["min_reads"] > 3
    assert by_id["S1"]["status"] == "pass"


def test_alpha_and_classification_accept_a_metadata_column(state):
    alpha = viz.viz_alpha(state, {"metric": ["shannon"], "group_by": ["land_cover"]})
    assert alpha["success"] is True and alpha["plot"]["data"]

    auto = ml.classify(state, {"model": "random_forest", "target_column": "land_cover", "split": "auto", "test_size": 0.5, "cv_folds": 2, "seed": 1, "normalize": "clr"})
    assert auto["success"] and auto["experiment"]["status"] == "completed"

    sql = ml.classify(state, {
        "model": "random_forest", "target_column": "land_cover", "split": "sql",
        "train_filter": "(land_cover = 'forest' OR land_cover = 'pasture') AND sample_id IN ('S1','S2','S5','S6')",
        "test_filter": "(land_cover = 'forest' OR land_cover = 'pasture') AND sample_id IN ('S3','S4','S7','S8')",
        "cv_folds": 2, "seed": 1, "normalize": "clr",
    })
    assert sql["success"] and sql["experiment"]["train_n"] == 4 and sql["experiment"]["test_n"] == 4


def test_kmeans_returns_the_requested_k(state):
    out = ml.cluster(state, {"method": "kmeans", "n_clusters": 2, "normalize": "clr", "seed": 1})
    assert out["success"] and out["requested_k"] == 2 and out["n_clusters"] == 2
    assert len({row["cluster"] for row in out["labels"]}) == 2


def test_explore_map_is_registered_and_returns_points(state, tmp_path):
    assert GET_ROUTES["/api/explore/map"] is explore.get_map
    mapped = explore.get_map(state, {"group_by": ["land_cover"]})
    assert mapped["map"]["available"] is True
    assert mapped["map"]["mapped"] == 8
    assert mapped["map"]["group_column"] == "land_cover"

    server_cls, handler_cls, _ = create_app(workdir=tmp_path / "http")
    # The handler closes over its own state; hit the route on a fresh app that shares nothing,
    # then again through the seeded state's server by rebuilding is unnecessary: dispatch the live handler.
    httpd = server_cls(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/explore/map"
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode())
        assert response.status == 200 and payload["success"] is True and "map" in payload
        assert "Endpoint desconhecido" not in json.dumps(payload)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_stage_advances_and_replace_clears_the_pipeline_log(state, tmp_path):
    ingest.compute_diversity(state, {})
    assert state.projects.get(state.projects.active_id()).stage == "analyzed"
    report.generate_report(state, {"title": "Relatório", "group_by": "land_cover"})
    assert state.projects.get(state.projects.active_id()).stage == "reported"

    state.db.execute("INSERT INTO pipeline_log (run_id, step, status, started_at, message) VALUES ('old', 'compute_diversity', 'completed', now(), 'antigo')")
    meta = tmp_path / "metadata.tsv"
    asv = tmp_path / "asv_table.tsv"
    tax = tmp_path / "taxonomy.tsv"
    meta.write_text("sample_id\tland_cover\nA\tforest\nB\tpasture\n", encoding="utf-8")
    asv.write_text("sample_id\tf1\tf2\nA\t10\t1\nB\t1\t12\n", encoding="utf-8")
    tax.write_text("feature_id\tkingdom\tphylum\nf1\tBacteria\tProteobacteria\nf2\tBacteria\tFirmicutes\n", encoding="utf-8")
    ingest.ingest_dataset(state, {"metadata_path": str(meta), "asv_path": str(asv), "taxonomy_path": str(tax), "replace": True})
    steps = [row[0] for row in state.db.query("SELECT step FROM pipeline_log").to_polars().iter_rows()]
    assert "compute_diversity" not in steps
    assert state.projects.get(state.projects.active_id()).stage == "ingested"


def test_delete_project_requires_confirmation_then_removes_it(state):
    pid = state.projects.active_id()
    pending = projects.delete_project(state, {"id": pid})
    assert pending["applied"] is False and state.projects.get(pid).name == "Amazônia"
    done = projects.delete_project(state, {"id": pid, "confirm": True})
    assert done["applied"] is True and state.projects.active_id() == ""
    with pytest.raises(Exception):
        state.projects.get(pid)


def test_catalog_download_ingests_via_replace(state, tmp_path, monkeypatch):
    from flora.io import sources

    meta = tmp_path / "metadata.tsv"
    asv = tmp_path / "asv.tsv"
    tax = tmp_path / "tax.tsv"
    meta.write_text("sample_id\tland_cover\tlatitude\tlongitude\nS1\tforest\t-13.3\t-54.9\nS2\tpasture\t-13.4\t-54.8\n", encoding="utf-8")
    asv.write_text("sample_id\tMGN_00001\tMGN_00002\nS1\t8\t1\nS2\t1\t9\n", encoding="utf-8")
    tax.write_text("feature_id\tkingdom\tphylum\tgenus\nMGN_00001\tBacteria\tProteobacteria\tRhizobium\nMGN_00002\tBacteria\tFirmicutes\t\n", encoding="utf-8")

    def fake(self, accession, output_dir, **opts):
        return {"metadata": str(meta), "asv_table": str(asv), "taxonomy": str(tax)}

    monkeypatch.setattr(sources.MGnifySource, "download", fake)
    out = downloads.library_download(state, {"source": "mgnify", "accession": "MGYS00001352"})
    assert out["ingested"]["project_stage"] == "ingested"
    assert state.db.query("SELECT COUNT(*) FROM samples").to_polars().row(0)[0] == 2
    assert explore.default_group(state.db) == "land_cover"
