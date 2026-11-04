"""Analysis endpoints against a real in-memory DuckDB with a known group effect."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from flora.db.connection import FloraDB
from flora.db.schema import initialize_schema
from flora.ui.handlers import analysis
from flora.ui.http import UiHttpError


@pytest.fixture()
def state():
    rng = np.random.default_rng(7)
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    samples = [f"S{i:02d}" for i in range(16)]
    biome = ["Amazon"] * 8 + ["Cerrado"] * 8
    db.load_dataframe("samples", pl.DataFrame({
        "sample_id": samples, "biome": biome, "location": ["BR"] * 16, "latitude": [None] * 16, "longitude": [None] * 16, "sequencing_depth": [None] * 16,
    }, schema_overrides={"latitude": pl.Float64, "longitude": pl.Float64, "sequencing_depth": pl.Int64}))
    feats = [f"F{j}" for j in range(8)]
    rows = []
    for s, b in zip(samples, biome, strict=True):
        for j, f in enumerate(feats):
            base = 60 if (b == "Amazon") == (j < 4) else 8  # group-specific taxa
            rows.append((s, f, float(rng.poisson(base))))
    rows.append(("S00", "F8", 40.0))  # chloroplast read in one sample
    db.load_dataframe("asv", pl.DataFrame(rows, schema=["sample_id", "feature_id", "abundance"], orient="row"))
    tax = [(f, "Bacteria", "Proteobacteria" if j < 4 else "Firmicutes", "c", "o", "f", f"Gen{j}", None, None) for j, f in enumerate(feats)]
    tax.append(("F8", "Bacteria", "Cyanobacteria", "Chloroplast", "Chloroplast", "f", "g", None, None))
    db.load_dataframe("taxonomy", pl.DataFrame(tax, schema=["feature_id", "kingdom", "phylum", "class", "order", "family", "genus", "species", "confidence"], orient="row",
                                               schema_overrides={"species": pl.Utf8, "confidence": pl.Float64}))
    import tempfile
    from pathlib import Path

    return SimpleNamespace(db=db, projects=SimpleNamespace(active_id=lambda: None), data_dir=Path(tempfile.mkdtemp()))


def P(**kw):
    return {k: [str(v)] for k, v in kw.items()}


def test_qc_flags_organelles_and_depth(state):
    out = analysis.get_qc(state, P(min_reads=400))
    assert out["summary"]["organelle_features"] == 1 and out["summary"]["samples"] == 16
    s00 = next(r for r in out["samples"] if r["sample_id"] == "S00")
    assert s00["organelle_pct"] > 0
    assert out["plot"]["data"]


def test_apply_qc_is_dry_run_until_confirmed(state):
    plan = analysis.apply_qc(state, {"remove_organelles": True})
    assert plan["applied"] is False and plan["plan"]["features_removed"] == 1
    assert state.db.query("SELECT COUNT(*) FROM asv WHERE feature_id='F8'").to_polars().row(0)[0] == 1
    done = analysis.apply_qc(state, {"remove_organelles": True, "confirm": True})
    assert done["applied"] and done["plan"]["reads_removed"] == 40
    assert state.db.query("SELECT COUNT(*) FROM asv WHERE feature_id='F8'").to_polars().row(0)[0] == 0
    assert state.db.query("SELECT COUNT(*) FROM taxonomy WHERE feature_id='F8'").to_polars().row(0)[0] == 0
    with pytest.raises(UiHttpError):
        analysis.apply_qc(state, {})


def test_apply_qc_drops_low_depth_samples(state):
    out = analysis.apply_qc(state, {"drop_low_depth": True, "min_reads": 10**6, "confirm": True})
    assert out["plan"]["samples_removed"] == 16
    assert state.db.query("SELECT COUNT(*) FROM samples").to_polars().row(0)[0] == 0


def test_rarefaction_curves_have_one_line_per_sample(state):
    out = analysis.get_rarefaction(state, P(group_by="biome", depth=300))
    assert len(out["samples"]) == 16 and all(0 < r["saturation"] <= 1 for r in out["samples"])
    assert len({t["name"] for t in out["plot"]["data"]}) == 2


def test_alpha_stats_returns_fdr_adjusted_tests(state):
    out = analysis.get_alpha_stats(state, P(group_by="biome"))
    assert out["tests"] and all(0 <= t["q"] <= 1 and t["q"] >= t["p"] for t in out["tests"])
    assert {"metric", "h", "p", "epsilon2", "pairwise"} <= set(out["tests"][0])
    with pytest.raises(UiHttpError):
        analysis.get_alpha_stats(state, P())


def test_beta_stats_finds_the_group_effect(state):
    out = analysis.get_beta_stats(state, P(group_by="biome", metric="bray_curtis", permutations=199))
    assert out["permanova"]["p"] <= 0.01 and out["permanova"]["r2"] > 0.2
    assert 0 < out["permdisp"]["p"] <= 1 and out["plot"]["data"]
    assert analysis.get_beta_stats(state, P(group_by="biome", metric="aitchison", permutations=99))["permanova"]["p"] <= 0.05


def test_beta_stats_unifrac_explains_the_tree_requirement(state):
    with pytest.raises(UiHttpError) as err:
        analysis.get_beta_stats(state, P(group_by="biome", metric="unifrac"))
    assert err.value.code == "requires_tree"
    with pytest.raises(UiHttpError):
        analysis.get_beta_stats(state, P(group_by="biome", metric="nope"))


def test_volcano_default_contrast_and_significance(state):
    out = analysis.get_volcano(state, P(group_by="biome", rank="genus"))
    assert out["a"] == "Amazon" and out["b"] == "Cerrado" and out["results"]
    assert all(r["q"] >= r["p"] for r in out["results"])
    top = out["results"][0]
    assert top["significant"] and abs(top["log2fc"]) >= 1
    with pytest.raises(UiHttpError):
        analysis.get_volcano(state, P(group_by="biome", a="Amazon", b="Amazon"))


def test_mixs_reports_present_and_missing_fields(state):
    out = analysis.get_mixs(state)
    by = {f["field"]: f for f in out["fields"]}
    assert by["geo_loc_name"]["present"] and by["geo_loc_name"]["filled_pct"] == 100.0
    assert by["env_broad_scale"]["column"] == "biome"
    assert not by["collection_date"]["present"] and out["required_total"] == 6


def test_settings_roundtrip_and_validation(state):
    assert analysis.get_settings(state)["settings"] == {}
    assert analysis.save_settings(state, {"taxonomy_db": "SILVA 138"})["settings"] == {"taxonomy_db": "SILVA 138"}
    assert analysis.save_settings(state, {"taxonomy_db": "GTDB r214"})["settings"] == {"taxonomy_db": "GTDB r214"}
    with pytest.raises(UiHttpError):
        analysis.save_settings(state, {"taxonomy_db": "mystery"})


def test_empty_database_gives_actionable_error():
    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    with pytest.raises(UiHttpError) as err:
        analysis.get_rarefaction(SimpleNamespace(db=db), {})
    assert err.value.code == "empty_feature_matrix"


def test_exports_tsv_and_biom_roundtrip(state):
    import json

    from biom.table import Table

    from flora.ui.handlers import exports

    tsv = exports.export_dataset(state, P(format="features_tsv"))
    assert tsv.filename.endswith("_feature_table.tsv") and tsv.body.decode().splitlines()[0].startswith("sample_id\t")
    assert len(tsv.body.decode().splitlines()) == 17  # header + 16 samples
    biom = exports.export_dataset(state, P(format="biom"))
    payload = json.loads(biom.body)
    assert payload["shape"] == [9, 16] and payload["rows"][0]["metadata"]["taxonomy"][1] in {"Proteobacteria", "Firmicutes", "Cyanobacteria"}
    assert isinstance(Table.from_json(payload), Table)
    assert b"Chloroplast" in exports.export_dataset(state, P(format="taxonomy_tsv")).body
    with pytest.raises(UiHttpError):
        exports.export_dataset(state, P(format="exe"))


def test_provenance_records_taxonomy_db_and_engines(state):
    from flora.ui.provenance import build_provenance

    state.projects.get = lambda _id: None
    analysis.save_settings(state, {"taxonomy_db": "SILVA 138"})
    labels = {p["label"]: p["value"] for p in build_provenance(state)["parameters"]}
    assert labels["Banco taxonômico"] == "SILVA 138"


def test_report_draft_carries_taxonomy_db_and_accessions(state, tmp_path):
    from flora.ui.handlers import report

    source = SimpleNamespace(type="mgnify", accession="MGYS00005810")
    project = SimpleNamespace(id="p1", name="Amazonia", stage="ingested", sources=[source])
    state.projects = SimpleNamespace(active_id=lambda: "p1", get=lambda _id: project)
    state.pipeline = SimpleNamespace(get_feature_matrix=lambda normalize=None: state.db.pivot_asv(normalize=normalize))
    state.experiments = SimpleNamespace(list=lambda: [])
    analysis.save_settings(state, {"taxonomy_db": "SILVA 138"})
    draft = report.report_draft(state, {"group_by": ["biome"]})
    labels = {p["label"]: p["value"] for p in draft["parameters"]}
    assert labels["Banco taxonômico"] == "SILVA 138" and labels["Accessions"] == "mgnify:MGYS00005810"
    assert any(p["label"] == "numpy" for p in draft["parameters"])


def _star_tree(features):
    return "(" + ",".join(f"{f}:1" for f in features) + ");"


def test_unifrac_beta_stats_uses_the_uploaded_tree(state):
    tree = "((F0:0.1,F1:0.1):0.2,(F2:0.1,F3:0.1):0.2,((F4:0.1,F5:0.1):0.2,(F6:0.1,F7:0.1):0.2):0.3,F8:0.5);"
    saved = analysis.save_tree(state, {"newick": tree})
    assert saved["overlap"] == 9 and analysis.tree_status(state)["overlap"] == 9
    # every feature is present in every sample, so presence/absence UniFrac cannot separate the groups...
    unweighted = analysis.get_beta_stats(state, P(group_by="biome", metric="unifrac", permutations=99))
    assert unweighted["metric"] == "unifrac" and unweighted["permanova"]["p"] > 0.5
    # ...while the abundance-weighted one sees the group-specific taxa
    weighted = analysis.get_beta_stats(state, P(group_by="biome", metric="weighted_unifrac", permutations=199))
    assert weighted["permanova"]["p"] <= 0.01 and weighted["permanova"]["r2"] > 0.2


def test_tree_upload_validation_and_mismatch(state):
    with pytest.raises(UiHttpError) as err:
        analysis.save_tree(state, {"newick": "(A,B"})
    assert err.value.code == "invalid_tree"
    with pytest.raises(UiHttpError) as err:
        analysis.save_tree(state, {"newick": "(X:1,Y:1);"})
    assert err.value.code == "tree_mismatch"
    assert analysis.tree_status(state)["present"] is False
