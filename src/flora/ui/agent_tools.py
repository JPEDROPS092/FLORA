"""Tools the LLM operator can call. Each one is a thin adapter over an existing handler.

The model chooses tools and arguments; **every number comes from the deterministic code behind the tool** (ADR 0002:
the LLM never computes results). A tool returns:

* ``summary`` - a compact dict the model reads (and quotes);
* ``artifacts`` - charts, tables, maps and navigation shown to the researcher (kept out of the model's context).

Tools with ``confirm=True`` change data or state (download, ingest, delete, switch project, report). They never run
without the researcher's approval in the UI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from flora.ui.http import UiHttpError

PAGES = {
    "dashboard": "/dashboard", "explorer": "/explorer", "pipeline": "/pipeline", "downloads": "/downloads", "projects": "/projects",
    "reports": "/reports", "ml": "/ml", "engines": "/engines", "settings": "/settings",
}
EXPLORER_VIEWS = ("pcoa", "alpha", "beta", "taxonomy", "relations", "data", "qc", "rarefaction", "stats")
_RANKS = ["phylum", "class", "order", "family", "genus"]
_ALPHA = ["shannon", "observed_features", "chao1", "simpson"]
_MAX_ROWS = 15


@dataclass
class ToolResult:
    summary: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict[str, dict[str, Any]]
    required: tuple[str, ...]
    run: Callable[[Any, dict[str, Any]], ToolResult]
    confirm: bool = False

    def spec(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties, "required": list(self.required)}}}


def _p(**kw: Any) -> dict[str, list[str]]:
    """Handler query params: ``{key: [value]}`` without the empty ones."""
    return {k: [str(v)] for k, v in kw.items() if v not in (None, "")}


def _plot(title: str, payload: dict[str, Any]) -> dict[str, Any]:
    fig = payload.get("plot") or {}
    return {"type": "plot", "title": title, "figure": {"data": fig.get("data", []), "layout": fig.get("layout", {})}}


def _table(title: str, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"type": "table", "title": title, "columns": columns, "rows": rows[:_MAX_ROWS], "total": len(rows)}


def _num(v: Any, digits: int = 4) -> Any:
    return round(v, digits) if isinstance(v, float) else v


# ---------------------------------------------------------------------------
# read-only
# ---------------------------------------------------------------------------
def _get_workspace(state, args):
    from flora.ui.handlers import explore, status

    schema = explore.get_schema(state)
    st = status.get_status(state)
    sources = []
    try:
        active = state.projects.active_id()
        sources = [{"type": x.type, "accession": x.accession} for x in state.projects.get(active).sources] if active else []
    except Exception:  # noqa: BLE001 - sources are context, never a failure
        pass
    return ToolResult({
        "project": schema.get("project"), "source_studies": sources, "database": st.get("db_path"), "persistent": st.get("db_persistent"),
        "counts": schema["counts"], "reads_per_sample": schema.get("reads"),
        "group_columns": [{"name": c["name"], "values": c["values"]} for c in schema["group_columns"]],
    })


def _list_projects(state, args):
    from flora.ui.handlers import projects

    out = projects.list_projects(state)
    rows = [{"id": p["id"], "name": p["name"], "stage": p.get("stage"), "samples": p.get("samples"), "asvs": p.get("asvs")} for p in out["projects"]]
    return ToolResult({"active": out["active"], "projects": rows},
                      [_table("Projetos", ["id", "nome", "estágio", "amostras", "ASVs"], [[r["id"], r["name"], r["stage"], r["samples"], r["asvs"]] for r in rows])])


def _list_datasets(state, args):
    from flora.ui.handlers import datasets

    items = datasets.list_datasets(state)["datasets"]
    rows = [{"id": d["id"], "name": d["label"], "ready": d["complete"], "samples": d["samples"], "origin": d["origin"],
             "missing": d["missing"], "raw_reads_only": d["raw_reads_only"]} for d in items]
    return ToolResult({"datasets": rows, "note": "Só datasets com ready=true podem ser ingeridos."},
                      [_table("Datasets baixados", ["id", "nome", "pronto", "amostras", "origem"], [[r["id"], r["name"], r["ready"], r["samples"], r["origin"]] for r in rows])])


def _search_catalog(state, args):
    from flora.ui.handlers import downloads

    out = downloads.library_catalog(state, _p(q=args.get("q"), biome=args.get("biome"), region=args.get("region"),
                                              seq_type=args.get("seq_type"), amazonia="1" if args.get("amazonia") else ""))
    rows = [{"source": s["source"], "accession": s["accession"], "title": s.get("title_pt") or s["title"], "samples": s.get("n_samples"),
             "biome": s.get("biome_label") or s.get("biome"), "local_state": s.get("local_state")} for s in out["studies"][:12]]
    return ToolResult({"total": out["count"], "shown": len(rows), "studies": rows},
                      [_table("Catálogo de estudos", ["fonte", "código", "título", "amostras", "bioma", "no disco"],
                              [[r["source"], r["accession"], r["title"], r["samples"], r["biome"], r["local_state"]] for r in rows])])


def _show_table(state, args):
    from flora.ui.handlers import explore

    out = explore.get_table(state, _p(name=args["table"], q=args.get("query"), limit=min(int(args.get("limit") or 10), _MAX_ROWS)))
    return ToolResult({"table": args["table"], "total": out["total"], "columns": out["columns"], "first_rows": out["rows"][:5]},
                      [_table(f"Tabela: {args['table']} ({out['total']} linhas)", out["columns"], out["rows"])])


def _run_qc(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_qc(state, _p(min_reads=args.get("min_reads", 1000)))
    worst = sorted(out["samples"], key=lambda r: r["reads"])[:8]
    return ToolResult({"summary": out["summary"], "lowest_depth_samples": [{"sample": r["sample_id"], "reads": r["reads"], "status": r["status"]} for r in worst]},
                      [_plot("Reads por amostra", out)])


def _plot_rarefaction(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_rarefaction(state, _p(group_by=args.get("group_by"), depth=args.get("depth")))
    sat = [r["saturation"] for r in out["samples"]]
    return ToolResult({"samples": len(sat), "saturation_min": _num(min(sat)) if sat else None, "saturation_median": _num(sorted(sat)[len(sat) // 2]) if sat else None,
                       "note": out["note"]}, [_plot("Curvas de rarefação", out)])


def _alpha_stats(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_alpha_stats(state, _p(group_by=args["group_by"]))
    tests = [{"metric": t["metric"], "H": _num(t["h"], 3), "p": _num(t["p"]), "q_fdr": _num(t["q"]), "epsilon2": _num(t["epsilon2"], 3),
              "group_medians": {g: _num(v["median"], 3) for g, v in t["groups"].items()}} for t in out["tests"]]
    return ToolResult({"group_by": args["group_by"], "tests": tests, "method": out["notes"][0] if out["notes"] else ""},
                      [_table("Diversidade alfa: Kruskal-Wallis", ["métrica", "H", "p", "q (FDR)", "ε²"], [[t["metric"], t["H"], t["p"], t["q_fdr"], t["epsilon2"]] for t in tests])])


def _beta_stats(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_beta_stats(state, _p(group_by=args["group_by"], metric=args.get("metric", "bray_curtis"), permutations=min(int(args.get("permutations") or 999), 999)))
    return ToolResult({"metric": out["metric"], "group_sizes": out["sizes"], "permanova": {k: _num(out["permanova"][k]) for k in ("f", "r2", "p", "permutations")},
                       "permdisp": {k: _num(out["permdisp"][k]) for k in ("f", "p")}, "notes": out["notes"]},
                      [_plot(f"PCoA ({out['metric']})", out)])


def _differential(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_volcano(state, _p(group_by=args["group_by"], rank=args.get("rank", "genus"), a=args.get("a"), b=args.get("b")))
    top = [{"taxon": r["taxon"], "log2fc": _num(r["log2fc"], 2), "q": _num(r["q"]), "significant": r["significant"]} for r in out["results"][:10]]
    return ToolResult({"contrast": f"{out['b']} vs {out['a']}", "n": {out["a"]: out["n_a"], out["b"]: out["n_b"]}, "rank": out["rank"],
                       "significant": sum(1 for r in out["results"] if r["significant"]), "top": top, "method": out["notes"][0]},
                      [_plot(f"Volcano: {out['b']} vs {out['a']}", out), _table("Táxons mais diferentes", ["táxon", "log2FC", "q"], [[r["taxon"], r["log2fc"], r["q"]] for r in top])])


def _plot_taxonomy(state, args):
    import polars as pl

    from flora.ui.handlers import viz

    level, group_by = args.get("level", "phylum"), args.get("group_by") or None
    payload = viz.viz_taxonomy(state, _p(level=level, group_by=group_by, top_n=args.get("top_n", 10)))
    agg = state.db.aggregate_by_taxon(level=level, group_by=group_by)
    top = agg.group_by(level).agg(pl.col("mean_abundance").sum().alias("t")).sort("t", descending=True).head(6)
    total = float(top["t"].sum()) or 1.0
    return ToolResult({"level": level, "group_by": group_by, "top_taxa_share_pct": {str(r[level]): round(float(r["t"]) / total * 100, 1) for r in top.iter_rows(named=True)}},
                      [_plot(f"Composição taxonômica ({level})", payload)])


def _plot_alpha(state, args):
    from flora.diversity.alpha import compute_alpha_diversity
    from flora.ui.handlers import viz
    from flora.ui.handlers.workspace import _groups_frame

    metric, group_by = args.get("metric", "shannon"), args.get("group_by") or None
    payload = viz.viz_alpha(state, _p(metric=metric, group_by=group_by))
    summary: dict[str, Any] = {"metric": metric, "group_by": group_by}
    if group_by:
        alpha = compute_alpha_diversity(state.db.pivot_asv(normalize=None), metrics=[metric]).join(_groups_frame(state.db, group_by), on="sample_id")
        med = alpha.group_by("group").agg(__import__("polars").col(metric).median().alias("m")).sort("group")
        summary["median_by_group"] = {str(r["group"]): _num(float(r["m"]), 3) for r in med.iter_rows(named=True)}
    return ToolResult(summary, [_plot(f"Diversidade alfa ({metric})", payload)])


def _plot_pcoa(state, args):
    from flora.ui.handlers import viz

    payload = viz.viz_pcoa(state, _p(color_by=args.get("color_by"), normalize=args.get("normalize", "clr")))
    return ToolResult({"color_by": args.get("color_by"), "normalize": args.get("normalize", "clr"), "note": "Ordenação por Bray-Curtis; veja beta_stats para o teste."},
                      [_plot("PCoA", payload)])


def _plot_beta_heatmap(state, args):
    from flora.ui.handlers import viz

    payload = viz.viz_beta_heatmap(state, _p(metric=args.get("metric", "bray_curtis"), normalize=args.get("normalize", "tss"), max_samples=60))
    return ToolResult({"metric": args.get("metric", "bray_curtis")}, [_plot("Matriz de distância beta", payload)])


def _show_map(state, args):
    """Map of the active project's samples; with ``source`` + ``accession`` it maps a downloaded library dataset instead."""
    from flora.ui.handlers import downloads, explore

    if args.get("source") and args.get("accession"):
        out = downloads.library_map(state, _p(source=args["source"], accession=args["accession"], group_by=args.get("group_by")))["map"]
        title = f"Mapa das amostras ({args['accession']})"
    else:
        out = explore.get_map(state, _p(group_by=args.get("group_by")))["map"]
        title = "Mapa das amostras do projeto"
    summary = {"available": out["available"], "reason": out["reason"], "mapped": out["mapped"], "total": out["total"], "color_by": out.get("group_column"), "groups": out["groups"][:6]}
    return ToolResult(summary, [{"type": "map", "title": title, "map": out}] if out["available"] else [])


