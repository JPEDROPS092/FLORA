"""Ingestion and matrix-related UI handlers."""

from __future__ import annotations

from flora.core.exceptions import PipelineError, ValidationError
from flora.ui.http import UiHttpError, json_success


def _as_http_error(exc: Exception, *, code: str) -> UiHttpError:
    if isinstance(exc, UiHttpError):
        return exc
    if "Duplicate key" in str(exc):
        key = str(exc).split('Duplicate key "', 1)[-1].split('"', 1)[0]
        return UiHttpError(
            f"Estes dados já estão no projeto (chave repetida: {key}). Use a ingestão com substituição "
            "(Pipeline → Confirmar) ou crie um projeto novo para um estudo diferente.",
            status=409,
            code="already_ingested",
            details={"key": key},
        )
    if isinstance(exc, FileNotFoundError):
        return UiHttpError(str(exc), status=400, code="missing_file")
    if isinstance(exc, (PipelineError, ValidationError, ValueError)):
        return UiHttpError(str(exc), status=400, code=code)
    return UiHttpError(str(exc), status=500, code="internal_error")


def ingest_metadata(state, body: dict):
    path = body.get("path", "")
    if not path:
        raise UiHttpError("path is required", code="missing_path")
    sample_col = body.get("sample_col", "sample_id")
    try:
        count = state.pipeline.ingest_metadata(path, sample_col=sample_col)
        return json_success(data={"samples_ingested": count})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_metadata_failed") from exc


def ingest_asv(state, body: dict):
    path = body.get("path", "")
    if not path:
        raise UiHttpError("path is required", code="missing_path")
    wide = body.get("wide_format", False)
    try:
        count = state.pipeline.ingest_asv_table(path, wide_format=wide)
        return json_success(data={"observations_ingested": count})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_asv_failed") from exc


def ingest_taxonomy(state, body: dict):
    path = body.get("path", "")
    if not path:
        raise UiHttpError("path is required", code="missing_path")
    try:
        count = state.pipeline.ingest_taxonomy(path)
        return json_success(data={"taxonomy_rows": count})
    except Exception as exc:
        raise _as_http_error(exc, code="ingest_taxonomy_failed") from exc


def compute_diversity(state, body: dict):
    depth = body.get("sampling_depth")
    metrics = body.get("metrics", ["shannon", "observed_features", "chao1"])
    try:
        result = state.pipeline.compute_diversity(
            sampling_depth=int(depth) if depth else None,
            metrics=metrics,
        )
        return json_success(
            data={
                "metrics": metrics,
                "samples": len(result),
                "preview": result.head(5).to_pandas().to_dict(orient="records"),
            }
        )
    except Exception as exc:
        raise _as_http_error(exc, code="compute_diversity_failed") from exc


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
    paths = {k: str(body.get(k) or "") for k in ("metadata_path", "asv_path", "taxonomy_path")}
    missing = [k for k, v in paths.items() if not v]
    if missing:
        raise UiHttpError(f"Informe {', '.join(missing)}.", code="missing_path")
    replace = body.get("replace", True) is not False
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
        n = pipe.ingest_asv_table(paths["asv_path"], wide_format=bool(body.get("wide_format", True)))
        steps.append({"step": "asv", "success": True, "detail": f"{n} registros"})
        current = "taxonomy"
        n = pipe.ingest_taxonomy(paths["taxonomy_path"])
        steps.append({"step": "taxonomy", "success": True, "detail": f"{n} registros"})
    except Exception as exc:
        if snapshot is not None:
            pipe.restore_dataset(snapshot)
        err = _as_http_error(exc, code=f"ingest_{current}_failed")
        note = " (os dados anteriores foram mantidos)" if snapshot is not None else ""
        raise UiHttpError(f"{current}: {err.message}{note}", status=err.status, code=err.code, details={"step": current}) from exc
    return json_success(data={"steps": steps, "replaced": {"samples": removed.get("samples", 0)} if replace else {}})
