from __future__ import annotations

from flora.ui.handlers import report


def test_preview_report_reads_html(tmp_path):
    html = tmp_path / "report.html"
    html.write_text("<html><body>ok</body></html>", encoding="utf-8")

    content = report.preview_report(None, {"path": [str(html)]})

    assert "ok" in content