def _mixs(state, args):
    from flora.ui.handlers import analysis

    out = analysis.get_mixs(state)
    return ToolResult({"required_present": out["required_present"], "required_total": out["required_total"],
                       "missing": [f["field"] for f in out["fields"] if not f["present"]]},
                      [_table("Metadados MIxS", ["campo", "nível", "coluna", "preenchido %"], [[f["field"], f["level"], f["column"] or "—", f["filled_pct"]] for f in out["fields"]])])


def _list_engines(state, args):
    from flora.engines import registry

    engines = registry.detect_all()
    return ToolResult({"engines": [{"id": e["id"], "available": e["available"], "version": e["version"]} for e in engines]})


def _open_page(state, args):
    page = args["page"]
    path = PAGES[page]
    query = {"view": args["view"]} if page == "explorer" and args.get("view") else {}
    return ToolResult({"opened": page, "view": query.get("view")}, [{"type": "navigate", "label": f"Abrir {page}", "path": path, "query": query}])


# ---------------------------------------------------------------------------
# confirmed (change data or state)
# ---------------------------------------------------------------------------
def _download_study(state, args):
    from flora.ui.handlers import downloads

    body = {"source": args["source"], "accession": args["accession"]}
    job = downloads.recorded(args["source"], downloads.library_download)(state, body)["job"]
    return ToolResult({"status": job["status"], "readiness": job.get("readiness"), "detail": job["detail"], "files": [a["label"] for a in job["artifacts"]],
                       "next": "Se readiness=ready, use ingest_dataset; se metadata_only, só há metadados (sem análise)."})


