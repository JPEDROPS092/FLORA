"""End-to-end synthetic study through the HTTP API (80 samples).

This is the run documented in the pull request: download, replace-mode ingest,
QC, adaptive diversity, statistics, stratified classification and the report.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from flora.ui.server import create_app


def _call(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {}
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode())
        raise AssertionError(f"{method} {path} -> {exc.code} {payload}") from exc


@pytest.fixture()
def api(tmp_path):
    server_cls, handler_cls, _state = create_app(workdir=tmp_path)
    httpd = server_cls(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base, tmp_path
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_synthetic_pipeline_over_http(api):
    base, tmp_path = api
    project = _call(base, "POST", "/api/projects", {"name": "Sintético 80", "question": "Os biomas diferem?"})["project"]
    _call(base, "POST", "/api/projects/activate", {"id": project["id"]})
    assert _call(base, "GET", f"/api/projects/detail?id={project['id']}")["project"]["stage"] == "empty"

    files = _call(base, "POST", "/api/download/synthetic", {
        "output_dir": str(tmp_path / "synthetic"), "samples": 80, "features": 40, "seed": 7,
    })
    ingested = _call(base, "POST", "/api/ingest/dataset", {
        "metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"],
    })
    assert [step["step"] for step in ingested["steps"]] == ["metadata", "asv", "taxonomy"]
    assert ingested["project_stage"] == "ingested"
    detail = _call(base, "GET", f"/api/projects/detail?id={project['id']}")["project"]
    assert detail["stage"] == "ingested" and detail["samples"] == 80

    qc = _call(base, "GET", "/api/analysis/qc")
    assert qc["success"] is True and qc["summary"]["samples"] == 80
    assert any(row["reads"] > 0 for row in qc["samples"])

    diversity = _call(base, "POST", "/api/diversity", {})
    assert diversity["depth_source"] == "adaptive_min"
    assert diversity["sampling_depth"] == diversity["reads"]["min"]
    assert diversity["dropped_count"] == 0 and diversity["retained"] == 80
    assert diversity["reads"]["max"] < 10000  # the old default would have rejected this table

    alpha = _call(base, "GET", "/api/analysis/alpha_stats?group_by=biome")
    assert alpha["tests"] and all("q" in row for row in alpha["tests"]) and alpha["n_samples"] == 80
    beta = _call(base, "GET", "/api/analysis/beta_stats?group_by=biome&permutations=99")
    assert {"f", "r2", "p"} <= set(beta["permanova"]) and {"f", "p"} <= set(beta["permdisp"])
    volcano = _call(base, "GET", "/api/analysis/volcano?group_by=biome&rank=genus&a=Amazon&b=Cerrado")
    assert volcano["a"] == "Amazon" and volcano["b"] == "Cerrado" and volcano["results"]

    trained = _call(base, "POST", "/api/ml/classify", {
        "model": "random_forest", "target_column": "biome", "split": "auto", "test_size": 0.25, "seed": 7, "cv_folds": 3,
    })
    assert trained["success"] and trained["experiment"]["train_n"] and trained["experiment"]["test_n"]
    assert "estratificada" in " ".join(trained["experiment"]["limitations"])

    generated = _call(base, "POST", "/api/report", {"title": "Sintético 80", "group_by": "biome", "output_path": str(tmp_path / "report.html")})
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "cdn.plot.ly" in html and "Kruskal-Wallis" in html and "PERMANOVA" in html
    assert generated["sections"] >= 8 and len(html) < 2_000_000

    other = _call(base, "POST", "/api/download/synthetic", {
        "output_dir": str(tmp_path / "other"), "samples": 5, "features": 6, "seed": 8,
    })
    replaced = _call(base, "POST", "/api/ingest/dataset", {
        "metadata_path": other["metadata"], "asv_path": other["asv_table"], "taxonomy_path": other["taxonomy"],
    })
    assert replaced["replaced"]["samples"] == 80
    assert _call(base, "GET", f"/api/projects/detail?id={project['id']}")["project"]["samples"] == 5

    cleared = _call(base, "POST", "/api/ingest/clear", {"confirm": True})
    assert cleared["applied"] is True
    assert _call(base, "GET", f"/api/projects/detail?id={project['id']}")["project"]["samples"] == 0


def test_volcano_requires_two_groups_when_more_exist(api):
    """Separated so the pipeline test can pass a contrast after the refusal is checked."""
    base, tmp_path = api
    project = _call(base, "POST", "/api/projects", {"name": "Volcano"})["project"]
    _call(base, "POST", "/api/projects/activate", {"id": project["id"]})
    files = _call(base, "POST", "/api/download/synthetic", {
        "output_dir": str(tmp_path / "synthetic"), "samples": 12, "features": 6, "seed": 1,
    })
    _call(base, "POST", "/api/ingest/dataset", {
        "metadata_path": files["metadata"], "asv_path": files["asv_table"], "taxonomy_path": files["taxonomy"],
    })
    request = urllib.request.Request(base + "/api/analysis/volcano?group_by=biome&rank=genus")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(request, timeout=60)
    payload = json.loads(err.value.read().decode())
    assert err.value.code == 400 and payload["code"] == "needs_contrast" and "grupos" in payload["error"]
    ok = _call(base, "GET", "/api/analysis/volcano?group_by=biome&rank=genus&a=Amazon&b=Cerrado")
    assert ok["a"] == "Amazon" and ok["b"] == "Cerrado" and "results" in ok
