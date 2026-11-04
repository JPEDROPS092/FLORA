"""MGnify taxonomy-abundance table -> FLORA asv_table/taxonomy."""

from __future__ import annotations

import polars as pl
import pytest

from flora.io.mgnify_tables import analysis_sample_map, convert_ssu_table, parse_lineage

TABLE = (
    "#SampleID\tERZ1\tERZ2\tERR9\n"
    "sk__Archaea\t1\t0\t0\n"
    "sk__Bacteria;k__;p__Proteobacteria;c__Alpha;o__;f__;g__Rhizobium\t5\t2\t3\n"
    "sk__Bacteria;k__;p__Firmicutes\t0\t0\t0\n"
)


def test_parse_lineage_ranks_and_empties():
    tax = parse_lineage("sk__Bacteria;k__;p__Proteobacteria;c__Alpha;o__;f__;g__Rhizobium")
    assert tax["kingdom"] == "Bacteria" and tax["phylum"] == "Proteobacteria" and tax["genus"] == "Rhizobium"
    assert tax["order"] == "" and tax["species"] == ""


def test_convert_maps_columns_to_samples_and_sums_duplicates(tmp_path):
    out = convert_ssu_table(TABLE, {"ERZ1": "S1", "ERZ2": "S2", "ERR9": "S2"}, tmp_path)
    asv = pl.read_csv(out["asv_table"], separator="\t")
    tax = pl.read_csv(out["taxonomy"], separator="\t")
    assert asv["sample_id"].to_list() == ["S1", "S2"]
    assert asv.columns == ["sample_id", "MGN_00001", "MGN_00002"]  # all-zero feature dropped
    assert asv.filter(pl.col("sample_id") == "S2")["MGN_00002"].item() == 5  # ERZ2 + ERR9 summed
    assert tax["genus"].to_list()[1] == "Rhizobium" and tax.columns[0] == "feature_id"


def test_unmapped_columns_are_kept_not_dropped(tmp_path):
    out = convert_ssu_table(TABLE, {"ERZ1": "S1"}, tmp_path)
    assert pl.read_csv(out["asv_table"], separator="\t")["sample_id"].to_list() == ["S1", "ERZ2", "ERR9"]


def test_empty_table_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        convert_ssu_table("#SampleID\tA\nsk__X\t0\n", {}, tmp_path)


def test_analysis_sample_map_uses_assembly_run_and_id():
    analyses = [
        {"id": "MGYA1", "relationships": {"sample": {"data": {"id": "SRS1"}}, "assembly": {"data": {"id": "ERZ1"}}, "run": {"data": None}}},
        {"id": "MGYA2", "relationships": {"sample": {"data": {"id": "SRS2"}}, "run": {"data": {"id": "ERR2"}}}},
        {"id": "MGYA3", "relationships": {}},
    ]
    assert analysis_sample_map(analyses) == {"ERZ1": "SRS1", "MGYA1": "SRS1", "ERR2": "SRS2", "MGYA2": "SRS2"}


def test_project_sync_ingests_mgnify_when_tables_are_complete(tmp_path, monkeypatch):
    from flora.projects.sync import SyncManager
    from flora.io import sources

    raw = tmp_path / "raw"
    done = {"metadata": raw / "metadata.tsv", "asv_table": raw / "asv_table.tsv", "taxonomy": raw / "taxonomy.tsv"}

    def fake(accession, out):
        return {k: str(v) for k, v in done.items()}

    monkeypatch.setattr(sources, "download_mgnify_tables", fake)
    from flora.projects.registry import Source

    mgr = SyncManager.__new__(SyncManager)
    files = mgr._download(Source(type="mgnify", accession="MGYS1"), raw, {"log": []})
    assert files and set(files) == {"metadata", "asv", "taxonomy"}

    job = {"log": []}
    monkeypatch.setattr(sources, "download_mgnify_tables", lambda a, o: {"metadata": str(done["metadata"])})
    assert mgr._download(Source(type="mgnify", accession="MGYS1"), raw, job) is None
    assert "só os metadados" in job["log"][0]
