"""Ingestion and matrix-related UI handlers."""

from __future__ import annotations

from flora.core.exceptions import PipelineError, ValidationError
from flora.ui.http import UiHttpError, json_success


def _as_http_error(exc: Exception, *, code: str) -> UiHttpError:
    if isinstance(exc, UiHttpError):
        return exc
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