def _ingest_dataset(state, args):
    from flora.ui.handlers import datasets, ingest

    wanted = str(args["dataset_id"])
    items = {d["id"]: d for d in datasets.list_datasets(state)["datasets"]}
    item = items.get(wanted) or next((d for d in items.values() if d["label"] == wanted), None)
    if item is None:
        raise UiHttpError(f"Dataset '{wanted}' não encontrado. Use list_datasets.", code="not_found")
    if not item["complete"]:
        raise UiHttpError(f"O dataset '{item['label']}' está incompleto (faltam: {', '.join(item['missing'])}).", code="incomplete")
    out = ingest.ingest_dataset(state, {"metadata_path": item["files"]["metadata"], "asv_path": item["files"]["asv"], "taxonomy_path": item["files"]["taxonomy"], "replace": True})
    return ToolResult({"ingested": item["label"], "steps": out["steps"], "replaced_samples": out["replaced"].get("samples", 0), "project_stage": out.get("project_stage")})


def _activate_project(state, args):
    from flora.ui.handlers import projects

    out = projects.activate_project(state, {"id": args["project_id"]})
    return ToolResult({"active": out["project"]["name"], "stage": out["project"].get("stage")})


def _create_project(state, args):
    from flora.ui.handlers import projects

    out = projects.create_project(state, {"name": args["name"], "question": args.get("question", "")})
    return ToolResult({"created": out["project"]["name"], "id": out["project"]["id"], "note": "Use activate_project para trabalhar nele."})


