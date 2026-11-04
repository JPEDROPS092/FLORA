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


def _resolve_output(state, value: str | None, default_name: str) -> Path:
    """Relative paths land in ``<project>/reports`` so reports follow the active project."""
    base = Path(state.data_dir) / "reports"
    if not value:
        return base / default_name
    path = Path(value)
    return path if path.is_absolute() else base / path.name


def _figure(spec: dict):
    import plotly.graph_objects as go

    return go.Figure(data=spec.get("data") or [], layout=spec.get("layout") or {})


def _append_study_sections(state, report, group_by: str, warnings: list[str]) -> None:
    """QC, rarefaction, tests, taxonomy database and package versions. Failures become notes, not a broken report."""
    import polars as pl

    from flora.ui.handlers import analysis
    from flora.ui.http import UiHttpError
    from flora.ui.provenance import build_provenance
    from flora.ui.reads import plan_sampling_depth

    def params(**items: str) -> dict[str, list[str]]:
        return {key: [value] for key, value in items.items() if value != ""}

    depth_plan: dict | None = None
    try:
        stored = None
        try:
            frame = state.db.query("SELECT MAX(sampling_depth) FROM diversity_alpha").to_polars()
            if frame.height and frame.row(0)[0] is not None:
                stored = int(frame.row(0)[0])
        except Exception:  # noqa: BLE001
            stored = None
        depth_plan = plan_sampling_depth(state.db, stored)
        report.add_metrics("Rarefação", {
            "Profundidade escolhida": depth_plan["sampling_depth"],
            "Origem": "já calculada" if stored else "mínimo das amostras",
            "Amostras mantidas": depth_plan["retained"],
            "Amostras descartadas": depth_plan["dropped_count"],
            "Mínimo de reads": depth_plan["reads"]["min"],
            "Mediana de reads": depth_plan["reads"]["median"],
            "Máximo de reads": depth_plan["reads"]["max"],
            "Sugestão (percentil 95%)": depth_plan["percentile_depth"],
        }, section_id="rarefaction_depth")
        if depth_plan["dropped_count"]:
            names = ", ".join(depth_plan["dropped_samples"])
            extra = "" if depth_plan["dropped_count"] <= len(depth_plan["dropped_samples"]) else " …"
            report.add_text("Amostras abaixo da profundidade", names + extra, section_id="dropped_samples")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Rarefação omitida: {exc}")

    try:
        qc = analysis.get_qc(state, {})
        summary = qc["summary"]
        report.add_metrics("Controle de qualidade", {
            "Amostras": summary["samples"],
            "Abaixo do corte": summary["below_depth"],
            "Corte (reads)": summary["min_reads"],
            "Features organelares": summary["organelle_features"],
            "% reads organelares": summary["organelle_reads_pct"],
        }, section_id="qc_summary")
        if qc["samples"]:
            report.add_table("QC por amostra", pl.DataFrame(qc["samples"]), max_rows=80, section_id="qc_samples")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"QC omitido: {exc}")

    try:
        depth = str(depth_plan["sampling_depth"]) if depth_plan else "0"
        rare = analysis.get_rarefaction(state, params(group_by=group_by, depth=depth))
        report.add_plot("Curvas de rarefação", _figure(rare["plot"]), section_id="rarefaction_curves")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Curvas de rarefação omitidas: {exc}")

    try:
        alpha = analysis.get_alpha_stats(state, params(group_by=group_by))
        if alpha.get("caution"):
            report.add_text("Aviso antes dos testes", "\n".join(alpha["caution"]), section_id="stats_caution")
        rows = [{"métrica": row["metric"], "H": round(row["h"], 3), "p": row["p"], "q (FDR)": row.get("q")} for row in alpha["tests"]]
        if rows:
            report.add_table("Kruskal-Wallis com FDR", pl.DataFrame(rows), section_id="kruskal")
        elif alpha.get("notes"):
            report.add_text("Kruskal-Wallis", "\n".join(alpha["notes"]), section_id="kruskal")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Kruskal-Wallis omitido: {exc}")

    try:
        beta = analysis.get_beta_stats(state, params(group_by=group_by, metric="bray_curtis", permutations="199"))
        perm, disp = beta["permanova"], beta["permdisp"]
        report.add_metrics("PERMANOVA e PERMDISP", {
            "Distância": beta["metric"],
            "PERMANOVA F": round(perm["f"], 3),
            "PERMANOVA R²": round(perm["r2"], 3),
            "PERMANOVA p": perm["p"],
            "PERMDISP F": round(disp["f"], 3),
            "PERMDISP p": disp["p"],
            "Permutações": perm.get("permutations", 199),
        }, section_id="permanova")
        if beta.get("notes"):
            report.add_text("Notas de beta-diversidade", "\n".join(beta["notes"]), section_id="permanova_notes")
        report.add_plot("Ordenação dos grupos (PERMANOVA)", _figure(beta["plot"]), section_id="permanova_plot")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"PERMANOVA omitida: {exc}")

    levels: list[str] = []
    if group_by and group_by.replace("_", "").isalnum() and group_by[0].isalpha():
        try:
            levels = sorted({
                str(row[0]) for row in state.db.query(
                    f'SELECT DISTINCT CAST("{group_by}" AS VARCHAR) FROM samples WHERE "{group_by}" IS NOT NULL AND CAST("{group_by}" AS VARCHAR) <> \'\''
                ).to_polars().iter_rows()
            })
        except Exception:  # noqa: BLE001 - a missing column just skips the contrast note
            levels = []
    try:
        query = params(group_by=group_by, rank="genus")
        if len(levels) >= 2:
            query["a"] = [levels[0]]
            query["b"] = [levels[1]]
        volcano = analysis.get_volcano(state, query)
        if len(levels) > 2:
            report.add_text(
                "Contraste do volcano",
                f"Há {len(levels)} grupos ({', '.join(levels)}). O gráfico compara apenas {volcano['a']} e {volcano['b']}.",
                section_id="volcano_contrast",
            )
        hits = [row for row in volcano["results"] if row.get("significant")][:30]
        shown = hits or volcano["results"][:30]
        if shown:
            report.add_table(
                "Abundância diferencial",
                pl.DataFrame([{k: row[k] for k in ("taxon", "log2fc", "p", "q", "significant")} for row in shown]),
                section_id="differential",
            )
        report.add_plot(f"Volcano ({volcano['b']} vs {volcano['a']})", _figure(volcano["plot"]), section_id="volcano")
    except UiHttpError as exc:
        warnings.append(exc.message)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Volcano omitido: {exc}")

    settings = analysis.read_settings(state.db)
    depth_label = str(depth_plan["sampling_depth"]) if depth_plan else "não calculada"
    provenance = build_provenance(state, parameters=[
        {"label": "Agrupamento", "value": group_by},
        {"label": "Profundidade de rarefação", "value": depth_label},
        {"label": "Corte de QC (reads)", "value": str(settings.get("min_reads") or depth_label)},
        {"label": "Distância", "value": "bray_curtis"},
        {"label": "Permutações", "value": "199"},
        {"label": "Rank do volcano", "value": "genus"},
    ])
    report.add_metrics("Banco taxonômico", {
        "Banco": settings.get("taxonomy_db") or "não informado",
        "Versão registrada": settings.get("taxonomy_db") or "não informada",
    }, section_id="taxonomy_db")
    packages = provenance.get("packages") or []
    if packages:
        report.add_table("Versões dos pacotes", pl.DataFrame(packages), section_id="package_versions")
    report.add_table(
        "Parâmetros",
        pl.DataFrame(provenance.get("parameters") or []),
        section_id="parameters",
    )
    report.add_text(
        "Ferramentas",
        provenance.get("pipeline_version", "") + "\nPlotly é carregado uma vez pelo CDN (o HTML não embute a biblioteca).",
        section_id="tool_versions",
    )


