"""Self-contained HTML report generator for FLORA analysis runs.

FLORAReport collects Plotly figures, metric tables, and text sections
and renders them into a single auto-contained HTML file that requires
no external dependencies to open.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from jinja2 import Environment, BaseLoader
from plotly.offline import get_plotlyjs

logger = logging.getLogger("flora.reports")

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
  :root { color-scheme: light; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f1e8; margin: 0; padding: 0; color: #1f2937; }
  header { background: linear-gradient(135deg, #1f5137, #0f766e); color: white; padding: 28px 40px; }
  header h1 { margin: 0; font-size: 2.2em; letter-spacing: -0.04em; }
  header p { margin: 6px 0 0; opacity: 0.88; }
  .topbar { max-width: 1200px; margin: 0 auto; }
  .toc { max-width: 1200px; margin: 18px auto 0; padding: 0 24px; display: flex; flex-wrap: wrap; gap: 10px; }
  .toc a { text-decoration: none; color: #285943; background: rgba(255,255,255,0.9); border: 1px solid rgba(31,41,55,0.12); border-radius: 999px; padding: 8px 14px; font-size: 0.92em; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .summary-banner { display: grid; gap: 16px; grid-template-columns: 1.3fr 1fr; margin-bottom: 24px; }
  .hero-card, .notice-card { background: rgba(255, 253, 248, 0.96); border-radius: 18px; padding: 22px 24px; border: 1px solid rgba(31,41,55,0.10); box-shadow: 0 8px 32px rgba(31,41,55,0.08); }
  .hero-card h2, .notice-card h3 { margin: 0 0 8px; color: #1f5137; }
  .hero-card p, .notice-card p, .notice-card li { color: #4b5563; line-height: 1.6; }
  .section { background: rgba(255, 253, 248, 0.98); border-radius: 18px; padding: 24px; margin-bottom: 24px; border: 1px solid rgba(31,41,55,0.10); box-shadow: 0 8px 32px rgba(31,41,55,0.08); }
  .section h2 { margin-top: 0; color: #1f5137; border-bottom: 2px solid rgba(31,41,55,0.10); padding-bottom: 10px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
  .metric-card { background: #f0f7f3; border-radius: 14px; padding: 16px; text-align: center; border: 1px solid rgba(15,118,110,0.10); }
  .metric-card .value { font-size: 2em; font-weight: bold; color: #1a6b3c; }
  .metric-card .label { color: #666; font-size: 0.9em; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
  th { background: #1a6b3c; color: white; padding: 10px 14px; text-align: left; }
  td { padding: 8px 14px; border-bottom: 1px solid #eee; }
  tr:hover td { background: #f0f7f3; }
  .text-block { color: #333; line-height: 1.6; white-space: pre-wrap; font-family: monospace;
                background: #f5f5f5; padding: 12px; border-radius: 12px; }
  .empty-state { padding: 16px; border-radius: 14px; background: rgba(220,107,47,0.10); color: #8a3c13; }
  footer { text-align: center; color: #888; padding: 24px; font-size: 0.85em; }
  .plotly-chart { width: 100%; }
  ul { margin: 0; padding-left: 20px; }
  @media (max-width: 900px) {
    .summary-banner { grid-template-columns: 1fr; }
  }
  @media print {
    body { background: white; }
    .toc { display: none; }
    .section, .hero-card, .notice-card { box-shadow: none; border: 1px solid #d1d5db; break-inside: avoid; }
  }
</style>
<script>{{ plotly_js | safe }}</script>
</head>
<body>
<header>
  <div class="topbar">
    <h1>{{ title }}</h1>
    <p>Generated {{ timestamp }} | FLORA v{{ version }}</p>
  </div>
</header>
{% if sections %}
<nav class="toc">
  {% for section in sections %}
  <a href="#{{ section.id }}">{{ section.title }}</a>
  {% endfor %}
</nav>
{% endif %}
<div class="container">
  {% if summary %}
  <section class="summary-banner">
    <div class="hero-card">
      <h2>Analysis Summary</h2>
      <p>{{ summary.overview }}</p>
    </div>
    <div class="notice-card">
      <h3>Export Notes</h3>
      <ul>
        {% for item in summary.notes %}
        <li>{{ item }}</li>
        {% endfor %}
      </ul>
    </div>
  </section>
  {% endif %}

{% for section in sections %}
<div class="section" id="{{ section.id }}">
  <h2>{{ section.title }}</h2>

  {% if section.type == "metrics" %}
  <div class="metrics-grid">
    {% for k, v in section.data.items() %}
    <div class="metric-card">
      <div class="value">{{ v }}</div>
      <div class="label">{{ k }}</div>
    </div>
    {% endfor %}
  </div>

  {% elif section.type == "table" %}
  {% if section.rows %}
  <table>
    <thead><tr>{% for col in section.columns %}<th>{{ col }}</th>{% endfor %}</tr></thead>
    <tbody>
      {% for row in section.rows %}
      <tr>{% for cell in row %}<td>{{ cell }}</td>{% endfor %}</tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty-state">No rows available for this section.</div>
  {% endif %}

  {% elif section.type == "text" %}
  <div class="text-block">{{ section.data }}</div>

  {% elif section.type == "plot" %}
  <div class="plotly-chart" id="{{ section.id }}_chart"></div>
  <script>
    var spec = {{ section.data }};
    Plotly.newPlot('{{ section.id }}_chart', spec.data, spec.layout, {responsive: true});
  </script>

  {% endif %}
</div>
{% endfor %}

</div>
<footer>
  Generated by FLORA — Feature Learning and Omics Research Analytics
</footer>
</body>
</html>
"""


