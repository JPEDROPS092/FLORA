"""FLORA Web Interface Server.

Lightweight HTTP server built with Python's built-in http.server. No Flask
or FastAPI dependency required. Exposes a REST-like JSON API consumed by
the single-page HTML interface.

Endpoints:
    GET  /                       -> index.html (SPA)
    GET  /api/status             -> pipeline status and DB stats
    POST /api/ingest/metadata    -> ingest a metadata file
    POST /api/ingest/asv         -> ingest an ASV table
    POST /api/ingest/taxonomy    -> ingest a taxonomy file
    POST /api/diversity          -> compute alpha diversity
    GET  /api/feature_matrix     -> get feature matrix (CLR/TSS/raw)
    POST /api/ml/classify        -> train a classifier
    POST /api/ml/cluster         -> run clustering
    GET  /api/viz/taxonomy       -> taxonomy barplot JSON
    GET  /api/viz/pcoa           -> PCoA plot JSON
    GET  /api/viz/alpha          -> alpha diversity plot JSON
    POST /api/download/mgnify    -> download from MGnify
    POST /api/download/sra       -> download from NCBI SRA
    POST /api/report             -> generate HTML report
"""

from __future__ import annotations

import json
import logging
import os
import threading
import traceback
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from flora.config.settings import FloraConfig, load_config
from flora.core.logging import setup_logging

logger = logging.getLogger("flora.ui.server")

_UI_DIR = Path(__file__).parent
_FRONT_DIST = _UI_DIR.parent / "front" / "dist"

# MIME types for static file serving
_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".eot": "application/vnd.ms-fontobject",
    ".map": "application/json",
}


def _angular_dist_available() -> bool:
    """Check if the Angular frontend has been built."""
    return _FRONT_DIST.is_dir() and any(_FRONT_DIST.iterdir())