def _apply_qc(state, args):
    from flora.ui.handlers import analysis

    out = analysis.apply_qc(state, {"remove_organelles": bool(args.get("remove_organelles")), "drop_low_depth": bool(args.get("drop_low_depth")),
                                    "min_reads": int(args.get("min_reads") or 0), "confirm": True})
    return ToolResult({"applied": out["applied"], **out["plan"]})


def _generate_report(state, args):
    from urllib.parse import quote

    from flora.ui.handlers import report

    out = report.generate_report(state, {"title": args.get("title", "Relatório FLORA"), "group_by": args.get("group_by", "biome")})
    path = out.get("output_path") or out.get("path") or ""
    artifacts = [{"type": "navigate", "label": "Abrir o relatório", "path": "/reports", "query": {}}]
    return ToolResult({"generated": True, "path": path, "warnings": out.get("warnings", []), "preview": f"/api/report/preview?path={quote(str(path))}" if path else ""}, artifacts)


def _tool(name, description, run, properties=None, required=(), confirm=False) -> Tool:
    return Tool(name, description, properties or {}, tuple(required), run, confirm)


_GROUP = {"type": "string", "description": "Coluna de metadata para agrupar (veja group_columns em get_workspace)."}
TOOLS: dict[str, Tool] = {t.name: t for t in (
    _tool("get_workspace", "Estado atual: projeto ativo, banco, contagens de amostras/ASVs, profundidade de reads e as colunas de agrupamento com seus valores. Chame primeiro.", _get_workspace),
    _tool("list_projects", "Lista os projetos e qual está ativo.", _list_projects),
    _tool("list_datasets", "Lista os datasets já baixados no disco (biblioteca local) e se estão prontos para ingerir.", _list_datasets),
    _tool("search_catalog", "Procura estudos públicos no catálogo (MGnify, ENA, EMP…) por texto, bioma, região ou tipo de sequenciamento.", _search_catalog,
          {"q": {"type": "string"}, "biome": {"type": "string"}, "region": {"type": "string"}, "seq_type": {"type": "string", "enum": ["amplicon", "shotgun", "misto"]}, "amazonia": {"type": "boolean"}}),
    _tool("show_table", "Mostra amostras, features (ASVs com taxonomia) ou taxonomia do dataset carregado.", _show_table,
          {"table": {"type": "string", "enum": ["samples", "features", "taxonomy"]}, "query": {"type": "string"}, "limit": {"type": "integer"}}, ("table",)),
    _tool("run_qc", "Controle de qualidade: reads por amostra, corte de profundidade e conteúdo de cloroplasto/mitocôndria.", _run_qc, {"min_reads": {"type": "integer"}}),
    _tool("plot_rarefaction", "Curvas de rarefação (riqueza esperada × reads).", _plot_rarefaction, {"group_by": _GROUP, "depth": {"type": "integer"}}),
    _tool("alpha_stats", "Teste Kruskal-Wallis da diversidade alfa entre grupos, com correção FDR.", _alpha_stats, {"group_by": _GROUP}, ("group_by",)),
    _tool("beta_stats", "PERMANOVA + PERMDISP da diversidade beta entre grupos, com PCoA.", _beta_stats,
          {"group_by": _GROUP, "metric": {"type": "string", "enum": ["bray_curtis", "jaccard", "aitchison", "unifrac", "weighted_unifrac"]}, "permutations": {"type": "integer"}}, ("group_by",)),
    _tool("differential_abundance", "Abundância diferencial entre dois grupos (volcano). Com mais de dois grupos na coluna, informe a e b (valores de group_columns).", _differential,
          {"group_by": _GROUP, "rank": {"type": "string", "enum": _RANKS}, "a": {"type": "string"}, "b": {"type": "string"}}, ("group_by",)),
    _tool("plot_taxonomy", "Gráfico de barras da composição taxonômica.", _plot_taxonomy,
          {"level": {"type": "string", "enum": _RANKS}, "group_by": _GROUP, "top_n": {"type": "integer"}}),
    _tool("plot_alpha", "Boxplot da diversidade alfa por grupo.", _plot_alpha, {"metric": {"type": "string", "enum": _ALPHA}, "group_by": _GROUP}),
    _tool("plot_pcoa", "PCoA (ordenação) colorida por uma coluna.", _plot_pcoa, {"color_by": _GROUP, "normalize": {"type": "string", "enum": ["clr", "tss", "none"]}}),
    _tool("plot_beta_heatmap", "Mapa de calor das distâncias entre amostras.", _plot_beta_heatmap, {"metric": {"type": "string", "enum": ["bray_curtis", "jaccard"]}, "normalize": {"type": "string", "enum": ["tss", "clr", "none"]}}),
    _tool("show_sample_map", "Mapa de onde as amostras foram coletadas (precisa de latitude/longitude). Sem argumentos mapeia o projeto ativo; NÃO invente source/accession.", _show_map,
          {"source": {"type": "string"}, "accession": {"type": "string"}, "group_by": _GROUP}),
    _tool("mixs_check", "Confere os metadados contra os campos MIxS.", _mixs),
    _tool("list_engines", "Quais ferramentas externas (QIIME 2, DADA2, R…) estão instaladas.", _list_engines),
    _tool("open_page", "Propõe abrir uma página do app (o usuário clica).", _open_page,
          {"page": {"type": "string", "enum": list(PAGES)}, "view": {"type": "string", "enum": list(EXPLORER_VIEWS), "description": "Só para explorer."}}, ("page",)),
    _tool("download_study", "Baixa um estudo do catálogo para o disco. Exige aprovação.", _download_study,
          {"source": {"type": "string"}, "accession": {"type": "string"}}, ("source", "accession"), confirm=True),
    _tool("ingest_dataset", "Carrega um dataset baixado no projeto ativo, SUBSTITUINDO os dados atuais. Exige aprovação.", _ingest_dataset,
          {"dataset_id": {"type": "string", "description": "id ou nome vindo de list_datasets"}}, ("dataset_id",), confirm=True),
    _tool("activate_project", "Troca o projeto ativo. Exige aprovação.", _activate_project, {"project_id": {"type": "string"}}, ("project_id",), confirm=True),
    _tool("create_project", "Cria um projeto vazio. Exige aprovação.", _create_project, {"name": {"type": "string"}, "question": {"type": "string"}}, ("name",), confirm=True),
    _tool("apply_qc", "Remove cloroplasto/mitocôndria e/ou amostras abaixo do corte (DESTRUTIVO). Exige aprovação.", _apply_qc,
          {"remove_organelles": {"type": "boolean"}, "drop_low_depth": {"type": "boolean"}, "min_reads": {"type": "integer"}}, confirm=True),
    _tool("generate_report", "Gera o relatório HTML com os resultados atuais. Exige aprovação.", _generate_report, {"title": {"type": "string"}, "group_by": _GROUP}, confirm=True),
)}


