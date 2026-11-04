"""Correctness fixes for ingestion, rarefaction depth, QC and the HTML report."""

from __future__ import annotations

import pytest

from flora.db.connection import FloraDB
from flora.db.ingestion import ingest_metadata, ingest_tsv_asv
from flora.db.schema import initialize_schema
from flora.ui.handlers import analysis, downloads, ingest, projects, report
from flora.ui.http import UiHttpError
from flora.ui.server import create_app


def _db():
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    return db


def _write(path, text: str):
    path.write_text(text, encoding="utf-8")
    return path


def test_wide_and_long_tables_are_detected_without_a_flag(tmp_path):
    db = _db()
    meta = _write(tmp_path / "metadata.tsv", "sample_id\tbiome\nS1\tA\nS2\tB\n")
    wide = _write(tmp_path / "wide.tsv", "sample_id\tASV_1\tASV_2\nS1\t4\t1\nS2\t0\t6\n")
    long = _write(tmp_path / "long.tsv", "sample_id\tfeature_id\tabundance\nS1\tASV_9\t3\nS2\tASV_9\t2\n")
    qiime = _write(tmp_path / "qiime.tsv", "feature-id\tS1\tS2\nASV_3\t5\t0\nASV_4\t1\t7\n")
    ingest_metadata(db, meta)
    assert ingest_tsv_asv(db, wide) == 3  # the zero is dropped
    db.execute("DELETE FROM asv")
    assert ingest_tsv_asv(db, wide, wide_format=False) == 3  # explicit long is corrected
    db.execute("DELETE FROM asv")
    assert ingest_tsv_asv(db, long, wide_format=True) == 2  # explicit wide is corrected
    db.execute("DELETE FROM asv")
    assert ingest_tsv_asv(db, qiime) == 3


def test_lat_lon_is_filled_and_empty_schema_columns_are_not_present(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    paired = _write(tmp_path / "paired.tsv", "sample_id\tbiome\tlat_lon\nS1\tA\t10.5 S 30.2 W\nS2\tB\t1.5 -2.5\n")
    state.pipeline.ingest_metadata(paired)
    mixs = {row["field"]: row for row in analysis.get_mixs(state)["fields"]}
    assert mixs["lat_lon"]["present"] is True and mixs["lat_lon"]["filled_pct"] == 100.0
    state.pipeline.clear_dataset()
    bare = _write(tmp_path / "bare.tsv", "sample_id\tbiome\nS1\tA\n")
    state.pipeline.ingest_metadata(bare)
    mixs = {row["field"]: row for row in analysis.get_mixs(state)["fields"]}
    assert mixs["lat_lon"]["present"] is False and mixs["lat_lon"]["filled_pct"] == 0.0


def test_diversity_defaults_to_the_shallowest_sample_and_reports_drops(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    files = downloads.download_synthetic(state, {"output_dir": str(tmp_path / "raw"), "samples": 12, "features": 8, "seed": 4})
    ingest.ingest_dataset(state, {
        "metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"],
    })
    out = ingest.compute_diversity(state, {})
    assert out["depth_source"] == "adaptive_min"
    assert out["sampling_depth"] == out["reads"]["min"]
    assert out["dropped_count"] == 0 and out["retained"] == 12 and out["samples"] == 12
    with pytest.raises(UiHttpError) as err:
        ingest.compute_diversity(state, {"sampling_depth": 10000})
    assert err.value.code == "depth_too_high" and "10000" in err.value.message and str(out["reads"]["max"]) in err.value.message


def test_qc_without_an_asv_table_is_an_error(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    meta = _write(tmp_path / "metadata.tsv", "sample_id\tbiome\nS1\tA\nS2\tB\n")
    state.pipeline.ingest_metadata(meta)
    with pytest.raises(UiHttpError) as err:
        analysis.get_qc(state, {})
    assert err.value.code == "missing_asv_table" and "0 reads" in err.value.message


def test_saved_reads_threshold_is_shared_by_qc(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    files = downloads.download_synthetic(state, {"output_dir": str(tmp_path / "raw"), "samples": 8, "features": 5, "seed": 5})
    ingest.ingest_dataset(state, {"metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"]})
    analysis.save_settings(state, {"min_reads": 10**9})
    qc = analysis.get_qc(state, {})
    assert qc["summary"]["min_reads"] == 10**9 and qc["summary"]["below_depth"] == 8
    explicit = analysis.get_qc(state, {"min_reads": ["3"]})
    assert explicit["summary"]["min_reads"] == 3


def test_ingest_updates_stage_and_a_failed_asv_keeps_the_previous_dataset(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    project = projects.create_project(state, {"name": "Estudo"})["project"]
    projects.activate_project(state, {"id": project["id"]})
    first = downloads.download_synthetic(state, {"output_dir": str(tmp_path / "a"), "samples": 6, "features": 4, "seed": 1})
    second = downloads.download_synthetic(state, {"output_dir": str(tmp_path / "b"), "samples": 4, "features": 4, "seed": 2})
    done = ingest.ingest_dataset(state, {"metadata_path": first["metadata"], "asv_path": first["asv_table"], "taxonomy_path": first["taxonomy"]})
    assert done["project_stage"] == "ingested"
    assert projects.get_project(state, {"id": [project["id"]]})["project"]["stage"] == "ingested"
    missing = tmp_path / "missing.tsv"
    with pytest.raises(UiHttpError) as err:
        ingest.ingest_dataset(state, {"metadata_path": second["metadata"], "asv_path": str(missing), "taxonomy_path": second["taxonomy"]})
    assert err.value.details == {"step": "asv"} and "anteriores foram mantidos" in err.value.message
    assert state.db.query("SELECT COUNT(*) FROM samples").to_polars().row(0)[0] == 6
    assert projects.get_project(state, {"id": [project["id"]]})["project"]["stage"] == "ingested"


def test_report_sections_and_plotly_loaded_once(tmp_path):
    _, _, state = create_app(workdir=tmp_path)
    files = downloads.download_synthetic(state, {"output_dir": str(tmp_path / "raw"), "samples": 16, "features": 12, "seed": 6})
    ingest.ingest_dataset(state, {"metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"]})
    analysis.save_settings(state, {"taxonomy_db": "SILVA 138"})
    saved = report.generate_report(state, {"title": "Relatório sintético", "group_by": "biome", "output_path": str(tmp_path / "report.html")})
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    for title in (
        "Controle de qualidade",
        "Curvas de rarefação",
        "Kruskal-Wallis",
        "PERMANOVA",
        "PERMDISP",
        "Volcano",
        "Abundância diferencial",
        "SILVA 138",
        "Versões dos pacotes",
        "Parâmetros",
    ):
        assert title in html, title
    assert "cdn.plot.ly/plotly-" in html
    assert html.count("cdn.plot.ly/plotly-") == 1
    assert "Plotly.newPlot" in html
    assert len(html) < 1_500_000  # the embedded library alone is about 5 MB
    assert saved["sections"] >= 8