@dataclass
class ReportSection:
    """A single section in the FLORA HTML report.

    Parameters
    ----------
    title : str
        Section heading.
    section_type : str
        One of: ``"metrics"``, ``"table"``, ``"text"``, ``"plot"``.
    data : Any
        Content appropriate for the section type.
    section_id : str, optional
        HTML element ID. Auto-generated if not provided.
    """

    title: str
    section_type: str
    data: Any
    section_id: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.section_id:
            self.section_id = self.title.lower().replace(" ", "_").replace("/", "_")


class FLORAReport:
    """Consolidated HTML report for a FLORA analysis run.

    Parameters
    ----------
    title : str
        Report title displayed in the header.
    version : str
        Library version string.

    Examples
    --------
    >>> report = FLORAReport(title="Amazonian Microbiome Analysis")
    >>> report.add_metrics("Pipeline Summary", {"Samples": 80, "ASVs": 3421})
    >>> report.add_plot("PCoA", pcoa_fig)
    >>> report.save("results/report.html")
    """

    def __init__(
        self,
        title: str = "FLORA Analysis Report",
        version: str = "0.1.0",
    ) -> None:
        self.title = title
        self.version = version
        self.summary_overview = ""
        self.summary_notes: list[str] = []
        self._sections: list[ReportSection] = []

    def set_summary(
        self,
        overview: str,
        notes: list[str] | None = None,
    ) -> "FLORAReport":
        """Set the report summary banner content."""
        self.summary_overview = overview
        self.summary_notes = notes or []
        return self

    def add_metrics(
        self,
        title: str,
        metrics: dict[str, Any],
        section_id: str = "",
    ) -> "FLORAReport":
        """Add a metrics card grid section.

        Parameters
        ----------
        title : str
            Section heading.
        metrics : dict
            Keys are metric labels, values are formatted values.
        section_id : str, optional
            HTML element ID.

        Returns
        -------
        FLORAReport
            Self, for method chaining.
        """
        formatted = {k: self._fmt(v) for k, v in metrics.items()}
        self._sections.append(ReportSection(
            title=title,
            section_type="metrics",
            data=formatted,
            section_id=section_id,
        ))
        return self

    def add_table(
        self,
        title: str,
        df: pl.DataFrame,
        max_rows: int = 50,
        section_id: str = "",
    ) -> "FLORAReport":
        """Add a data table section from a Polars DataFrame.

        Parameters
        ----------
        title : str
            Section heading.
        df : polars.DataFrame
            Table data. Columns become headers; rows become cells.
        max_rows : int
            Maximum rows to display in the report.
        section_id : str, optional
            HTML element ID.

        Returns
        -------
        FLORAReport
            Self, for method chaining.
        """
        sub = df.head(max_rows)
        cols = sub.columns
        rows = [[self._fmt(v) for v in row] for row in sub.iter_rows()]
        section = ReportSection(
            title=title,
            section_type="table",
            data=None,
            section_id=section_id,
        )
        section.columns = cols
        section.rows = rows
        self._sections.append(section)
        return self

    def add_plot(
        self,
        title: str,
        fig: Any,
        section_id: str = "",
    ) -> "FLORAReport":
        """Add a Plotly figure as an interactive plot section.

        Parameters
        ----------
        title : str
            Section heading.
        fig : plotly.graph_objects.Figure
            Any Plotly figure.
        section_id : str, optional
            HTML element ID.

        Returns
        -------
        FLORAReport
            Self, for method chaining.
        """
        json_str = fig.to_json()
        self._sections.append(ReportSection(
            title=title,
            section_type="plot",
            data=json_str,
            section_id=section_id,
        ))
        return self

    def add_text(
        self,
        title: str,
        text: str,
        section_id: str = "",
    ) -> "FLORAReport":
        """Add a preformatted text block section.

        Parameters
        ----------
        title : str
            Section heading.
        text : str
            Preformatted text (e.g. classification report, notes).
        section_id : str, optional
            HTML element ID.

        Returns
        -------
        FLORAReport
            Self, for method chaining.
        """
        self._sections.append(ReportSection(
            title=title,
            section_type="text",
            data=text,
            section_id=section_id,
        ))
        return self

    def save(self, path: str | Path) -> Path:
        """Render and save the report to an HTML file.

        The output file is fully self-contained (Plotly loaded from CDN).

        Parameters
        ----------
        path : str or Path
            Destination file path.

        Returns
        -------
        Path
            Resolved path to the saved report.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        env = Environment(loader=BaseLoader())
        tmpl = env.from_string(_TEMPLATE)

        section_dicts = []
        for s in self._sections:
            d = {
                "id": s.section_id or s.title.lower().replace(" ", "_"),
                "title": s.title,
                "type": s.section_type,
                "data": s.data,
                "columns": s.columns,
                "rows": s.rows,
            }
            section_dicts.append(d)

        html = tmpl.render(
            title=self.title,
            version=self.version,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            sections=section_dicts,
            summary={
                "overview": self.summary_overview,
                "notes": self.summary_notes,
            } if self.summary_overview or self.summary_notes else None,
            plotly_js=get_plotlyjs(),
        )

        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(html)

        logger.info("Report saved to %s (%d sections)", dest, len(self._sections))
        return dest

    @staticmethod
    def _fmt(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.4f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)