def validate_args(tool: Tool, args: Any) -> dict[str, Any]:
    """Check the model's arguments against the tool schema; coerce harmless type slips, reject the rest."""
    if not isinstance(args, dict):
        raise UiHttpError("Os argumentos da ferramenta devem ser um objeto JSON.", code="invalid_tool_args")
    clean: dict[str, Any] = {}
    for key, value in args.items():
        spec = tool.properties.get(key)
        if spec is None:
            continue  # unknown arguments are ignored, never forwarded
        kind = spec.get("type")
        try:
            if kind == "integer":
                value = int(value)
            elif kind == "boolean":
                value = value if isinstance(value, bool) else str(value).lower() in {"true", "1", "sim"}
            elif kind == "string":
                value = str(value)
        except (TypeError, ValueError) as exc:
            raise UiHttpError(f"Argumento '{key}' inválido (esperado {kind}).", code="invalid_tool_args") from exc
        if "enum" in spec and value not in spec["enum"]:
            raise UiHttpError(f"Argumento '{key}' deve ser um de: {', '.join(map(str, spec['enum']))}.", code="invalid_tool_args")
        clean[key] = value
    missing = [k for k in tool.required if k not in clean or clean[k] in ("", None)]
    if missing:
        raise UiHttpError(f"Faltam argumentos: {', '.join(missing)}.", code="invalid_tool_args")
    return clean


def execute(state, name: str, args: Any) -> tuple[ToolResult, dict[str, Any]]:
    """Run one tool. Returns the result and a trace entry (tool, ok, ms, detail)."""
    started = time.perf_counter()
    tool = TOOLS.get(name)
    if tool is None:
        err = f"Ferramenta desconhecida: {name}."
        return ToolResult({"error": err}), {"tool": name, "ok": False, "ms": 0, "detail": err}
    try:
        clean = validate_args(tool, args)
        result = tool.run(state, clean)
        ok, detail = True, ", ".join(f"{k}={v}" for k, v in clean.items())[:160]
    except UiHttpError as exc:
        result, ok, detail = ToolResult({"error": exc.message}), False, exc.message
    except Exception as exc:  # noqa: BLE001 - a tool failure goes back to the model, not to a 500
        result, ok, detail = ToolResult({"error": f"Falha inesperada: {exc}"}), False, f"Falha inesperada: {exc}"
    return result, {"tool": name, "ok": ok, "ms": int((time.perf_counter() - started) * 1000), "detail": detail}
