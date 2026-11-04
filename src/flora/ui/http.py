"""HTTP helpers for the FLORA UI server."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

logger = logging.getLogger("flora.ui.http")

#: base64 inflates uploads by ~4/3, so this admits files up to the 200 MB upload limit.
MAX_BODY_BYTES = 280 * 1024 * 1024


@dataclass(slots=True)
class UiHttpError(Exception):
    """HTTP-aware application error for UI handlers."""

    message: str
    status: int = 400
    code: str = "bad_request"
    details: dict[str, Any] | None = None


def json_success(
    *,
    data: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Build a success response envelope."""
    payload: dict[str, Any] = {"success": True}
    if message:
        payload["message"] = message
    if data:
        payload.update(data)
    return payload


def json_error(error: UiHttpError) -> dict[str, Any]:
    """Build an error response envelope."""
    payload: dict[str, Any] = {
        "success": False,
        "error": error.message,
        "code": error.code,
    }
    if error.details:
        payload["details"] = error.details
    return payload


def send_json(handler: BaseHTTPRequestHandler, data: dict[str, Any], *, status: int = 200) -> None:
    """Send a JSON response."""
    body = json.dumps(data, default=str).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        # The browser navigated away or cancelled the request; nobody is left to answer.
        logger.debug("Client disconnected before the response was sent")


@dataclass(slots=True)
class RawResponse:
    """A non-JSON download (TSV, BIOM…) returned by a handler."""

    body: bytes
    content_type: str
    filename: str


def send_raw(handler: BaseHTTPRequestHandler, raw: RawResponse) -> None:
    """Send a file download."""
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", raw.content_type)
        handler.send_header("Content-Length", str(len(raw.body)))
        handler.send_header("Content-Disposition", f'attachment; filename="{raw.filename}"')
        handler.end_headers()
        handler.wfile.write(raw.body)
    except (BrokenPipeError, ConnectionResetError):
        logger.debug("Client disconnected before the download was sent")


def send_html(handler: BaseHTTPRequestHandler, html: str, *, status: int = 200) -> None:
    """Send an HTML response."""
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_error(handler: BaseHTTPRequestHandler, error: UiHttpError) -> None:
    """Send an error envelope."""
    send_json(handler, json_error(error), status=error.status)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    """Read and validate a JSON request body."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    if length > MAX_BODY_BYTES:
        raise UiHttpError("Request body too large", status=413, code="too_large")

    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UiHttpError(
            "Request body must be valid JSON.",
            status=400,
            code="invalid_json",
        ) from exc

    if not isinstance(payload, dict):
        raise UiHttpError(
            "Request body must be a JSON object.",
            status=400,
            code="invalid_payload",
        )
    return payload
