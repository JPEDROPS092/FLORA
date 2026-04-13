"""Unit tests for robust MGnify downloader field parsing."""

from flora.io.downloaders import _as_lower_text


def test_as_lower_text_handles_plain_string() -> None:
    assert _as_lower_text("Taxonomy TSV") == "taxonomy tsv"


def test_as_lower_text_handles_none() -> None:
    assert _as_lower_text(None) == ""


def test_as_lower_text_handles_dict_payload() -> None:
    value = {"name": "Tax Assignment", "id": "SSU rRNA"}
    result = _as_lower_text(value)
    assert "tax assignment" in result
    assert "ssu rrna" in result


def test_as_lower_text_handles_list_payload() -> None:
    value = ["OTU table", 123, "Reads SSU"]
    assert _as_lower_text(value) == "otu table 123 reads ssu"
