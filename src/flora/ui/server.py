"""FLORA Web Interface server bootstrap and request dispatch."""

from __future__ import annotations

import logging
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flora.config.settings import FloraConfig, load_config
from flora.core.logging import setup_logging
from flora.ui.frontend import (
    FrontendNotBuiltError,
    load_index_html,
    resolve_frontend_asset,
    should_serve_spa_index,
)
from flora.ui.handlers import analysis, datasets, engines, exports, downloads, explore, ingest, llm, ml, projects, report, status, viz, workspace
from flora.ui.http import RawResponse, UiHttpError, read_json_body, send_error, send_html, send_json, send_raw
from flora.ui.state import FLORAState

logger = logging.getLogger("flora.ui.server")

_LOG_BUFFER: list[str] = []
_LOG_BUFFER_MAX = 500


class _BufferHandler(logging.Handler):
    """Appends formatted records to the in-memory UI log buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        _LOG_BUFFER.append(line)
        if len(_LOG_BUFFER) > _LOG_BUFFER_MAX:
            del _LOG_BUFFER[: len(_LOG_BUFFER) - _LOG_BUFFER_MAX]


def _public_failure(exc: Exception) -> UiHttpError:
    """A short Portuguese message. The traceback stays in the server log."""
    detail = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
    return UiHttpError(
        "A etapa falhou. Confira os dados do projeto e tente de novo. "
        f"Se continuar, o detalhe técnico é: {detail}",
        status=500,
        code="internal_error",
    )


def _install_buffer_handler() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, _BufferHandler):
            return

    buffer_handler = _BufferHandler()
    buffer_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
    )
    root.addHandler(buffer_handler)


GET_ROUTES = {
    "/api/status": status.get_status,
    "/api/dashboard": workspace.get_dashboard,
    "/api/pipeline": workspace.get_pipeline,
    "/api/pipeline/datasets": datasets.list_datasets,
    "/api/explore/summary": workspace.explore_summary,
    "/api/explore/schema": explore.get_schema,
    "/api/explore/map": explore.get_map,
    "/api/engines": engines.list_engines,
    "/api/export/dataset": exports.export_dataset,
    "/api/engines/jobs": engines.list_jobs,
    "/api/engines/environments": engines.get_environments,
    "/api/engines/jobs/detail": engines.get_job,
    "/api/engines/jobs/results": engines.job_results,
    "/api/analysis/qc": analysis.get_qc,
    "/api/analysis/rarefaction": analysis.get_rarefaction,
    "/api/analysis/alpha_stats": analysis.get_alpha_stats,
    "/api/analysis/beta_stats": analysis.get_beta_stats,
    "/api/analysis/volcano": analysis.get_volcano,
    "/api/analysis/mixs": analysis.get_mixs,
    "/api/analysis/tree": analysis.tree_status,
    "/api/analysis/settings": analysis.get_settings,
    "/api/explore/table": explore.get_table,
    "/api/ml/experiments": ml.list_experiments,
    "/api/downloads": downloads.list_downloads,
    "/api/downloads/library": downloads.library_search,
    "/api/downloads/library/runs": downloads.library_runs,
    "/api/report/draft": report.report_draft,
    "/api/feature_matrix": ingest.get_feature_matrix,
    "/api/report/preview": report.preview_report,
    "/api/projects": projects.list_projects,
    "/api/projects/detail": projects.get_project,
    "/api/sync-jobs": projects.get_job,
    "/api/examples": projects.list_examples,
    "/api/llm/config": llm.get_config,
    "/api/llm/models": llm.list_models,
    "/api/llm/agent/runs": llm.list_agent_runs,
    "/api/llm/agent/runs/detail": llm.get_agent_run,
    "/api/llm/models/pull": llm.pull_status,
    "/api/viz/taxonomy": viz.viz_taxonomy,
    "/api/viz/pcoa": viz.viz_pcoa,
    "/api/viz/alpha": viz.viz_alpha,
    "/api/viz/taxonomy_heatmap": viz.viz_taxonomy_heatmap,
    "/api/viz/beta_heatmap": viz.viz_beta_heatmap,
    "/api/viz/krona": viz.viz_krona,
    "/api/viz/tree": viz.viz_tree,
    "/api/viz/network": viz.viz_network,
}

POST_ROUTES = {
    "/api/ingest/dataset": ingest.ingest_dataset,
    "/api/ingest/clear": ingest.clear_dataset,
    "/api/ingest/metadata": ingest.ingest_metadata,
    "/api/ingest/asv": ingest.ingest_asv,
    "/api/ingest/taxonomy": ingest.ingest_taxonomy,
    "/api/diversity": ingest.compute_diversity,
    "/api/ml/classify": ml.classify,
    "/api/ml/cluster": ml.cluster,
    "/api/ingest/preview": workspace.preview_ingest,
    "/api/pipeline/upload": datasets.upload_file,
    "/api/engines/run": engines.run_engine,
    "/api/engines/config": engines.save_environment,
    "/api/engines/jobs/cancel": engines.cancel_job,
    "/api/analysis/qc/apply": analysis.apply_qc,
    "/api/analysis/tree": analysis.save_tree,
    "/api/analysis/settings": analysis.save_settings,
    "/api/download/mgnify": downloads.recorded("mgnify", downloads.download_mgnify),
    "/api/download/sra": downloads.recorded("sra", downloads.download_sra),
    "/api/download/emp": downloads.recorded("emp", downloads.download_emp),
    "/api/download/synthetic": downloads.recorded("synthetic", downloads.download_synthetic),
    "/api/report": report.generate_report,
    "/api/projects": projects.create_project,
    "/api/projects/update": projects.update_project,
    "/api/projects/activate": projects.activate_project,
    "/api/projects/sync": projects.start_sync,
    "/api/sync-jobs/cancel": projects.cancel_job,
    "/api/examples/install": projects.install_example,
    "/api/llm/config": llm.save_config,
    "/api/llm/test": llm.test_connection,
    "/api/llm/chat": llm.chat,
    "/api/llm/agent": llm.agent,
    "/api/llm/models/pull": llm.pull_start,
    "/api/llm/models/pull/cancel": llm.pull_cancel,
}


def _serve_frontend_missing(handler: BaseHTTPRequestHandler, message: str) -> None:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLORA UI build missing</title>
  <style>
    body {{ font-family: sans-serif; margin: 0; padding: 32px;
      background: #f6f0e6; color: #1f2937; }}
    main {{ max-width: 720px; margin: 0 auto; background: white;
      padding: 24px; border-radius: 16px; }}
    pre {{ padding: 12px; background: #f3f4f6; border-radius: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <main>
    <h1>FLORA UI build not found</h1>
    <p>{message}</p>
    <pre>cd src/flora/front
npm ci
npm run build
flora ui --host 127.0.0.1 --port 8765 --workdir results/ --log-level INFO</pre>
  </main>
</body>
</html>"""
    send_html(handler, html, status=503)


