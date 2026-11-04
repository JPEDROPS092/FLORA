"""Catalog loading, filters and library HTTP handlers. Live checks skip when offline."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml

from flora.io import library
from flora.io.catalog import CatalogError, filter_catalog, get_entry, load_catalog
from flora.io.sources import SyntheticSource, get_source
from flora.ui.handlers import downloads
from flora.ui.http import UiHttpError

_DENIED = {"MGYS00005116", "SRP151124", "PRJNA477418", "ERP009703"}


def test_frontend_catalog_matches_yaml():
    catalog_ts = Path("src/flora/front/src/app/core/data/mock/catalog.data.ts")
    text = catalog_ts.read_text(encoding="utf-8")
    raw = text.split("=", 1)[1].strip().rstrip(";")
    front = json.loads(raw)
    back = load_catalog()
    assert [item["accession"] for item in front] == [item["accession"] for item in back]
    assert [item["n_samples"] for item in front] == [item["n_samples"] for item in back]
    assert [item["highlight"] for item in front] == [item["highlight"] for item in back]


def test_catalog_loads_verified_entries():
    entries = load_catalog()
    by_acc = {item["accession"]: item for item in entries}
    assert len(by_acc) == len(entries) >= 15
    assert not _DENIED & set(by_acc)
    amazon = by_acc["MGYS00005779"]
    assert amazon["n_samples"] == 64
    assert amazon["seq_type"] == "WGS"
    assert amazon["highlight"] == "amazonia"
    assert amazon["verified_at"] == "2026-11-03"
    assert by_acc["MGYS00005810"]["bioproject"] == "PRJNA237344"
    assert by_acc["MGYS00004385"]["seq_type"] == "amplicon"
    assert by_acc["MGYS00004385"]["n_samples"] == 29
    assert by_acc["PRJEB8682"]["highlight"] == ""
    assert by_acc["PRJEB8682"]["secondary"] == "ERP009703"
    assert by_acc["PRJEB8682"]["seq_type"] == "misto"
    assert by_acc["MGYS00006055"]["highlight"] == ""
    assert by_acc["EMP-R1"]["license"] == "CC-BY-4.0"
    assert by_acc["QIIME2-MP"]["n_samples"] == 34
    assert by_acc["MOTHUR-SOP"]["n_samples"] == 20
    for entry in entries:
        assert entry["verified_at"]
        assert entry["seq_type"] in {"amplicon", "WGS", "misto"}


def test_catalog_filters_biome_region_and_text():
    solo = filter_catalog(biome="solo", amazonia=True)
    assert {item["accession"] for item in solo} == {"MGYS00005779", "MGYS00001352"}
    hosts = filter_catalog(host="humano")
    assert {item["accession"] for item in hosts} >= {"QIIME2-MP", "PRJNA43021"}
    wgs = filter_catalog(region="amazonia", seq_type="WGS", q="colomb")
    assert [item["accession"] for item in wgs] == ["MGYS00005779"]
    assert filter_catalog(q="does-not-exist-xyz") == []


def test_catalog_rejects_incomplete_file(tmp_path: Path):
    (tmp_path / "broken.yaml").write_text("[{id: only}]\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(tmp_path)


def test_catalog_roundtrip_yaml_shape(tmp_path: Path):
    payload = {
        "id": "x",
        "title": "T",
        "title_pt": "T pt",
        "description": "d",
        "source": "synthetic",
        "accession": "X1",
        "biome": "sintetico",
        "host": "ambiental",
        "region": "brasil",
        "n_samples": 1,
        "seq_type": "amplicon",
        "verified_at": "2026-11-03",
        "importable": True,
        "download_note": "nota",
        "highlight": "",
    }
    (tmp_path / "one.yaml").write_text(yaml.safe_dump([payload]), encoding="utf-8")
    [entry] = load_catalog(tmp_path)
    assert entry["accession"] == "X1"
    assert get_entry("synthetic", "X1", tmp_path)["id"] == "x"


def test_catalog_endpoint_filters():
    params = {"biome": ["solo"], "amazonia": ["1"], "q": ["colomb"]}
    payload = downloads.library_catalog(None, params)
    assert payload["success"] is True
    assert [item["accession"] for item in payload["studies"]] == ["MGYS00005779"]
    assert payload["count"] == 1


def test_metadata_unknown_accession_is_404():
    with pytest.raises(UiHttpError) as err:
        downloads.library_metadata(None, {"source": ["mgnify"], "accession": ["MGYS00000000"]})
    assert err.value.status == 404


def test_metadata_and_download_routes():
    assert downloads.library_route("GET", "/api/library/catalog") == ("catalog", {})
    kind, extra = downloads.library_route("GET", "/api/library/mgnify/MGYS00005779/metadata")
    assert kind == "metadata" and extra == {"source": "mgnify", "accession": "MGYS00005779"}
    kind, extra = downloads.library_route("POST", "/api/library/url/QIIME2-MP/download")
    assert kind == "download" and extra["accession"] == "QIIME2-MP"
    assert downloads.library_route("POST", "/api/library/catalog") is None
    assert downloads.library_route("GET", "/api/library/../etc/metadata") is None


def test_synthetic_metadata_and_recorded_download(tmp_path: Path):
    preview = SyntheticSource().metadata("SYNTHETIC", limit=3)
    assert preview["row_count"] == 3
    assert preview["truncated"] is True
    assert preview["rows"][0]["sample_id"] == "S000"

    state = SimpleNamespace(workdir=tmp_path)
    payload = downloads.recorded("synthetic", downloads.library_download)(
        state,
        {"source": "synthetic", "accession": "SYNTHETIC", "samples": 6, "features": 8, "seed": 1},
    )
    assert payload["job"]["status"] == "completed"
    assert Path(payload["metadata"]).exists()
    assert Path(payload["asv_table"]).exists()
    jobs = downloads.list_downloads(state)["jobs"]
    assert jobs[0]["source"] == "synthetic"
    assert any(item["label"] == "Metadata" for item in jobs[0]["artifacts"])


def test_download_rejects_path_escape(tmp_path: Path):
    state = SimpleNamespace(workdir=tmp_path)
    with pytest.raises(UiHttpError) as err:
        downloads.library_download(
            state,
            {"source": "synthetic", "accession": "SYNTHETIC", "output_dir": "../outside"},
        )
    assert err.value.code == "invalid_output_dir"


def test_mgnify_metadata_uses_source(monkeypatch):
    class _Fake:
        def metadata(self, accession, limit=50):
            return {
                "source": "mgnify",
                "accession": accession,
                "columns": ["sample_id"],
                "rows": [{"sample_id": "ERS1"}],
                "row_count": 1,
                "truncated": False,
            }

    import flora.io.sources as sources

    monkeypatch.setattr(sources, "get_source", lambda source: _Fake())
    payload = downloads.library_metadata(
        None, {"source": ["mgnify"], "accession": ["MGYS00005779"], "limit": ["10"]}
    )
    assert payload["preview"]["rows"][0]["sample_id"] == "ERS1"


def test_unknown_source_rejected():
    with pytest.raises(library.LibraryError):
        get_source("nope")


def test_mgnify_metadata_and_download_are_local(monkeypatch, tmp_path: Path):
    import flora.io.sources as sources
    from flora.io.downloaders import MGnifyDownloader

    sample = {
        "id": "ERS1",
        "attributes": {
            "latitude": 1.5,
            "longitude": -75.9,
            "environment-biome": "ENVO:01000228",
            "environment-feature": "litter",
            "environment-material": "soil",
            "geo-loc-name": None,
        },
    }
    monkeypatch.setattr(
        MGnifyDownloader,
        "_iter_paginated",
        lambda self, session, url: iter([sample]),
    )
    preview = get_source("mgnify").metadata("MGYS00005779", limit=50)
    assert preview["rows"][0]["sample_id"] == "ERS1"
    assert preview["rows"][0]["latitude"] == 1.5
    assert preview["truncated"] is False

    monkeypatch.setattr(sources, "_mgnify_samples", lambda accession, limit: preview["rows"])
    monkeypatch.setattr(sources, "_download_ssu_table", lambda accession, output_dir: {})
    written = get_source("mgnify").download("MGYS00005779", tmp_path)
    header = Path(written["metadata"]).read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("sample_id")
    with pytest.raises(library.LibraryError):
        get_source("mgnify").metadata("not-an-accession")


def test_ena_metadata_parses_runs(monkeypatch):
    import flora.io.sources as sources

    class _Response:
        text = "[{}]"

        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"run_accession": "ERR1", "library_strategy": "WGS", "country": ""},
                {"run_accession": "ERR2", "library_strategy": "AMPLICON", "country": "Brazil"},
            ]

    class _Session:
        def get(self, url, params=None, timeout=None, stream=None):
            return _Response()

    monkeypatch.setattr(sources, "_make_session", lambda: _Session())
    preview = get_source("ena").metadata("PRJEB8682", limit=1)
    assert preview["row_count"] == 1
    assert preview["truncated"] is True
    assert preview["rows"][0]["run_accession"] == "ERR1"


def test_url_preview_and_download(monkeypatch, tmp_path: Path):
    import flora.io.sources as sources

    monkeypatch.setattr(
        sources,
        "_fetch_text",
        lambda url, max_bytes=0: "sample-id\tbody-site\nL1S8\tgut\nL2\tskin\n",
    )
    preview = get_source("url").metadata("QIIME2-MP", limit=1)
    assert preview["rows"] == [{"sample-id": "L1S8", "body-site": "gut"}]
    assert preview["truncated"] is True

    def fake_download(url, dest, session=None, min_bytes=100):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("data", encoding="utf-8")
        return dest

    monkeypatch.setattr(sources, "_download_file", fake_download)
    written = get_source("url").download("QIIME2-MP", tmp_path)
    assert set(written) >= {"metadata", "sequences", "barcodes"}
    assert Path(written["metadata"]).read_text(encoding="utf-8") == "data"


def test_live_mgnify_catalog_entry_still_matches():
    """Fails when the curated title or sample count drifts. Skips with no network."""
    entry = get_entry("mgnify", "MGYS00005779")
    assert entry is not None
    try:
        response = requests.get(
            "https://www.ebi.ac.uk/metagenomics/api/v1/studies/MGYS00005779",
            timeout=25,
            headers={"User-Agent": "FLORA-Library/0.1.0"},
        )
        response.raise_for_status()
        attrs = response.json()["data"]["attributes"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        pytest.skip(f"offline or API unavailable: {exc}")
    assert attrs["samples-count"] == entry["n_samples"]
    assert attrs["study-name"] == entry["title"]