def generate_report(state, body: dict):
    from flora.diversity.alpha import compute_alpha_diversity
    from flora.feature_engineering.reduction import compute_pcoa
    from flora.reports.html_report import FLORAReport
    from flora.ui.analytics import build_beta_heatmap, build_taxonomy_heatmap
    from flora.ui.query_helpers import fetch_sample_taxonomy_profile
    from flora.viz.diversity_plots import plot_alpha_diversity, plot_pcoa
    from flora.viz.taxonomy_plots import plot_taxonomy_barplot

    title = body.get("title", "FLORA Analysis Report")
    output_path = _resolve_output(state, body.get("output_path"), "report.html")
    output_format = body.get("output_format", "html")
    from flora.ui.handlers.explore import default_group

    group_by = body.get("group_by") or default_group(state.db)
    include_pdf = output_format in {"pdf", "both"}
    pdf_path = _resolve_output(state, body.get("pdf_path"), output_path.with_suffix(".pdf").name)
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

    _append_study_sections(state, report, group_by, warnings)

    notes = [
        "Recommended workflow: edit and review the HTML report first, then export to PDF when the narrative is finalized.",
        "Os gráficos usam Plotly carregado uma vez pelo CDN, para o HTML não embutir a biblioteca.",
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

        from flora.ui.project_progress import record_project_step

        stage = record_project_step(state, "report", saved.name)
        return json_success(
            data={
                "report_path": str(saved),
                "report_preview_url": _report_preview_url(saved),
                "pdf_path": pdf_saved,
                "warnings": warnings,
                "sections": len(report._sections),
                "project_stage": stage,
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
    root = Path(_state.workdir).resolve() if _state is not None else None
    if root is not None and not path.resolve().is_relative_to(root):
        raise UiHttpError("Reports can only be previewed from the workspace.", status=403, code="forbidden_path")
    if not path.exists():
        raise UiHttpError(f"Report file not found: {path}", status=404, code="report_not_found")
    if path.suffix.lower() != ".html":
        raise UiHttpError("Preview only supports HTML reports.", status=400, code="unsupported_format")

    return path.read_text(encoding="utf-8")


def report_draft(state, params: dict | None = None):
    """Editable report skeleton: prose is derived from real numbers, figures from the project's data."""
    import json

    from flora.ui.handlers.workspace import _groups_frame, _table_counts
    from flora.ui.i18n import lang_of, tr
    from flora.ui.provenance import build_provenance

    lang = lang_of(params)
    from flora.ui.handlers.explore import default_group

    group_by = ((params or {}).get("group_by") or [""])[0] or default_group(state.db)
    active = state.projects.active_id()
    project = state.projects.get(active) if active else None
    name = project.name if project else "workspace"
    counts = _table_counts(state.db)
    groups = sorted({g for g in _groups_frame(state.db, group_by)["group"].to_list() if g})

    figures: dict = {}

    def fig(key: str, build):
        try:
            figures[key] = json.loads(build().to_json())
        except Exception as exc:  # noqa: BLE001 - a missing figure must not block the draft
            logger.info("Report figure %s skipped: %s", key, exc)

    from flora.diversity.alpha import compute_alpha_diversity
    from flora.feature_engineering.reduction import compute_pcoa
    from flora.diversity.beta import compute_beta_diversity
    from flora.ui.analytics import build_beta_heatmap
    from flora.viz.diversity_plots import plot_alpha_diversity, plot_pcoa
    from flora.viz.taxonomy_plots import plot_taxonomy_barplot

    metadata = None
    comparisons: list[list[str]] = []
    try:
        metadata = state.db.query("SELECT * FROM samples").to_polars()
        raw = state.pipeline.get_feature_matrix(normalize=None)
        alpha = compute_alpha_diversity(raw, metrics=["shannon", "observed_features"])
        grouped = alpha.join(_groups_frame(state.db, group_by).rename({"group": group_by}), on="sample_id", how="left")
        fig("alpha", lambda: plot_alpha_diversity(grouped, metric="shannon", group_by=group_by))
        stats = grouped.group_by(group_by).agg(
            pl.len().alias("n"), pl.col("shannon").mean().alias("m"), pl.col("shannon").std().alias("sd"), pl.col("observed_features").mean().alias("o")
        ).sort(group_by)
        comparisons = [[str(r[group_by]), str(r["n"]), f"{r['m']:.2f} ± {(r['sd'] or 0):.2f}", str(round(r["o"]))] for r in stats.iter_rows(named=True)]
    except Exception as exc:  # noqa: BLE001
        logger.info("Report alpha section skipped: %s", exc)
    try:
        tss = state.pipeline.get_feature_matrix(normalize="tss")
        if len(tss) >= 2:
            pcoa = compute_pcoa(tss, metric="braycurtis", n_components=3)
            gm = _groups_frame(state.db, group_by).rename({"group": group_by})
            fig("pcoa", lambda: plot_pcoa(pcoa, metadata_df=gm, color_by=group_by))
            fig("beta", lambda: build_beta_heatmap(compute_beta_diversity(tss.head(60), metric="bray_curtis"), metric="bray_curtis"))
    except Exception as exc:  # noqa: BLE001
        logger.info("Report ordination skipped: %s", exc)
    fig("taxonomy", lambda: plot_taxonomy_barplot(state.db.aggregate_by_taxon(level="phylum", group_by=group_by), level="phylum", group_by=group_by))

    experiments = [e for e in state.experiments.list() if e["status"] == "completed"]
    best = max(experiments, key=lambda e: e["f1_macro"], default=None)
    if best:
        for key, field in (("confusion", "confusion"), ("shap", "importance")):
            if best[field].get("figure"):
                figures[key] = best[field]["figure"]

    parameters = [
        {"label": tr(lang, "report.p.project"), "value": name},
        {"label": tr(lang, "report.p.samples"), "value": str(counts["samples"])},
        {"label": "ASVs", "value": str(counts["asvs"])},
        {"label": "Group by", "value": group_by},
    ]
    if best:
        parameters += best["config"]
    provenance = build_provenance(state, parameters=parameters)
    parameters = list(provenance["parameters"])  # includes the taxonomy database and the engine versions
    if provenance["inputs"]:
        parameters.append({"label": "Accessions", "value": ", ".join(provenance["inputs"])})
    parameters += [{"label": p["name"], "value": p["version"]} for p in provenance["packages"]]

    def section(key, figure, text, table=None):
        return {"id": key, "title": tr(lang, f"report.{key}"), "included": True, "figure": figure if figure in figures else None, "narrative": text, "table": table}

    sections = [
        section("summary", None, tr(lang, "report.summary_text", name=name, samples=counts["samples"], asvs=counts["asvs"], groups=len(groups), group_by=group_by),
                {"columns": [tr(lang, "report.col.group"), "n", "Shannon", tr(lang, "report.col.observed")], "rows": comparisons} if comparisons else None),
        section("methods", None, tr(lang, "report.methods_text")),
        section("alpha", "alpha", tr(lang, "report.alpha_text")),
        section("beta", "pcoa", tr(lang, "report.beta_text")),
        section("taxonomy", "taxonomy", tr(lang, "report.taxonomy_text")),
        section("ml", "confusion", tr(lang, "report.ml_text", model=best["model"], acc=f"{best['accuracy']:.2f}", f1=f"{best['f1_macro']:.2f}",
                                       auc=f"{best['roc_auc']:.2f}" if best["roc_auc"] is not None else "—") if best else tr(lang, "report.ml_none")),
        section("params", "shap", tr(lang, "report.params_text"),
                {"columns": [tr(lang, "report.col.param"), tr(lang, "report.col.value")], "rows": [[p["label"], p["value"]] for p in parameters]}),
    ]
    return json_success(data={
        "title": tr(lang, "report.title", name=name), "project_id": active or "workspace",
        "parameters": parameters, "figures": figures, "sections": sections,
    })