def _serve_frontend_asset(handler: BaseHTTPRequestHandler, path: str) -> bool:
    asset = resolve_frontend_asset(path)
    if asset is None:
        return False

    if asset.binary:
        body = asset.path.read_bytes()
    else:
        body = asset.path.read_text(encoding="utf-8").encode("utf-8")

    handler.send_response(200)
    handler.send_header("Content-Type", asset.content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _make_handler(state: FLORAState):
    class FLORAHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.info("HTTP %s", fmt % args)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            try:
                if path in {"/", "/index.html"}:
                    send_html(self, load_index_html())
                    return

                if not path.startswith("/api/") and _serve_frontend_asset(self, path):
                    return

                if not path.startswith("/api/") and should_serve_spa_index(path):
                    send_html(self, load_index_html())
                    return

                if path == "/api/logs":
                    payload = downloads.get_logs(_LOG_BUFFER, parse_qs(parsed.query))
                    send_json(self, payload)
                    return

                routed = downloads.library_route("GET", path)
                if routed:
                    kind, extra = routed
                    params = parse_qs(parsed.query)
                    for key, value in extra.items():
                        params[key] = [value]
                    if kind == "catalog":
                        payload = downloads.library_catalog(state, params)
                    elif kind == "map":
                        payload = downloads.library_map(state, params)
                    else:
                        payload = downloads.library_metadata(state, params)
                    send_json(self, payload)
                    return

                handler = GET_ROUTES.get(path)
                if handler is None:
                    raise UiHttpError(f"Endpoint desconhecido: {path}", status=404, code="not_found")

                payload = handler(state, parse_qs(parsed.query))
                if isinstance(payload, RawResponse):
                    send_raw(self, payload)
                    return
                if path == "/api/report/preview":
                    send_html(self, payload)
                    return
                send_json(self, payload)
            except UiHttpError as exc:
                send_error(self, exc)
            except FrontendNotBuiltError as exc:
                _serve_frontend_missing(self, str(exc))
            except Exception as exc:
                logger.error("Handler error: %s\n%s", exc, traceback.format_exc())
                send_error(self, _public_failure(exc))

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            try:
                body = read_json_body(self)
                routed = downloads.library_route("POST", path)
                if routed:
                    _kind, extra = routed
                    body = {**body, **extra}
                    handler = downloads.recorded(extra["source"], downloads.library_download)
                    payload = handler(state, body)
                    send_json(self, payload)
                    return

                handler = POST_ROUTES.get(path)
                if handler is None:
                    raise UiHttpError(f"Endpoint desconhecido: {path}", status=404, code="not_found")

                payload = handler(state, body)
                send_json(self, payload)
            except UiHttpError as exc:
                send_error(self, exc)
            except Exception as exc:
                logger.error("Handler error: %s\n%s", exc, traceback.format_exc())
                send_error(self, _public_failure(exc))

    return FLORAHandler


def create_app(
    config: FloraConfig | None = None,
    workdir: str | Path = "results",
) -> tuple[type[HTTPServer], type[BaseHTTPRequestHandler], FLORAState]:
    """Create the FLORA HTTP server and application state."""
    cfg = config or load_config()
    state = FLORAState(config=cfg, workdir=Path(workdir))
    return HTTPServer, _make_handler(state), state


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    config: FloraConfig | None = None,
    workdir: str | Path = "results",
    open_browser: bool = True,
    log_level: str = "INFO",
) -> None:
    """Start the FLORA web interface server."""
    setup_logging(level=log_level)
    _install_buffer_handler()

    server_cls, handler_cls, _state = create_app(config=config, workdir=workdir)
    server = server_cls((host, port), handler_cls)
    url = f"http://{host}:{port}"
    logger.info("FLORA web interface: %s", url)
    print(f"\nFLORA Web Interface running at: {url}")
    print(f"Log level: {log_level}  |  Press Ctrl+C to stop.\n")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
