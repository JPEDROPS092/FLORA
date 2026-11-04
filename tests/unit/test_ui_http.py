"""Tests for UI HTTP helpers."""

import pytest

from flora.ui.http import UiHttpError, json_error, json_success


def test_json_success_wraps_payload():
    payload = json_success(data={"status": "ok"}, message="ready")

    assert payload["success"] is True
    assert payload["message"] == "ready"
    assert payload["status"] == "ok"


def test_json_error_wraps_http_error():
    error = UiHttpError("bad input", status=422, code="invalid_input", details={"field": "path"})
    payload = json_error(error)

    assert payload == {
        "success": False,
        "error": "bad input",
        "code": "invalid_input",
        "details": {"field": "path"},
    }


def test_ui_http_error_is_exception():
    with pytest.raises(UiHttpError):
        raise UiHttpError("boom", status=500)


def test_taxonomy_endpoint_reports_no_data_instead_of_internal_error():
    from types import SimpleNamespace

    from flora.db.connection import FloraDB
    from flora.db.schema import initialize_schema
    from flora.ui.handlers import viz

    db = FloraDB.connect(":memory:")
    initialize_schema(db)
    with pytest.raises(UiHttpError) as err:
        viz.viz_taxonomy(SimpleNamespace(db=db), {"level": ["phylum"]})
    assert err.value.status == 400 and err.value.code == "empty_feature_matrix"


def test_taxonomy_barplot_without_group_column_and_with_other_bucket():
    import polars as pl

    from flora.viz.taxonomy_plots import plot_taxonomy_barplot

    df = pl.DataFrame({"phylum": ["A", "B", "C"], "mean_abundance": [5.0, 3.0, 1.0], "n_samples": [2, 2, 1]})
    fig = plot_taxonomy_barplot(df, level="phylum", top_n=2)
    assert {trace.name for trace in fig.data} == {"A", "B", "Outros"}
