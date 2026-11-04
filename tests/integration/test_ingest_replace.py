"""Re-ingesting or switching dataset replaces the data atomically instead of failing on duplicate keys."""

from __future__ import annotations

import pytest

from flora.ui.handlers import downloads, ingest
from flora.ui.http import UiHttpError
from flora.ui.server import create_app


@pytest.fixture()
def env(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    a = downloads.download_synthetic(st, {"output_dir": str(tmp_path / "a"), "samples": 12, "features": 20, "seed": 1})
    b = downloads.download_synthetic(st, {"output_dir": str(tmp_path / "b"), "samples": 7, "features": 15, "seed": 2})
    return st, a, b


def body(files, **extra):
    return {"metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"], "wide_format": True, **extra}


def counts(st):
    q = lambda t: int(st.db.query(f"SELECT COUNT(*) FROM {t}").to_polars().row(0)[0])  # noqa: E731
    return q("samples"), q("asv"), q("taxonomy")


def test_ingesting_the_same_dataset_twice_works_and_does_not_duplicate(env):
    st, a, _ = env
    first = ingest.ingest_dataset(st, body(a))
    assert [s["step"] for s in first["steps"]] == ["metadata", "asv", "taxonomy"] and all(s["success"] for s in first["steps"])
    again = ingest.ingest_dataset(st, body(a))
    assert again["replaced"] == {"samples": 12}
    assert counts(st)[0] == 12 and counts(st)[2] == 20


def test_a_different_dataset_replaces_the_previous_one(env):
    st, a, b = env
    ingest.ingest_dataset(st, body(a))
    ingest.ingest_dataset(st, body(b))
    samples, _asv, taxa = counts(st)
    assert (samples, taxa) == (7, 15)
    assert st.db.query("SELECT COUNT(*) FROM samples WHERE sample_id = 'S011'").to_polars().row(0)[0] == 0  # only in the 12-sample set


def test_a_failure_rolls_everything_back_and_keeps_the_old_data(env, tmp_path):
    st, a, b = env
    ingest.ingest_dataset(st, body(a))
    broken = {**body(b), "taxonomy_path": str(tmp_path / "does-not-exist.tsv")}
    with pytest.raises(UiHttpError) as err:
        ingest.ingest_dataset(st, broken)
    assert err.value.details == {"step": "taxonomy"} and "dados anteriores foram mantidos" in err.value.message
    assert counts(st)[0] == 12 and counts(st)[2] == 20  # the previous dataset is intact


def test_append_mode_and_single_steps_explain_duplicates(env):
    st, a, _ = env
    ingest.ingest_dataset(st, body(a))
    with pytest.raises(UiHttpError) as err:
        ingest.ingest_dataset(st, body(a, replace=False))
    assert err.value.status == 409 and err.value.code == "already_ingested" and "substitui" in err.value.message
    with pytest.raises(UiHttpError) as err:
        ingest.ingest_metadata(st, {"path": a["metadata"]})
    assert err.value.code == "already_ingested" and "chave repetida" in err.value.message
    assert counts(st)[0] == 12


def test_missing_paths_are_reported(env):
    with pytest.raises(UiHttpError) as err:
        ingest.ingest_dataset(env[0], {"metadata_path": "x"})
    assert err.value.code == "missing_path" and "asv_path" in err.value.message


def test_confirming_updates_the_active_project_record(env):
    st, a, b = env
    project = st.projects.create("Teste")
    st.projects.set_active(project.id)
    assert st.projects.get(project.id).stage == "empty"
    out = ingest.ingest_dataset(st, body(a))
    assert out["project_stage"] == "ingested"
    rec = st.projects.get(project.id)
    assert (rec.stage, rec.samples, rec.asvs) == ("ingested", 12, 20)
    assert rec.analyses[-1]["step"] == "ingest"
    ingest.ingest_dataset(st, body(b))  # replacing keeps the record in sync
    assert st.projects.get(project.id).samples == 7


def test_ml_can_target_a_metadata_key_not_stored_in_the_samples_table(env):
    st, a, _ = env
    ingest.ingest_dataset(st, body(a))
    # move the label into the key-value metadata, as real MGnify studies do (land_cover, environment_biome…)
    st.db.execute("INSERT INTO sample_metadata SELECT sample_id, 'land_cover', CASE WHEN biome IN ('Amazon','Cerrado') THEN 'forest' ELSE 'pasture' END FROM samples")
    from flora.ui.handlers import ml

    out = ml.classify(st, {"model": "random_forest", "target_column": "land_cover", "split": "auto", "cv_folds": 2, "seed": 1, "normalize": "clr"})
    assert out["success"] and out["experiment"]["status"] == "completed" and out["experiment"]["train_n"] + out["experiment"]["test_n"] == 12
