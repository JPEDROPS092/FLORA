"""Reporting UI handlers."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import polars as pl

from flora.core.exceptions import DatabaseError, PipelineError, ValidationError
from flora.ui.analytics import build_publication_checklist
from flora.ui.http import UiHttpError
from flora.ui.http import json_success

logger = logging.getLogger("flora.ui.report")


def _report_preview_url(path: Path) -> str:
    return f"/api/report/preview?path={quote(path.as_posix())}"


def _count_tables(state) -> dict[str, int]:
    info = state.db.table_info()
    return {row["table_name"]: int(row["row_count"]) for row in info.iter_rows(named=True)}


def _sample_summary(state) -> dict[str, str]:
    summary = {}
    try:
        metadata = state.db.query(
            """
            SELECT
              COUNT(*) AS n_samples,
              COUNT(DISTINCT biome) AS n_biomes,
              COUNT(DISTINCT location) AS n_locations,
              COALESCE(ROUND(AVG(sequencing_depth), 2), 0) AS mean_depth
            FROM samples
            """
        ).to_polars()
        if not metadata.is_empty():
            row = metadata.row(0, named=True)
            summary = {
                "Samples": row["n_samples"],
                "Biomes": row["n_biomes"],
                "Locations": row["n_locations"],
                "Mean depth": row["mean_depth"],
            }
    except Exception as exc:
        logger.warning("Sample summary skipped in report: %s", exc)
    return summary


def _safe_pdf_export(html_path: Path, pdf_path: Path) -> tuple[bool, str | None]:
    try:
        from weasyprint import HTML
    except Exception:
        return False, "PDF export requires the optional dependency 'weasyprint'."

    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return True, None


def generate_report(state, body: dict):
    from flora.diversity.alpha import compute_alpha_diversity
    from flora.feature_engineering.reduction import compute_pcoa
    from flora.reports.html_report import FLORAReport
    from flora.ui.analytics import build_beta_heatmap, build_taxonomy_heatmap
    from flora.ui.query_helpers import fetch_sample_taxonomy_profile
    from flora.viz.diversity_plots import plot_alpha_diversity, plot_pcoa
    from flora.viz.taxonomy_plots import plot_taxonomy_barplot

    title = body.get("title", "FLORA Analysis Report")
    output_path = Path(body.get("output_path", str(state.workdir / "report.html")))
    output_format = body.get("output_format", "html")
    group_by = body.get("group_by", "biome")
    include_pdf = output_format in {"pdf", "both"}
    pdf_path = Path(body.get("pdf_path", output_path.with_suffix(".pdf")))
    warnings: list[str] = []

    report = FLORAReport(title=title)
    report.set_summary(
        "FLORA keeps the HTML report as the editable source of truth. The same artifact can be previewed in-browser and printed or exported to PDF for submission workflows.",
        notes=[
            "HTML is the canonical editable format for analytical reports.",
            "PDF should be treated as a publication/export artifact.",
            "Each section below is generated from the current database state.",
        ],
    )

    try:
        tables = _count_tables(state)
        report.add_metrics("Dataset Summary", tables)
        sample_summary = _sample_summary(state)
        if sample_summary:
            report.add_metrics("Sample Overview", sample_summary)
        checklist = pl.DataFrame(build_publication_checklist(tables))
        report.add_table("Publication Checklist", checklist)
    except Exception as exc:
        logger.warning("Dataset summary skipped in report: %s", exc)

    try:
        feature_matrix = state.pipeline.get_feature_matrix(normalize=None)
        alpha = compute_alpha_diversity(
            feature_matrix,
            metrics=["shannon", "observed_features", "chao1", "simpson"],
        )
        report.add_table("Alpha Diversity", alpha)
        if len(alpha) > 1:
            metadata = state.db.query("SELECT * FROM samples").to_polars()
            if group_by and group_by in metadata.columns:
                alpha_plot_df = alpha.join(
                    metadata.select(["sample_id", group_by]),
                    on="sample_id",
                    how="left",
                )
                alpha_fig = plot_alpha_diversity(alpha_plot_df, metric="shannon", group_by=group_by)
                report.add_plot("Alpha Diversity Distribution", alpha_fig)
    except Exception as exc:
        warnings.append(f"Alpha diversity skipped: {exc}")
        logger.warning("Alpha diversity skipped in report: %s", exc)

    try:
        agg = state.db.aggregate_by_taxon(level="phylum", group_by=group_by)
        fig = plot_taxonomy_barplot(agg, level="phylum", group_by=group_by)
        report.add_plot("Taxonomic Composition", fig)
        sample_taxa = fetch_sample_taxonomy_profile(state.db, "genus")
        heatmap = build_taxonomy_heatmap(sample_taxa, level="genus", top_n=25)
        report.add_plot("Genus Heatmap", heatmap)
    except Exception as exc:
        warnings.append(f"Taxonomy section skipped: {exc}")
        logger.warning("Taxonomy plot skipped in report: %s", exc)

    try:
        feature_matrix = state.pipeline.get_feature_matrix(normalize="tss")
        if len(feature_matrix) >= 2:
            pcoa_long = compute_pcoa(feature_matrix, metric="braycurtis", n_components=3)
            metadata = state.db.query("SELECT * FROM samples").to_polars()
            pcoa_fig = plot_pcoa(
                pcoa_long,
                metadata_df=metadata if group_by else None,
                color_by=group_by,
            )
            report.add_plot("PCoA Structure", pcoa_fig)
            from flora.diversity.beta import compute_beta_diversity

            beta_df = compute_beta_diversity(feature_matrix.head(60), metric="bray_curtis")
            beta_fig = build_beta_heatmap(beta_df, metric="bray_curtis")
            report.add_plot("Beta Diversity Heatmap", beta_fig)
        else:
            warnings.append("PCoA and beta diversity require at least 2 samples.")
    except Exception as exc:
        warnings.append(f"Ordination section skipped: {exc}")
        logger.warning("Ordination section skipped in report: %s", exc)

    notes = [
        "Recommended workflow: edit and review the HTML report first, then export to PDF when the narrative is finalized.",
        f"Preview endpoint: {_report_preview_url(output_path)}",
    ]
    if warnings:
        notes.extend(warnings)
    report.add_text("Reporting Notes", "\n".join(notes))

    try:
        saved = report.save(output_path)
        pdf_saved = None
        pdf_warning = None
        if include_pdf:
            ok, pdf_warning = _safe_pdf_export(saved, pdf_path)
            if ok:
                pdf_saved = str(pdf_path)
            elif pdf_warning:
                warnings.append(pdf_warning)

        return json_success(
            data={
                "report_path": str(saved),
                "report_preview_url": _report_preview_url(saved),
                "pdf_path": pdf_saved,
                "warnings": warnings,
                "sections": len(report._sections),
            }
        )
    except Exception as exc:
        if isinstance(exc, (DatabaseError, PipelineError, ValidationError, ValueError, FileNotFoundError)):
            raise UiHttpError(str(exc), status=400, code="report_generation_failed") from exc
        raise UiHttpError(str(exc), status=500, code="internal_error") from exc


def preview_report(_state, params: dict):
    path_value = params.get("path", [""])[0]
    if not path_value:
        raise UiHttpError("path is required", code="missing_path")

    path = Path(path_value)
    if not path.exists():
        raise UiHttpError(f"Report file not found: {path}", status=404, code="report_not_found")
    if path.suffix.lower() != ".html":
        raise UiHttpError("Preview only supports HTML reports.", status=400, code="unsupported_format")

    return path.read_text(encoding="utf-8")
