"""Custom exception hierarchy for the FLORA library.

All exceptions derive from FloraError, enabling callers to catch the entire
library's error surface with a single except clause when needed.
"""

from __future__ import annotations


class FloraError(Exception):
    """Base exception for all FLORA library errors.

    Parameters
    ----------
    message : str
        Human-readable description of the error.
    context : dict, optional
        Additional diagnostic context (file paths, parameter values, etc.).
    """

    def __init__(self, message: str, context: dict | None = None) -> None:
        self.message = message
        self.context = context or {}
        super().__init__(self._format())

    def _format(self) -> str:
        if not self.context:
            return self.message
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{self.message} [{ctx}]"


class PipelineError(FloraError):
    """Raised when a pipeline step fails or produces invalid output.

    Parameters
    ----------
    message : str
        Description of what failed.
    step : str, optional
        Name of the pipeline step that failed.
    context : dict, optional
        Additional diagnostic context.
    """

    def __init__(self, message: str, step: str | None = None, context: dict | None = None) -> None:
        ctx = context or {}
        if step:
            ctx["step"] = step
        super().__init__(message, ctx)
        self.step = step


class ValidationError(FloraError):
    """Raised when input data fails schema or format validation.

    Parameters
    ----------
    message : str
        Description of the validation failure.
    field : str, optional
        Name of the field or column that failed validation.
    context : dict, optional
        Additional diagnostic context.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if field:
            ctx["field"] = field
        super().__init__(message, ctx)
        self.field = field


class DatabaseError(FloraError):
    """Raised when a DuckDB operation fails.

    Parameters
    ----------
    message : str
        Description of the database error.
    query : str, optional
        The SQL query that caused the error (truncated if long).
    context : dict, optional
        Additional diagnostic context.
    """

    def __init__(
        self,
        message: str,
        query: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if query:
            ctx["query"] = query[:200] + "..." if len(query) > 200 else query
        super().__init__(message, ctx)
        self.query = query


class IngestionError(FloraError):
    """Raised when data ingestion from an external source fails.

    Parameters
    ----------
    message : str
        Description of the ingestion failure.
    source : str, optional
        Source identifier (URL, file path, accession).
    context : dict, optional
        Additional diagnostic context.
    """

    def __init__(
        self,
        message: str,
        source: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if source:
            ctx["source"] = source
        super().__init__(message, ctx)
        self.source = source


class MLError(FloraError):
    """Raised when a machine learning operation fails.

    Parameters
    ----------
    message : str
        Description of the ML error.
    model : str, optional
        Model identifier or type.
    context : dict, optional
        Additional diagnostic context.
    """

    def __init__(
        self,
        message: str,
        model: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if model:
            ctx["model"] = model
        super().__init__(message, ctx)
        self.model = model
