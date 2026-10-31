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
