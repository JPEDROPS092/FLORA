"""Study library: curated entries, MGnify/ENA parsing and error handling (network mocked)."""

from __future__ import annotations

import pytest
import requests

from flora.io import library
from flora.ui.handlers import downloads
from flora.ui.http import UiHttpError


class _Resp:
    def __init__(self, payload=None, text=""):
        self._payload, self.text = payload, text

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_curated_lists_verified_catalog_and_filters():
    accessions = {s["accession"] for s in library.search("curated")}
    assert {"EMP-R1", "MGYS00005779", "PRJEB8682", "SYNTHETIC"} <= accessions
    assert not accessions & set(library.MISLABELLED_AMAZON)
    osd = library.search("curated", "ERP009703")
    assert [s["accession"] for s in osd] == ["PRJEB8682"]
    assert "rhizosphere" not in osd[0]["title"].lower()
    assert library.search("curated", "colombian amazon")[0]["accession"] == "MGYS00005779"


def test_mgnify_parses_studies(monkeypatch):
    payload = {"data": [{"id": "MGYS1", "attributes": {"study-name": "Soil", "samples-count": 5, "bioproject": "PRJEB1", "last-update": "2025-01-02T00:00:00"}}]}
    monkeypatch.setattr(library.requests, "get", lambda *a, **k: _Resp(payload))
    [s] = library.search("mgnify", "soil")
    assert (s["accession"], s["title"], s["samples"], s["bioproject"], s["updated"]) == ("MGYS1", "Soil", 5, "PRJEB1", "2025-01-02")


def test_ena_parses_and_requires_query(monkeypatch):
    rows = [{"study_accession": "PRJNA1", "secondary_study_accession": "SRP1", "study_title": "16S", "center_name": "X", "first_public": "2020-01-01"}]
    monkeypatch.setattr(library.requests, "get", lambda *a, **k: _Resp(rows, text="[x]"))
    [s] = library.search("ena", "16S soil")
    assert s["bioproject"] == "PRJNA1" and s["secondary"] == "SRP1"
    with pytest.raises(library.LibraryError):
        library.search("ena", "")


def test_resolve_runs_and_validation(monkeypatch):
    monkeypatch.setattr(library.requests, "get", lambda *a, **k: _Resp(text="run_accession\nSRR1\nSRR2\n"))
    assert library.resolve_runs("SRP151124") == ["SRR1", "SRR2"]
    with pytest.raises(library.LibraryError):
        library.resolve_runs("../etc/passwd")


def test_remote_failure_becomes_http_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(library.requests, "get", boom)
    with pytest.raises(UiHttpError) as err:
        downloads.library_search(None, {"source": ["mgnify"], "q": ["x"]})
    assert err.value.status == 502
    with pytest.raises(UiHttpError):
        downloads.library_search(None, {"source": ["nope"]})
