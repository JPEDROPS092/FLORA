"""Ingestion and matrix-related UI handlers."""

from __future__ import annotations

from flora.core.exceptions import PipelineError, ValidationError
from flora.ui.http import UiHttpError, json_success


def _friendly(text: str) -> str:
    """Turn a library exception into a short Portuguese message the pipeline can show as-is."""
    lowered = text.lower()
    if "no such file" in lowered or "file not found" in lowered or "not found:" in lowered:
        return f"Arquivo não encontrado. Confira o caminho e se o servidor do FLORA consegue lê-lo. ({text})"
    if "missing required columns" in lowered or "não foi possível ler a tabela asv" in lowered or "tabela asv longa precisa" in lowered:
        if text.startswith("A tabela") or text.startswith("Não foi possível"):
            return text
        return (
            "A tabela ASV não tem as colunas de formato longo (sample_id, feature_id, abundance). "
            "Se as amostras estão nas linhas e as features nas colunas, o FLORA detecta isso pelo cabeçalho — "
            "confira se a primeira linha é o cabeçalho e se o separador é tabulação."
        )
    if "failed to read" in lowered or "could not parse" in lowered:
        return "Não foi possível ler o arquivo. Use TSV ou CSV com cabeçalho na primeira linha. Detalhe: " + text
    if "no samples have depth" in lowered:
        return (
            "A profundidade pedida é maior do que a de todas as amostras. "
            "Deixe o campo em branco para o FLORA usar a menor profundidade do estudo, "
            f"ou escolha um valor até o máximo observado. Detalhe: {text}"
        )
    return text


def _as_http_error(exc: Exception, *, code: str) -> UiHttpError:
    if isinstance(exc, UiHttpError):
        return exc
    text = str(exc)
    if "Duplicate key" in text:
        key = text.split('Duplicate key "', 1)[-1].split('"', 1)[0]
        return UiHttpError(
            f"Estes dados já estão no projeto (chave repetida: {key}). Use a ingestão com substituição "
            "(Pipeline → Confirmar) ou crie um projeto novo para um estudo diferente.",
            status=409,
            code="already_ingested",
            details={"key": key},
        )
    if isinstance(exc, FileNotFoundError) or "not found" in text.lower():
        return UiHttpError(_friendly(text), status=400, code="missing_file")
    if isinstance(exc, (PipelineError, ValidationError, ValueError)):
        return UiHttpError(_friendly(text), status=400, code=code)
    return UiHttpError(
        "A etapa falhou. Confira os arquivos e tente de novo. Se o problema continuar, o detalhe técnico é: " + text,
        status=500,
        code="internal_error",
    )


def ingest_metadata(state, body: dict):
    from flora.ui.project_progress import record_project_step

    path = body.get("path", "")
    if not path:
        raise UiHttpError("Informe o caminho do arquivo de metadata (path).", code="missing_path")
    sample_col = body.get("sample_col", "sample_id")
    try:
        count = state.pipeline.ingest_metadata(path, sample_col=sample_col)
        stage = record_project_step(state, "ingest_metadata", f"{count} amostras")
        return json_success(data={"samples_ingested": count, "project_stage": stage})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_metadata_failed") from exc


def ingest_asv(state, body: dict):
    from flora.ui.project_progress import record_project_step

    path = body.get("path", "")
    if not path:
        raise UiHttpError("Informe o caminho da tabela ASV (path).", code="missing_path")
    wide = body.get("wide_format", None)
    if wide is not None:
        wide = bool(wide)
    try:
        count = state.pipeline.ingest_asv_table(path, wide_format=wide)
        stage = record_project_step(state, "ingest_asv", f"{count} observações")
        return json_success(data={"observations_ingested": count, "project_stage": stage})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_asv_failed") from exc


def ingest_taxonomy(state, body: dict):
    from flora.ui.project_progress import record_project_step

    path = body.get("path", "")
    if not path:
        raise UiHttpError("Informe o caminho da taxonomia (path).", code="missing_path")
    try:
        count = state.pipeline.ingest_taxonomy(path)
        stage = record_project_step(state, "ingest_taxonomy", f"{count} táxons")
        return json_success(data={"taxonomy_rows": count, "project_stage": stage})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_taxonomy_failed") from exc


