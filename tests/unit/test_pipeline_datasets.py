"""Pipeline dataset discovery and upload from the computer."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from flora.ui.handlers import datasets
from flora.ui.http import UiHttpError


def _state(tmp_path):
    projects = SimpleNamespace(active_id=lambda: None, dir=lambda pid: tmp_path / "projects" / pid)
    return SimpleNamespace(workdir=tmp_path, projects=projects)


def test_lists_complete_and_incomplete_datasets(tmp_path):
    full = tmp_path / "raw" / "synthetic"
    full.mkdir(parents=True)
    (full / "metadata.tsv").write_text("sample_id\tbiome\nS1\tA\nS2\tB\n")
    (full / "asv_table.tsv").write_text("sample_id\tASV_1\nS1\t3\n")
    (full / "taxonomy.tsv").write_text("feature_id\tphylum\nASV_1\tX\n")
    raw = tmp_path / "raw" / "mgnify" / "MGYS1"
    (raw / "fastq").mkdir(parents=True)
    (raw / "manifest.tsv").write_text("sample-id\n")

    items = {d["label"]: d for d in datasets.list_datasets(_state(tmp_path))["datasets"]}
    synthetic = items["synthetic"]
    assert synthetic["complete"] and synthetic["samples"] == 2 and synthetic["columns"] == ["sample_id", "biome"]
    mg = items["mgnify/MGYS1"]
    assert not mg["complete"] and mg["raw_reads_only"] and set(mg["missing"]) == {"metadata", "asv", "taxonomy"}


def test_empty_workdir_lists_nothing(tmp_path):
    assert datasets.list_datasets(_state(tmp_path))["datasets"] == []


def test_upload_stores_file_and_returns_columns(tmp_path):
    content = base64.b64encode(b"sample_id\tgroup\nS1\ta\n").decode()
    out = datasets.upload_file(_state(tmp_path), {"kind": "metadata", "filename": "../../my meta.tsv", "content": content})
    assert out["path"].startswith(str(tmp_path / "uploads" / "manual"))
    assert "/.." not in out["path"] and out["columns"] == ["sample_id", "group"]
    assert (tmp_path / "uploads" / "manual" / "my_meta.tsv").read_text().startswith("sample_id")


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "x", "filename": "a.tsv", "content": "QQ=="},
        {"kind": "asv", "filename": "run.sh", "content": "QQ=="},
        {"kind": "asv", "filename": "a.tsv", "content": "***"},
        {"kind": "asv", "filename": "a.tsv", "content": ""},
    ],
)
def test_upload_rejects_bad_input(tmp_path, body):
    with pytest.raises(UiHttpError):
        datasets.upload_file(_state(tmp_path), body)