class FLORAState:
    """Singleton application state shared across HTTP handler instances."""

    def __init__(self, config: FloraConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir
        self._pipeline = None
        self._lock = threading.Lock()

    @property
    def pipeline(self):
        from flora.pipelines.main_pipeline import FLORAPipeline

        with self._lock:
            if self._pipeline is None:
                self._pipeline = FLORAPipeline(config=self.config, workdir=self.workdir)
        return self._pipeline

    @property
    def db(self):
        return self.pipeline.db


def _json_response(handler: BaseHTTPRequestHandler, data: Any, status: int = 200) -> None:
    body = json.dumps(data, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _error_response(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    _json_response(handler, {"error": message, "success": False}, status)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _make_handler(state: FLORAState):
    class FLORAHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("HTTP %s", fmt % args)

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
                if path == "/" or path == "/index.html":
                    self._serve_index()
                elif path == "/api/status":
                    self._handle_status()
                elif path == "/api/feature_matrix":
                    params = parse_qs(parsed.query)
                    self._handle_feature_matrix(params)
                elif path == "/api/viz/taxonomy":
                    params = parse_qs(parsed.query)
                    self._handle_viz_taxonomy(params)
                elif path == "/api/viz/pcoa":
                    params = parse_qs(parsed.query)
                    self._handle_viz_pcoa(params)
                elif path == "/api/viz/alpha":
                    params = parse_qs(parsed.query)
                    self._handle_viz_alpha(params)
                elif path.startswith("/api/"):
                    _error_response(self, f"Unknown endpoint: {path}", 404)
                elif _angular_dist_available():
                    self._serve_static(path)
                else:
                    _error_response(self, "Not found", 404)
            except Exception as exc:
                logger.error("Handler error: %s\n%s", exc, traceback.format_exc())
                _error_response(self, f"Internal error: {exc}", 500)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            body = _read_body(self)

            try:
                if path == "/api/ingest/metadata":
                    self._handle_ingest_metadata(body)
                elif path == "/api/ingest/asv":
                    self._handle_ingest_asv(body)
                elif path == "/api/ingest/taxonomy":
                    self._handle_ingest_taxonomy(body)
                elif path == "/api/diversity":
                    self._handle_diversity(body)
                elif path == "/api/ml/classify":
                    self._handle_classify(body)
                elif path == "/api/ml/cluster":
                    self._handle_cluster(body)
                elif path == "/api/download/mgnify":
                    self._handle_download_mgnify(body)
                elif path == "/api/download/sra":
                    self._handle_download_sra(body)
                elif path == "/api/report":
                    self._handle_report(body)
                else:
                    _error_response(self, f"Unknown endpoint: {path}", 404)
            except Exception as exc:
                logger.error("Handler error: %s\n%s", exc, traceback.format_exc())
                _error_response(self, f"Internal error: {exc}", 500)

        def _serve_index(self):
            if _angular_dist_available():
                index_path = _FRONT_DIST / "index.html"
                if index_path.exists():
                    body = index_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            html = _build_index_html()
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, path: str):
            """Serve static files from the Angular dist directory."""
            file_path = (_FRONT_DIST / path.lstrip("/")).resolve()
            if not str(file_path).startswith(str(_FRONT_DIST.resolve())):
                _error_response(self, "Forbidden", 403)
                return
            if file_path.is_dir():
                file_path = file_path / "index.html"
            if not file_path.exists() or not file_path.is_file():
                index_path = _FRONT_DIST / "index.html"
                if index_path.exists():
                    body = index_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    _error_response(self, "Not found", 404)
                return
            suffix = file_path.suffix.lower()
            content_type = _MIME_TYPES.get(suffix, "application/octet-stream")
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if suffix in (".js", ".css", ".woff", ".woff2", ".ttf", ".eot"):
                self.send_header("Cache-Control", "public, max-age=31536000")
            self.end_headers()
            self.wfile.write(body)

        def _handle_status(self):
            try:
                info = state.db.table_info()
                tables = {
                    row["table_name"]: int(row["row_count"])
                    for row in info.iter_rows(named=True)
                }
                _json_response(self, {
                    "success": True,
                    "status": "connected",
                    "workdir": str(state.workdir),
                    "db_path": state.config.database.path,
                    "tables": tables,
                })
            except Exception as exc:
                _json_response(self, {
                    "success": True,
                    "status": "initialized",
                    "workdir": str(state.workdir),
                    "tables": {},
                })

        def _handle_ingest_metadata(self, body: dict):
            path = body.get("path", "")
            if not path:
                return _error_response(self, "path is required")
            sample_col = body.get("sample_col", "sample_id")
            n = state.pipeline.ingest_metadata(path, sample_col=sample_col)
            _json_response(self, {"success": True, "samples_ingested": n})

        def _handle_ingest_asv(self, body: dict):
            path = body.get("path", "")
            if not path:
                return _error_response(self, "path is required")
            wide = body.get("wide_format", False)
            n = state.pipeline.ingest_asv_table(path, wide_format=wide)
            _json_response(self, {"success": True, "observations_ingested": n})

        def _handle_ingest_taxonomy(self, body: dict):
            path = body.get("path", "")
            if not path:
                return _error_response(self, "path is required")
            n = state.pipeline.ingest_taxonomy(path)
            _json_response(self, {"success": True, "taxonomy_rows": n})

        def _handle_diversity(self, body: dict):
            depth = body.get("sampling_depth")
            metrics = body.get("metrics", ["shannon", "observed_features", "chao1"])
            result = state.pipeline.compute_diversity(
                sampling_depth=int(depth) if depth else None,
                metrics=metrics,
            )
            _json_response(self, {
                "success": True,
                "metrics": metrics,
                "samples": len(result),
                "preview": result.head(5).to_pandas().to_dict(orient="records"),
            })

        def _handle_feature_matrix(self, params: dict):
            normalize = params.get("normalize", ["clr"])[0]
            min_prev = float(params.get("min_prevalence", ["0.05"])[0])
            fm = state.pipeline.get_feature_matrix(
                normalize=normalize if normalize != "none" else None,
                min_prevalence=min_prev,
            )
            _json_response(self, {
                "success": True,
                "n_samples": len(fm),
                "n_features": len(fm.columns) - 1,
                "normalize": normalize,
                "preview": fm.head(3).to_pandas().to_dict(orient="records"),
            })

        def _handle_classify(self, body: dict):
            from flora.ml.classification.classifier import MicrobiomeClassifier

            model_type = body.get("model", "random_forest")
            target = body.get("target_column", "biome")
            train_filter = body.get("train_filter", "")
            test_filter = body.get("test_filter", "")
            cv_folds = int(body.get("cv_folds", 5))
            normalize = body.get("normalize", "clr")

            if not train_filter or not test_filter:
                return _error_response(self, "train_filter and test_filter are required")

            train, test = state.db.slice(
                train_filter=train_filter,
                test_filter=test_filter,
                features=normalize,
                target_column=target,
            )

            clf = MicrobiomeClassifier(
                model=model_type,
                target_column=target,
                random_state=42,
                mlflow_tracking_uri=None,
            )
            result = clf.fit(train, test, cv_folds=cv_folds)

            _json_response(self, {
                "success": True,
                "model": model_type,
                "accuracy": result.accuracy,
                "f1_macro": result.f1_macro,
                "roc_auc": result.roc_auc,
                "cv_accuracy_mean": sum(result.cv_scores["accuracy"]) / len(result.cv_scores["accuracy"]),
                "classification_report": result.classification_report_str,
                "top_features": result.feature_importances.head(10).to_pandas().to_dict(orient="records")
                if result.feature_importances is not None else [],
            })

        def _handle_cluster(self, body: dict):
            from flora.ml.clustering.clusterer import MicrobiomeClusterer
            from flora.feature_engineering.reduction import compute_pcoa

            method = body.get("method", "kmeans")
            n_clusters = int(body.get("n_clusters", 4))
            normalize = body.get("normalize", "clr")

            fm = state.pipeline.get_feature_matrix(normalize=normalize)
            pcoa_long = compute_pcoa(fm, metric="braycurtis", n_components=2)
            pcoa_wide = pcoa_long.pivot(
                index="sample_id", on="component", values="value",
                aggregate_function="first"
            ).rename({"1": "PC1", "2": "PC2"})

            clusterer = MicrobiomeClusterer(
                method=method,
                n_clusters=n_clusters,
                random_state=42,
            )
            result = clusterer.fit(pcoa_wide)

            _json_response(self, {
                "success": True,
                "method": method,
                "n_clusters": result.n_clusters,
                "silhouette": result.silhouette,
                "davies_bouldin": result.davies_bouldin,
                "noise_fraction": result.noise_fraction,
                "labels": result.labels.to_pandas().to_dict(orient="records"),
            })

        def _handle_viz_taxonomy(self, params: dict):
            level = params.get("level", ["phylum"])[0]
            group_by = params.get("group_by", [None])[0]
            try:
                agg = state.db.aggregate_by_taxon(level=level, group_by=group_by)
                from flora.viz.taxonomy_plots import plot_taxonomy_barplot
                fig = plot_taxonomy_barplot(agg, level=level, group_by=group_by)
                _json_response(self, {"success": True, "plot": json.loads(fig.to_json())})
            except Exception as exc:
                _error_response(self, str(exc))

        def _handle_viz_pcoa(self, params: dict):
            normalize = params.get("normalize", ["clr"])[0]
            color_by = params.get("color_by", [None])[0]
            try:
                fm = state.pipeline.get_feature_matrix(normalize=normalize)
                from flora.feature_engineering.reduction import compute_pcoa
                from flora.viz.diversity_plots import plot_pcoa

                pcoa_long = compute_pcoa(fm, metric="braycurtis", n_components=3)

                meta = state.db.query("SELECT * FROM samples").to_polars()
                fig = plot_pcoa(
                    pcoa_long,
                    metadata_df=meta if color_by else None,
                    color_by=color_by,
                )
                _json_response(self, {"success": True, "plot": json.loads(fig.to_json())})
            except Exception as exc:
                _error_response(self, str(exc))

        def _handle_viz_alpha(self, params: dict):
            metric = params.get("metric", ["shannon"])[0]
            group_by = params.get("group_by", [None])[0]
            try:
                fm = state.pipeline.get_feature_matrix(normalize=None)
                from flora.diversity.alpha import compute_alpha_diversity
                from flora.viz.diversity_plots import plot_alpha_diversity

                alpha = compute_alpha_diversity(fm, metrics=[metric])
                meta = state.db.query("SELECT * FROM samples").to_polars()
                if group_by:
                    alpha = alpha.join(
                        meta.select(["sample_id", group_by]), on="sample_id", how="left"
                    )
                fig = plot_alpha_diversity(alpha, metric=metric, group_by=group_by)
                _json_response(self, {"success": True, "plot": json.loads(fig.to_json())})
            except Exception as exc:
                _error_response(self, str(exc))

        def _handle_download_mgnify(self, body: dict):
            from flora.io.downloaders import MGnifyDownloader

            study = body.get("study_accession", "")
            if not study:
                return _error_response(self, "study_accession is required")

            biome = body.get("biome", "root:Environmental:Terrestrial")
            output_dir = body.get("output_dir", str(state.workdir / "raw"))
            max_samples = int(body.get("max_samples", 20))

            dl = MGnifyDownloader(biome=biome)
            try:
                manifest = dl.fetch(
                    study_accession=study,
                    output_dir=output_dir,
                    max_samples=max_samples,
                )
                _json_response(self, {
                    "success": True,
                    "manifest": str(manifest),
                    "output_dir": output_dir,
                })
            except Exception as exc:
                _error_response(self, str(exc))

        def _handle_download_sra(self, body: dict):
            from flora.io.downloaders import NCBISRADownloader

            accessions = body.get("accessions", [])
            if not accessions:
                return _error_response(self, "accessions list is required")

            output_dir = body.get("output_dir", str(state.workdir / "raw"))
            n_jobs = int(body.get("n_jobs", 4))

            dl = NCBISRADownloader(n_jobs=n_jobs)
            try:
                manifest = dl.fetch(accessions=accessions, output_dir=output_dir)
                _json_response(self, {
                    "success": True,
                    "manifest": str(manifest),
                    "accessions": accessions,
                })
            except Exception as exc:
                _error_response(self, str(exc))

        def _handle_report(self, body: dict):
            from flora.reports.html_report import FLORAReport
            from flora.diversity.alpha import compute_alpha_diversity
            from flora.viz.taxonomy_plots import plot_taxonomy_barplot

            title = body.get("title", "FLORA Analysis Report")
            output_path = body.get("output_path", str(state.workdir / "report.html"))

            report = FLORAReport(title=title)

            try:
                info = state.db.table_info()
                tables = {
                    row["table_name"]: int(row["row_count"])
                    for row in info.iter_rows(named=True)
                }
                report.add_metrics("Dataset Summary", tables)
            except Exception:
                pass

            try:
                fm = state.pipeline.get_feature_matrix(normalize=None)
                alpha = compute_alpha_diversity(fm, metrics=["shannon", "observed_features"])
                report.add_table("Alpha Diversity", alpha)
            except Exception as exc:
                logger.warning("Alpha diversity skipped in report: %s", exc)

            try:
                agg = state.db.aggregate_by_taxon(level="phylum", group_by="biome")
                fig = plot_taxonomy_barplot(agg, level="phylum", group_by="biome")
                report.add_plot("Taxonomic Composition", fig)
            except Exception as exc:
                logger.warning("Taxonomy plot skipped in report: %s", exc)

            saved = report.save(output_path)
            _json_response(self, {"success": True, "report_path": str(saved)})

    return FLORAHandler


def _build_index_html() -> str:
    """Return the complete single-page HTML application."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FLORA — Microbiome Analysis Platform</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --green: #1a6b3c; --green-light: #2a8c52; --green-pale: #e8f5ee;
    --gray: #6b7280; --gray-light: #f3f4f6; --border: #e5e7eb;
    --red: #dc2626; --blue: #2563eb; --orange: #d97706;
    --font: 'Segoe UI', system-ui, sans-serif;
    --radius: 8px; --shadow: 0 1px 4px rgba(0,0,0,.10);
  }
  body { font-family: var(--font); background: #f0f2f5; color: #111827; display: flex; min-height: 100vh; }
  nav {
    width: 240px; min-height: 100vh; background: var(--green); color: white;
    display: flex; flex-direction: column; padding: 0; flex-shrink: 0; position: fixed;
  }
  nav .logo { padding: 24px 20px 20px; border-bottom: 1px solid rgba(255,255,255,.15); }
  nav .logo h1 { font-size: 1.6em; font-weight: 700; letter-spacing: -.5px; }
  nav .logo p { font-size: .72em; opacity: .75; margin-top: 4px; line-height: 1.4; }
  nav ul { list-style: none; padding: 12px 0; flex: 1; }
  nav ul li a {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 20px; color: rgba(255,255,255,.85); text-decoration: none;
    font-size: .88em; border-left: 3px solid transparent; transition: all .15s;
  }
  nav ul li a:hover, nav ul li a.active {
    color: white; background: rgba(255,255,255,.12); border-left-color: white;
  }
  nav .status-bar { padding: 16px 20px; border-top: 1px solid rgba(255,255,255,.15); font-size: .75em; opacity: .8; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .dot.green { background: #4ade80; }
  .dot.red { background: #f87171; }
  main { margin-left: 240px; flex: 1; padding: 28px; max-width: 1200px; }
  .page { display: none; }
  .page.active { display: block; }
  h2 { font-size: 1.4em; color: var(--green); margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
  .card { background: white; border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow); margin-bottom: 20px; }
  .card h3 { font-size: 1em; color: var(--green); margin-bottom: 16px; font-weight: 600; }
  .form-row { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
  .form-group { flex: 1; min-width: 200px; }
  label { display: block; font-size: .82em; font-weight: 500; color: var(--gray); margin-bottom: 5px; }
  input, select, textarea {
    width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
    font-size: .88em; font-family: inherit; background: white; color: #111827;
    transition: border-color .15s;
  }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--green); }
  textarea { height: 80px; resize: vertical; }
  .btn {
    padding: 9px 20px; border: none; border-radius: 6px; font-size: .88em; font-weight: 600;
    cursor: pointer; transition: all .15s; display: inline-flex; align-items: center; gap: 6px;
  }
  .btn-primary { background: var(--green); color: white; }
  .btn-primary:hover { background: var(--green-light); }
  .btn-secondary { background: var(--gray-light); color: #374151; }
  .btn-secondary:hover { background: var(--border); }
  .btn-danger { background: #fee2e2; color: var(--red); }
  .btn-danger:hover { background: #fca5a5; }
  .btn:disabled { opacity: .5; cursor: not-allowed; }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: .76em;
    font-weight: 600;
  }
  .badge-green { background: #d1fae5; color: #065f46; }
  .badge-gray { background: var(--gray-light); color: var(--gray); }
  .badge-red { background: #fee2e2; color: var(--red); }
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }
  .metric-card { background: var(--green-pale); border-radius: var(--radius); padding: 16px; text-align: center; }
  .metric-card .val { font-size: 1.8em; font-weight: 700; color: var(--green); }
  .metric-card .lbl { font-size: .78em; color: var(--gray); margin-top: 4px; }
  .alert { padding: 12px 16px; border-radius: 6px; font-size: .88em; margin-top: 12px; }
  .alert-success { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
  .alert-error { background: #fee2e2; color: var(--red); border: 1px solid #fca5a5; }
  .alert-info { background: #dbeafe; color: var(--blue); border: 1px solid #93c5fd; }
  table { width: 100%; border-collapse: collapse; font-size: .85em; }
  th { background: var(--green); color: white; padding: 9px 14px; text-align: left; font-weight: 500; }
  td { padding: 8px 14px; border-bottom: 1px solid var(--border); }
  tr:hover td { background: var(--green-pale); }
  .plot-container { width: 100%; min-height: 420px; }
  .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid rgba(255,255,255,.4); border-top-color: white; border-radius: 50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .log-box { background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 6px; font-family: monospace; font-size: .82em; height: 180px; overflow-y: auto; }
  .log-line { margin: 2px 0; }
  .log-line.err { color: #fca5a5; }
  .log-line.ok { color: #6ee7b7; }
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 2px solid var(--border); padding-bottom: -2px; }
  .tab { padding: 9px 18px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: .88em; font-weight: 500; color: var(--gray); border: 1px solid transparent; border-bottom: none; transition: all .15s; }
  .tab.active { background: white; color: var(--green); border-color: var(--border); border-bottom-color: white; margin-bottom: -2px; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .progress { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; margin-top: 8px; }
  .progress-bar { height: 100%; background: var(--green); border-radius: 3px; transition: width .3s ease; }
  pre { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-size: .82em; overflow-x: auto; white-space: pre-wrap; }
  .step-list { list-style: none; }
  .step-list li { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
  .step-list li:last-child { border-bottom: none; }
  .step-icon { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: .8em; font-weight: 700; flex-shrink: 0; }
  .step-icon.done { background: #d1fae5; color: #065f46; }
  .step-icon.pending { background: var(--gray-light); color: var(--gray); }
  .step-icon.running { background: #dbeafe; color: var(--blue); animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
</style>
</head>
<body>

<nav>
  <div class="logo">
    <h1>FLORA</h1>
    <p>Feature Learning &amp; Omics Research Analytics</p>
  </div>
  <ul>
    <li><a href="#" class="active" data-page="dashboard">&#9632; Dashboard</a></li>
    <li><a href="#" data-page="ingest">&#8681; Data Ingestion</a></li>
    <li><a href="#" data-page="download">&#9660; Downloads</a></li>
    <li><a href="#" data-page="diversity">&#9670; Diversity</a></li>
    <li><a href="#" data-page="features">&#9670; Feature Engineering</a></li>
    <li><a href="#" data-page="ml">&#9670; Machine Learning</a></li>
    <li><a href="#" data-page="viz">&#9670; Visualization</a></li>
    <li><a href="#" data-page="report">&#9670; Report</a></li>
  </ul>
  <div class="status-bar">
    <span class="dot" id="status-dot"></span>
    <span id="status-text">Checking...</span>
  </div>
</nav>

<main>

<!-- DASHBOARD -->
<div class="page active" id="page-dashboard">
  <h2>Dashboard</h2>
  <div id="metrics-grid" class="metrics-grid"></div>
  <div class="card">
    <h3>Pipeline Steps</h3>
    <ul class="step-list" id="pipeline-steps">
      <li><div class="step-icon pending" id="step-meta">1</div><div><strong>Metadata</strong><br><small>Sample metadata (TSV/CSV)</small></div></li>
      <li><div class="step-icon pending" id="step-asv">2</div><div><strong>ASV Table</strong><br><small>BIOM or TSV feature table</small></div></li>
      <li><div class="step-icon pending" id="step-tax">3</div><div><strong>Taxonomy</strong><br><small>SILVA or Greengenes2 assignments</small></div></li>
      <li><div class="step-icon pending" id="step-div">4</div><div><strong>Diversity</strong><br><small>Alpha and beta diversity metrics</small></div></li>
      <li><div class="step-icon pending" id="step-ml">5</div><div><strong>ML</strong><br><small>Classification, clustering, regression</small></div></li>
    </ul>
  </div>
</div>

<!-- DATA INGESTION -->
<div class="page" id="page-ingest">
  <h2>Data Ingestion</h2>
  <div class="card">
    <h3>Sample Metadata</h3>
    <div class="form-row">
      <div class="form-group">
        <label>File Path (TSV or CSV)</label>
        <input type="text" id="meta-path" placeholder="/path/to/metadata.tsv">
      </div>
      <div class="form-group">
        <label>Sample ID Column</label>
        <input type="text" id="meta-sample-col" value="sample_id">
      </div>
    </div>
    <button class="btn btn-primary" onclick="ingestMetadata()">Load Metadata</button>
    <div id="meta-result"></div>
  </div>
  <div class="card">
    <h3>ASV Feature Table</h3>
    <div class="form-row">
      <div class="form-group">
        <label>File Path (BIOM or TSV)</label>
        <input type="text" id="asv-path" placeholder="/path/to/asv_table.biom">
      </div>
      <div class="form-group">
        <label>Format</label>
        <select id="asv-wide">
          <option value="false">Long format (sample_id, feature_id, abundance)</option>
          <option value="true">Wide format (samples x features)</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary" onclick="ingestASV()">Load ASV Table</button>
    <div id="asv-result"></div>
  </div>
  <div class="card">
    <h3>Taxonomy Assignments</h3>
    <div class="form-row">
      <div class="form-group">
        <label>File Path (TSV — SILVA or Greengenes2)</label>
        <input type="text" id="tax-path" placeholder="/path/to/taxonomy.tsv">
      </div>
    </div>
    <button class="btn btn-primary" onclick="ingestTaxonomy()">Load Taxonomy</button>
    <div id="tax-result"></div>
  </div>
</div>

<!-- DOWNLOADS -->
<div class="page" id="page-download">
  <h2>Dataset Downloads</h2>
  <div class="tabs">
    <div class="tab active" data-tab="mgnify">MGnify</div>
    <div class="tab" data-tab="sra">NCBI SRA</div>
  </div>
  <div class="tab-content active" id="tab-mgnify">
    <div class="card">
      <h3>MGnify (EMBL-EBI)</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Study Accession</label>
          <input type="text" id="mg-study" placeholder="MGYS00005116">
        </div>
        <div class="form-group">
          <label>Max Samples</label>
          <input type="number" id="mg-maxsamples" value="20" min="1">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Biome Filter</label>
          <input type="text" id="mg-biome" value="root:Environmental:Terrestrial:Forest">
        </div>
        <div class="form-group">
          <label>Output Directory</label>
          <input type="text" id="mg-outdir" placeholder="data/raw">
        </div>
      </div>
      <button class="btn btn-primary" onclick="downloadMGnify()">Start Download</button>
      <div id="mg-result"></div>
    </div>
  </div>
  <div class="tab-content" id="tab-sra">
    <div class="card">
      <h3>NCBI SRA</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Accessions (one per line)</label>
          <textarea id="sra-accessions" placeholder="SRR12345678&#10;SRR12345679"></textarea>
        </div>
        <div class="form-group">
          <label>Output Directory</label>
          <input type="text" id="sra-outdir" placeholder="data/raw">
        </div>
      </div>
      <button class="btn btn-primary" onclick="downloadSRA()">Start Download</button>
      <div id="sra-result"></div>
    </div>
  </div>
</div>

<!-- DIVERSITY -->
<div class="page" id="page-diversity">
  <h2>Diversity Analysis</h2>
  <div class="card">
    <h3>Compute Alpha Diversity</h3>
    <div class="form-row">
      <div class="form-group">
        <label>Sampling Depth (leave blank for auto)</label>
        <input type="number" id="div-depth" placeholder="10000" min="100">
      </div>
      <div class="form-group">
        <label>Metrics</label>
        <select id="div-metrics" multiple size="4">
          <option value="shannon" selected>Shannon</option>
          <option value="observed_features" selected>Observed Features</option>
          <option value="chao1" selected>Chao1</option>
          <option value="simpson">Simpson</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary" onclick="computeDiversity()">Compute Diversity</button>
    <div id="div-result"></div>
  </div>
</div>

<!-- FEATURE ENGINEERING -->
<div class="page" id="page-features">
  <h2>Feature Engineering</h2>
  <div class="card">
    <h3>Feature Matrix Preview</h3>
    <div class="form-row">
      <div class="form-group">
        <label>Normalization</label>
        <select id="feat-normalize">
          <option value="clr">CLR (Centered Log-Ratio)</option>
          <option value="tss">TSS (Relative Abundance)</option>
          <option value="none">None (raw counts)</option>
        </select>
      </div>
      <div class="form-group">
        <label>Min Prevalence</label>
        <input type="number" id="feat-prev" value="0.05" min="0" max="1" step="0.01">
      </div>
    </div>
    <button class="btn btn-primary" onclick="getFeatureMatrix()">Generate Matrix</button>
    <div id="feat-result"></div>
  </div>
</div>

<!-- ML -->
<div class="page" id="page-ml">
  <h2>Machine Learning</h2>
  <div class="tabs">
    <div class="tab active" data-tab="classify">Classification</div>
    <div class="tab" data-tab="cluster">Clustering</div>
  </div>
  <div class="tab-content active" id="tab-classify">
    <div class="card">
      <h3>Classification</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Model</label>
          <select id="clf-model">
            <option value="random_forest">Random Forest</option>
            <option value="xgboost">XGBoost</option>
            <option value="svm">SVM</option>
          </select>
        </div>
        <div class="form-group">
          <label>Target Column</label>
          <input type="text" id="clf-target" value="biome">
        </div>
        <div class="form-group">
          <label>CV Folds</label>
          <input type="number" id="clf-folds" value="5" min="2">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Train Filter (SQL WHERE)</label>
          <input type="text" id="clf-train" placeholder="biome = 'Amazon'">
        </div>
        <div class="form-group">
          <label>Test Filter (SQL WHERE)</label>
          <input type="text" id="clf-test" placeholder="biome = 'Cerrado'">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Normalization</label>
          <select id="clf-normalize">
            <option value="clr">CLR</option>
            <option value="tss">TSS</option>
            <option value="asv">Raw</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" onclick="runClassify()">Train Model</button>
      <div id="clf-result"></div>
    </div>
  </div>
  <div class="tab-content" id="tab-cluster">
    <div class="card">
      <h3>Clustering</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Method</label>
          <select id="clust-method">
            <option value="kmeans">K-Means</option>
            <option value="hdbscan">HDBSCAN</option>
          </select>
        </div>
        <div class="form-group">
          <label>Number of Clusters (K-Means)</label>
          <input type="number" id="clust-k" value="4" min="2">
        </div>
        <div class="form-group">
          <label>Normalization</label>
          <select id="clust-normalize">
            <option value="clr">CLR</option>
            <option value="tss">TSS</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" onclick="runCluster()">Run Clustering</button>
      <div id="clust-result"></div>
    </div>
  </div>
</div>

<!-- VISUALIZATION -->
<div class="page" id="page-viz">
  <h2>Visualization</h2>
  <div class="tabs">
    <div class="tab active" data-tab="vtax">Taxonomy</div>
    <div class="tab" data-tab="vpcoa">PCoA</div>
    <div class="tab" data-tab="valpha">Alpha Diversity</div>
  </div>
  <div class="tab-content active" id="tab-vtax">
    <div class="card">
      <h3>Taxonomic Composition</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Taxonomic Level</label>
          <select id="vtax-level">
            <option value="phylum">Phylum</option>
            <option value="class">Class</option>
            <option value="genus">Genus</option>
          </select>
        </div>
        <div class="form-group">
          <label>Group By (metadata column)</label>
          <input type="text" id="vtax-group" placeholder="biome (optional)">
        </div>
      </div>
      <button class="btn btn-primary" onclick="vizTaxonomy()">Generate Plot</button>
      <div id="vtax-plot" class="plot-container"></div>
    </div>
  </div>
  <div class="tab-content" id="tab-vpcoa">
    <div class="card">
      <h3>PCoA (Principal Coordinates Analysis)</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Normalization</label>
          <select id="vpcoa-normalize">
            <option value="clr">CLR</option>
            <option value="tss">TSS</option>
          </select>
        </div>
        <div class="form-group">
          <label>Color By (metadata column)</label>
          <input type="text" id="vpcoa-colorby" placeholder="biome (optional)">
        </div>
      </div>
      <button class="btn btn-primary" onclick="vizPCoA()">Generate PCoA</button>
      <div id="vpcoa-plot" class="plot-container"></div>
    </div>
  </div>
  <div class="tab-content" id="tab-valpha">
    <div class="card">
      <h3>Alpha Diversity</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Metric</label>
          <select id="valpha-metric">
            <option value="shannon">Shannon</option>
            <option value="observed_features">Observed Features</option>
            <option value="chao1">Chao1</option>
          </select>
        </div>
        <div class="form-group">
          <label>Group By</label>
          <input type="text" id="valpha-group" placeholder="biome (optional)">
        </div>
      </div>
      <button class="btn btn-primary" onclick="vizAlpha()">Generate Plot</button>
      <div id="valpha-plot" class="plot-container"></div>
    </div>
  </div>
</div>

<!-- REPORT -->
<div class="page" id="page-report">
  <h2>Generate Report</h2>
  <div class="card">
    <h3>HTML Report</h3>
    <div class="form-row">
      <div class="form-group">
        <label>Report Title</label>
        <input type="text" id="report-title" value="FLORA Microbiome Analysis Report">
      </div>
      <div class="form-group">
        <label>Output Path</label>
        <input type="text" id="report-path" placeholder="results/report.html">
      </div>
    </div>
    <button class="btn btn-primary" onclick="generateReport()">Generate Report</button>
    <div id="report-result"></div>
  </div>
</div>

</main>

<script>
const API = '';

// ---- Navigation ----
document.querySelectorAll('nav a[data-page]').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const page = link.dataset.page;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
    document.getElementById('page-' + page).classList.add('active');
    link.classList.add('active');
  });
});

// ---- Tabs ----
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const group = tab.closest('.tabs, .page');
    group.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const name = tab.dataset.tab;
    const parent = tab.closest('.page') || document.body;
    parent.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
    const target = parent.querySelector('#tab-' + name);
    if (target) target.classList.add('active');
  });
});

// ---- API helpers ----
async function apiFetch(path, method='GET', body=null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(API + path, opts);
    return await res.json();
  } catch(e) {
    return { success: false, error: String(e) };
  }
}

function alert_div(id, data) {
  const el = document.getElementById(id);
  if (!el) return;
  if (data.success) {
    el.innerHTML = '<div class="alert alert-success">' + JSON.stringify(data, null, 2).replace(/\\n/g,'<br>') + '</div>';
  } else {
    el.innerHTML = '<div class="alert alert-error">Error: ' + (data.error || 'Unknown error') + '</div>';
  }
}

function setLoading(btn, loading) {
  if (loading) {
    btn._origText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Processing...';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn._origText || 'Run';
    btn.disabled = false;
  }
}

// ---- Status ----
async function refreshStatus() {
  const data = await apiFetch('/api/status');
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  if (data.success) {
    dot.className = 'dot green';
    txt.textContent = 'Connected';
    updateDashboard(data);
  } else {
    dot.className = 'dot red';
    txt.textContent = 'Disconnected';
  }
}

function updateDashboard(data) {
  const tables = data.tables || {};
  const grid = document.getElementById('metrics-grid');
  const items = [
    { lbl: 'Samples', val: tables.samples || 0 },
    { lbl: 'ASV Observations', val: tables.asv || 0 },
    { lbl: 'Taxonomy Entries', val: tables.taxonomy || 0 },
    { lbl: 'Alpha Metrics', val: tables.diversity_alpha || 0 },
    { lbl: 'Beta Distances', val: tables.diversity_beta || 0 },
    { lbl: 'Workdir', val: data.workdir || '—' },
  ];
  grid.innerHTML = items.map(i =>
    `<div class="metric-card"><div class="val">${typeof i.val === 'number' ? i.val.toLocaleString() : i.val}</div><div class="lbl">${i.lbl}</div></div>`
  ).join('');

  const mark = (id, done) => {
    const el = document.getElementById(id);
    if (el) el.className = 'step-icon ' + (done ? 'done' : 'pending');
    if (el && done) el.textContent = '✓';
  };
  mark('step-meta', (tables.samples || 0) > 0);
  mark('step-asv',  (tables.asv || 0) > 0);
  mark('step-tax',  (tables.taxonomy || 0) > 0);
  mark('step-div',  (tables.diversity_alpha || 0) > 0);
}

// ---- Ingestion ----
async function ingestMetadata() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/metadata', 'POST', {
    path: document.getElementById('meta-path').value,
    sample_col: document.getElementById('meta-sample-col').value,
  });
  alert_div('meta-result', data);
  setLoading(btn, false);
  refreshStatus();
}

async function ingestASV() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/asv', 'POST', {
    path: document.getElementById('asv-path').value,
    wide_format: document.getElementById('asv-wide').value === 'true',
  });
  alert_div('asv-result', data);
  setLoading(btn, false);
  refreshStatus();
}

async function ingestTaxonomy() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/taxonomy', 'POST', {
    path: document.getElementById('tax-path').value,
  });
  alert_div('tax-result', data);
  setLoading(btn, false);
  refreshStatus();
}

// ---- Downloads ----
async function downloadMGnify() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/download/mgnify', 'POST', {
    study_accession: document.getElementById('mg-study').value,
    biome: document.getElementById('mg-biome').value,
    output_dir: document.getElementById('mg-outdir').value,
    max_samples: parseInt(document.getElementById('mg-maxsamples').value),
  });
  alert_div('mg-result', data);
  setLoading(btn, false);
}

async function downloadSRA() {
  const btn = event.target;
  setLoading(btn, true);
  const raw = document.getElementById('sra-accessions').value;
  const accessions = raw.split('\\n').map(s => s.trim()).filter(Boolean);
  const data = await apiFetch('/api/download/sra', 'POST', {
    accessions,
    output_dir: document.getElementById('sra-outdir').value,
  });
  alert_div('sra-result', data);
  setLoading(btn, false);
}

// ---- Diversity ----
async function computeDiversity() {
  const btn = event.target;
  setLoading(btn, true);
  const sel = document.getElementById('div-metrics');
  const metrics = Array.from(sel.selectedOptions).map(o => o.value);
  const depth = document.getElementById('div-depth').value;
  const data = await apiFetch('/api/diversity', 'POST', {
    metrics,
    sampling_depth: depth ? parseInt(depth) : null,
  });
  if (data.success) {
    let html = '<div class="alert alert-success">Computed ' + metrics.join(', ') + ' for ' + data.samples + ' samples.</div>';
    if (data.preview && data.preview.length) {
      html += '<table><thead><tr>' + Object.keys(data.preview[0]).map(k => '<th>' + k + '</th>').join('') + '</tr></thead><tbody>';
      data.preview.forEach(row => {
        html += '<tr>' + Object.values(row).map(v => '<td>' + (typeof v === 'number' ? v.toFixed(4) : v) + '</td>').join('') + '</tr>';
      });
      html += '</tbody></table>';
    }
    document.getElementById('div-result').innerHTML = html;
  } else {
    alert_div('div-result', data);
  }
  setLoading(btn, false);
  refreshStatus();
}

// ---- Feature Matrix ----
async function getFeatureMatrix() {
  const btn = event.target;
  setLoading(btn, true);
  const norm = document.getElementById('feat-normalize').value;
  const prev = document.getElementById('feat-prev').value;
  const data = await apiFetch('/api/feature_matrix?normalize=' + norm + '&min_prevalence=' + prev);
  if (data.success) {
    document.getElementById('feat-result').innerHTML =
      '<div class="alert alert-success">Matrix: <strong>' + data.n_samples + ' samples x ' + data.n_features + ' features</strong> (normalize=' + data.normalize + ')</div>';
  } else {
    alert_div('feat-result', data);
  }
  setLoading(btn, false);
}

// ---- Classification ----
async function runClassify() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/ml/classify', 'POST', {
    model: document.getElementById('clf-model').value,
    target_column: document.getElementById('clf-target').value,
    cv_folds: parseInt(document.getElementById('clf-folds').value),
    train_filter: document.getElementById('clf-train').value,
    test_filter: document.getElementById('clf-test').value,
    normalize: document.getElementById('clf-normalize').value,
  });
  if (data.success) {
    let html = '<div class="metrics-grid">';
    html += `<div class="metric-card"><div class="val">${(data.accuracy*100).toFixed(1)}%</div><div class="lbl">Accuracy</div></div>`;
    html += `<div class="metric-card"><div class="val">${(data.f1_macro*100).toFixed(1)}%</div><div class="lbl">F1-macro</div></div>`;
    if (data.roc_auc) html += `<div class="metric-card"><div class="val">${(data.roc_auc*100).toFixed(1)}%</div><div class="lbl">ROC-AUC</div></div>`;
    html += `<div class="metric-card"><div class="val">${(data.cv_accuracy_mean*100).toFixed(1)}%</div><div class="lbl">CV Accuracy</div></div>`;
    html += '</div>';
    html += '<pre>' + (data.classification_report || '') + '</pre>';
    if (data.top_features && data.top_features.length) {
      html += '<h4 style="margin:14px 0 8px;color:var(--green)">Top Features</h4><table><thead><tr><th>Feature</th><th>Importance</th></tr></thead><tbody>';
      data.top_features.forEach(f => {
        html += '<tr><td>' + f.feature + '</td><td>' + f.importance.toFixed(6) + '</td></tr>';
      });
      html += '</tbody></table>';
    }
    document.getElementById('clf-result').innerHTML = html;
  } else {
    alert_div('clf-result', data);
  }
  setLoading(btn, false);
}

// ---- Clustering ----
async function runCluster() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/ml/cluster', 'POST', {
    method: document.getElementById('clust-method').value,
    n_clusters: parseInt(document.getElementById('clust-k').value),
    normalize: document.getElementById('clust-normalize').value,
  });
  if (data.success) {
    let html = '<div class="metrics-grid">';
    html += `<div class="metric-card"><div class="val">${data.n_clusters}</div><div class="lbl">Clusters</div></div>`;
    if (data.silhouette != null) html += `<div class="metric-card"><div class="val">${data.silhouette.toFixed(4)}</div><div class="lbl">Silhouette</div></div>`;
    if (data.davies_bouldin != null) html += `<div class="metric-card"><div class="val">${data.davies_bouldin.toFixed(4)}</div><div class="lbl">Davies-Bouldin</div></div>`;
    html += `<div class="metric-card"><div class="val">${(data.noise_fraction*100).toFixed(1)}%</div><div class="lbl">Noise</div></div>`;
    html += '</div>';
    if (data.labels && data.labels.length) {
      const dist = {};
      data.labels.forEach(l => { dist[l.cluster] = (dist[l.cluster] || 0) + 1; });
      html += '<p style="margin-top:10px;font-size:.88em">Cluster distribution: ' + Object.entries(dist).map(([k,v]) => `<span class="badge badge-green">Cluster ${k}: ${v}</span>`).join(' ') + '</p>';
    }
    document.getElementById('clust-result').innerHTML = html;
  } else {
    alert_div('clust-result', data);
  }
  setLoading(btn, false);
}

// ---- Visualization ----
async function vizTaxonomy() {
  const btn = event.target;
  setLoading(btn, true);
  const level = document.getElementById('vtax-level').value;
  const group = document.getElementById('vtax-group').value.trim();
  const url = '/api/viz/taxonomy?level=' + level + (group ? '&group_by=' + group : '');
  const data = await apiFetch(url);
  if (data.success && data.plot) {
    Plotly.newPlot('vtax-plot', data.plot.data, data.plot.layout, {responsive: true});
  } else {
    document.getElementById('vtax-plot').innerHTML = '<div class="alert alert-error">' + (data.error || 'Plot failed') + '</div>';
  }
  setLoading(btn, false);
}

async function vizPCoA() {
  const btn = event.target;
  setLoading(btn, true);
  const norm = document.getElementById('vpcoa-normalize').value;
  const color = document.getElementById('vpcoa-colorby').value.trim();
  const url = '/api/viz/pcoa?normalize=' + norm + (color ? '&color_by=' + color : '');
  const data = await apiFetch(url);
  if (data.success && data.plot) {
    Plotly.newPlot('vpcoa-plot', data.plot.data, data.plot.layout, {responsive: true});
  } else {
    document.getElementById('vpcoa-plot').innerHTML = '<div class="alert alert-error">' + (data.error || 'Plot failed') + '</div>';
  }
  setLoading(btn, false);
}

async function vizAlpha() {
  const btn = event.target;
  setLoading(btn, true);
  const metric = document.getElementById('valpha-metric').value;
  const group = document.getElementById('valpha-group').value.trim();
  const url = '/api/viz/alpha?metric=' + metric + (group ? '&group_by=' + group : '');
  const data = await apiFetch(url);
  if (data.success && data.plot) {
    Plotly.newPlot('valpha-plot', data.plot.data, data.plot.layout, {responsive: true});
  } else {
    document.getElementById('valpha-plot').innerHTML = '<div class="alert alert-error">' + (data.error || 'Plot failed') + '</div>';
  }
  setLoading(btn, false);
}

// ---- Report ----
async function generateReport() {
  const btn = event.target;
  setLoading(btn, true);
  const data = await apiFetch('/api/report', 'POST', {
    title: document.getElementById('report-title').value,
    output_path: document.getElementById('report-path').value,
  });
  if (data.success) {
    document.getElementById('report-result').innerHTML =
      '<div class="alert alert-success">Report saved: <strong>' + data.report_path + '</strong></div>';
  } else {
    alert_div('report-result', data);
  }
  setLoading(btn, false);
}

// ---- Init ----
refreshStatus();
setInterval(refreshStatus, 15000);
</script>
</body>
</html>"""


def create_app(
    config: FloraConfig | None = None,
    workdir: str | Path = "results",
) -> tuple[HTTPServer, FLORAState]:
    """Create the FLORA HTTP server and application state.

    Parameters
    ----------
    config : FloraConfig, optional
        Library configuration. Defaults to ``load_config()``.
    workdir : str or Path
        Working directory for pipeline results.

    Returns
    -------
    tuple of (HTTPServer, FLORAState)
        Configured server and state objects.
    """
    cfg = config or load_config()
    state = FLORAState(config=cfg, workdir=Path(workdir))
    handler = _make_handler(state)
    return HTTPServer, handler, state


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    config: FloraConfig | None = None,
    workdir: str | Path = "results",
    open_browser: bool = True,
) -> None:
    """Start the FLORA web interface server.

    Parameters
    ----------
    host : str
        Interface to bind to.
    port : int
        TCP port to listen on.
    config : FloraConfig, optional
        Library configuration.
    workdir : str or Path
        Working directory for pipeline results.
    open_browser : bool
        Automatically open the browser after server starts.

    Examples
    --------
    >>> from flora.ui import run_server
    >>> run_server(port=8765, workdir="results/")
    """
    setup_logging()
    cfg = config or load_config()
    state = FLORAState(config=cfg, workdir=Path(workdir))
    handler_cls = _make_handler(state)

    server = HTTPServer((host, port), handler_cls)
    url = f"http://{host}:{port}"
    logger.info("FLORA web interface: %s", url)
    print(f"\nFLORA Web Interface running at: {url}")
    print("Press Ctrl+C to stop.\n")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