def compute_diversity(state, body: dict):
    from flora.ui.project_progress import record_project_step
    from flora.ui.reads import plan_sampling_depth

    metrics = body.get("metrics", ["shannon", "observed_features", "chao1"])
    raw_depth = body.get("sampling_depth")
    try:
        plan = plan_sampling_depth(state.db, int(raw_depth) if raw_depth else None)
        result = state.pipeline.compute_diversity(sampling_depth=plan["sampling_depth"], metrics=metrics)
        stage = record_project_step(state, "diversity", f"profundidade {plan['sampling_depth']}, {plan['dropped_count']} amostras abaixo")
        return json_success(
            data={
                "metrics": metrics,
                "samples": len(result),
                "preview": result.head(5).to_pandas().to_dict(orient="records"),
                "project_stage": stage,
                **plan,
            }
        )
    except Exception as exc:
        raise _as_http_error(exc, code="compute_diversity_failed") from exc


def clear_dataset(state, body: dict):
    """Delete the active project's tables. Requires ``confirm: true``."""
    from flora.ui.project_progress import record_project_step

    if body.get("confirm") is not True:
        return json_success(data={
            "applied": False,
            "message": "Nada foi apagado. Envie confirm=true para limpar metadata, ASV, taxonomia e diversidade deste projeto.",
        })
    try:
        removed = state.pipeline.clear_dataset()
    except Exception as exc:
        raise _as_http_error(exc, code="clear_failed") from exc
    stage = record_project_step(state, "clear", "dados do projeto apagados")
    return json_success(data={"applied": True, "removed": removed, "project_stage": stage})


def get_feature_matrix(state, params: dict):
    normalize = params.get("normalize", ["clr"])[0]
    min_prev = float(params.get("min_prevalence", ["0.05"])[0])
    try:
        matrix = state.pipeline.get_feature_matrix(
            normalize=normalize if normalize != "none" else None,
            min_prevalence=min_prev,
        )
        return json_success(
            data={
                "n_samples": len(matrix),
                "n_features": len(matrix.columns) - 1,
                "normalize": normalize,
                "preview": matrix.head(3).to_pandas().to_dict(orient="records"),
            }
        )
    except Exception as exc:
        raise _as_http_error(exc, code="feature_matrix_failed") from exc


def ingest_dataset(state, body: dict):
    """Load metadata, ASV table and taxonomy together, replacing the project's dataset, all or nothing.

    The previous dataset is copied first; if any step fails the partial load is removed and the copy is put back,
    so a failed ingestion never leaves the project half-overwritten.
    (A SQL transaction cannot do this: DuckDB rejects deleting and re-inserting the same key in one transaction.)
    """
    from flora.ui.project_progress import record_project_step

    paths = {k: str(body.get(k) or "") for k in ("metadata_path", "asv_path", "taxonomy_path")}
    missing = [k for k, v in paths.items() if not v]
    if missing:
        raise UiHttpError(f"Informe {', '.join(missing)}.", code="missing_path")
    replace = body.get("replace", True) is not False
    wide = None if "wide_format" not in body else bool(body.get("wide_format"))
    pipe = state.pipeline
    snapshot = pipe.snapshot_dataset() if replace else None
    steps: list[dict] = []
    current = "metadata"
    removed: dict[str, int] = {}
    try:
        if replace:
            removed = pipe.clear_dataset()
        n = pipe.ingest_metadata(paths["metadata_path"], sample_col=body.get("sample_col", "sample_id"))
        steps.append({"step": "metadata", "success": True, "detail": f"{n} registros"})
        current = "asv"
        n = pipe.ingest_asv_table(paths["asv_path"], wide_format=wide)
        steps.append({"step": "asv", "success": True, "detail": f"{n} registros"})
        current = "taxonomy"
        n = pipe.ingest_taxonomy(paths["taxonomy_path"])
        steps.append({"step": "taxonomy", "success": True, "detail": f"{n} registros"})
    except Exception as exc:
        if snapshot is not None:
            pipe.restore_dataset(snapshot)
        err = _as_http_error(exc, code=f"ingest_{current}_failed")
        note = " Os dados anteriores foram mantidos." if snapshot is not None else " Nada ficou gravado pela metade."
        raise UiHttpError(f"{current}: {err.message}{note}", status=err.status, code=err.code, details={"step": current}) from exc
    stage = record_project_step(state, "ingest", steps[-1]["detail"])
    return json_success(data={"steps": steps, "replaced": {"samples": removed.get("samples", 0)} if replace else {}, "project_stage": stage})
