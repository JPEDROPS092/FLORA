"""Machine-learning UI handlers."""

from __future__ import annotations

import json
import re

from flora.core.exceptions import DatabaseError, MLError, ValidationError
from flora.ui.http import UiHttpError, json_success


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_FORBIDDEN = re.compile(r";|--|/\*|\*/|\b(drop|delete|insert|update|alter|create|attach|copy|pragma)\b", re.IGNORECASE)
_MODELS = {"random_forest", "xgboost", "svm"}


def _safe_filter(value: str, name: str) -> str:
    """The filters are interpolated into a WHERE clause: allow one plain predicate only."""
    value = (value or "").strip()
    if not value:
        raise UiHttpError(
            "Informe os filtros SQL de treino e de teste, ou use a divisão automática estratificada (split=auto) — ela separa as classes sem SQL.",
            code="missing_filters",
        )
    if _FORBIDDEN.search(value):
        raise UiHttpError(
            f"{name} precisa ser um único predicado SQL (sem ';', comentários ou comandos como DROP). Exemplo: biome = 'Amazon'.",
            code="invalid_filter",
        )
    return value


def _quote_ids(ids: list[str]) -> str:
    quoted = ", ".join("'" + str(sid).replace("'", "''") + "'" for sid in ids)
    return f"sample_id IN ({quoted})"


def _stratified_filters(state, target: str, test_size: float, seed: int) -> tuple[str, str]:
    """Build train/test SQL filters with one share of every class. Raises a Portuguese error when a class is too small."""
    from sklearn.model_selection import train_test_split

    if not _IDENT.match(str(target)):
        raise UiHttpError("A coluna alvo precisa ser um nome simples, sem espaços.", code="invalid_target")
    columns = state.db.query("SELECT * FROM samples LIMIT 0").to_polars().columns
    if target in columns:
        frame = state.db.query(f'SELECT sample_id, CAST("{target}" AS VARCHAR) AS label FROM samples').to_polars()
    else:
        frame = state.db.query(
            "SELECT sample_id, value AS label FROM sample_metadata WHERE key = ?", [target]
        ).to_polars()
    rows = [(str(sid), str(label)) for sid, label in frame.iter_rows() if label not in (None, "")]
    if len(rows) < 4:
        raise UiHttpError(
            f"A divisão estratificada precisa de pelo menos 4 amostras com valor em '{target}'. Há {len(rows)}.",
            code="insufficient_samples",
        )
    from collections import Counter

    counts = Counter(label for _, label in rows)
    small = [label for label, n in counts.items() if n < 2]
    if small:
        raise UiHttpError(
            f"A divisão estratificada precisa de pelo menos 2 amostras em cada classe de '{target}'. "
            f"Classes com uma só amostra: {', '.join(small[:8])}. Escolha outra coluna ou use filtros SQL.",
            code="insufficient_classes",
        )
    ids = [sid for sid, _ in rows]
    labels = [label for _, label in rows]
    fraction = min(0.5, max(0.1, float(test_size or 0.2)))
    train_ids, test_ids = train_test_split(ids, test_size=fraction, random_state=seed, stratify=labels)
    return _quote_ids(list(train_ids)), _quote_ids(list(test_ids))


def _fig(fig) -> dict:
    return {"status": "ok", "figure": json.loads(fig.to_json())}


def _chart_error(message: str) -> dict:
    return {"status": "empty", "error": message}


def classify(state, body: dict):
    import numpy as np
    import polars as pl
    from sklearn.metrics import confusion_matrix

    from flora.ml.classification.classifier import MicrobiomeClassifier
    from flora.projects.store import new_id, now_iso
    from flora.ui.i18n import lang_of, tr
    from flora.ui.provenance import build_provenance
    from flora.viz.ml_plots import plot_confusion_matrix, plot_feature_importance, plot_roc_curve

    lang = lang_of(body)
    try:
        model_type = body.get("model", "random_forest")
        if model_type not in _MODELS:
            raise UiHttpError(f"Unknown model: {model_type}", code="invalid_model")
        target = body.get("target_column", "biome")
        if not _IDENT.match(str(target)):
            raise UiHttpError("A coluna alvo precisa ser um nome simples, sem espaços.", code="invalid_target")
        auto = body.get("split") in {"auto", "stratified"} or (
            not str(body.get("train_filter") or "").strip() and not str(body.get("test_filter") or "").strip()
        )
        if auto:
            train_filter, test_filter = _stratified_filters(state, target, float(body.get("test_size") or 0.2), int(body.get("seed", 42)))
        else:
            train_filter = _safe_filter(body.get("train_filter", ""), "train_filter")
            test_filter = _safe_filter(body.get("test_filter", ""), "test_filter")
        cv_folds = max(2, int(body.get("cv_folds", 5)))
        seed = int(body.get("seed", 42))
        normalize = body.get("normalize", "clr")

        train, test = state.db.slice(
            train_filter=train_filter,
            test_filter=test_filter,
            features=normalize,
            target_column=target,
        )

        classifier = MicrobiomeClassifier(
            model=model_type,
            target_column=target,
            random_state=seed,
            mlflow_tracking_uri=None,
        )
        result = classifier.fit(train, test, cv_folds=cv_folds)

        scores = result.cv_scores["accuracy"]
        importances = []
        if result.feature_importances is not None:
            importances = [
                {"feature": r["feature"], "value": float(r["importance"])}
                for r in result.feature_importances.head(10).iter_rows(named=True)
            ]
        labels = [str(label) for label in result.label_encoder.classes_]
        matrix = confusion_matrix(result.y_true, result.y_pred, labels=labels).tolist()

        confusion = _chart_error("empty")
        try:
            confusion = _fig(plot_confusion_matrix(result.y_true, result.y_pred, label_names=labels, normalize=False))
        except Exception as exc:  # noqa: BLE001 - one chart must not sink the experiment
            confusion = {"status": "error", "error": str(exc)}
        roc = _chart_error(tr(lang, "ml.lim.no_proba"))
        if result.y_proba is not None:
            try:
                roc = _fig(plot_roc_curve(result))
            except Exception as exc:  # noqa: BLE001
                roc = {"status": "error", "error": str(exc)}
        importance = _chart_error(tr(lang, "ml.lim.impurity"))
        if importances:
            importance = _fig(plot_feature_importance(pl.DataFrame(importances).rename({"value": "importance"}), top_n=10))

        n_test = len(test)
        limitations = [
            tr(lang, "ml.lim.auto_split", pct=int(round(float(body.get("test_size") or 0.2) * 100))) if auto else tr(lang, "ml.lim.split"),
            tr(lang, "ml.lim.compositional"),
        ]
        if n_test < 30:
            limitations.insert(0, tr(lang, "ml.lim.small_test", n=n_test))
        if importances:
            limitations.append(tr(lang, "ml.lim.impurity"))
        if result.y_proba is None:
            limitations.append(tr(lang, "ml.lim.no_proba"))

        params = [
            {"label": tr(lang, "ml.param.model"), "value": model_type},
            {"label": tr(lang, "ml.param.target"), "value": target},
            {"label": tr(lang, "ml.param.train"), "value": train_filter},
            {"label": tr(lang, "ml.param.test"), "value": test_filter},
            {"label": "CV", "value": str(cv_folds)},
            {"label": "Seed", "value": str(seed)},
            {"label": tr(lang, "ml.param.norm"), "value": str(normalize or "none").upper()},
        ]
        stamp = now_iso()
        experiment = {
            "id": new_id(),
            "name": tr(lang, "ml.name", model=model_type, target=target),
            "model": model_type,
            "status": "completed",
            "created_at": stamp,
            "accuracy": result.accuracy,
            "f1_macro": result.f1_macro,
            "roc_auc": result.roc_auc,
            "cv_accuracy_mean": float(np.mean(scores)),
            "train_n": len(train),
            "test_n": n_test,
            "features": len(result.feature_names),
            "importance_kind": "impurity",
            "confusion": confusion,
            "roc": roc,
            "importance": importance,
            "labels": labels,
            "matrix": matrix,
            "importances": importances,
            "config": params,
            "limitations": limitations,
            "classification_report": result.classification_report_str,
            "provenance": build_provenance(
                state, seed=seed, parameters=params,
                history=[{"at": stamp[:16].replace("T", " "), "event": tr(lang, "ml.event.trained", model=model_type, seed=seed)}],
            ),
        }
        state.experiments.save(experiment)
        from flora.ui.project_progress import record_project_step

        record_project_step(state, "classify", f"{model_type} → {target}")

        # Legacy flat keys stay for existing API consumers.
        return json_success(
            data={
                "experiment": experiment,
                "model": model_type,
                "accuracy": result.accuracy,
                "f1_macro": result.f1_macro,
                "roc_auc": result.roc_auc,
                "cv_accuracy_mean": experiment["cv_accuracy_mean"],
                "classification_report": result.classification_report_str,
                "top_features": [{"feature": i["feature"], "importance": i["value"]} for i in importances],
            }
        )
    except Exception as exc:
        if isinstance(exc, UiHttpError):
            raise
        if isinstance(exc, (DatabaseError, ValidationError, ValueError, MLError)):
            raise UiHttpError(str(exc), status=400, code="ml_classification_failed") from exc
        raise


def list_experiments(state, params=None):
    """Experiments persisted for the active project, newest first."""
    return json_success(data={"experiments": state.experiments.list()})


def _cluster_frame(feature_matrix, normalize: str | None):
    """Coordinates for k-means.

    Bray–Curtis is only defined for non-negative abundances. CLR values are signed,
    and Bray–Curtis on them collapses the ordination (every sample lands on one point,
    so k=2 comes back as 1 cluster). CLR uses Euclidean distance; counts and TSS keep Bray–Curtis.
    When that ordination has no spread, clustering uses the feature matrix itself.
    """
    import numpy as np

    from flora.feature_engineering.reduction import compute_pcoa

    values = feature_matrix.drop("sample_id").to_numpy()
    signed = bool(values.size) and float(np.nanmin(values)) < 0
    metric = "euclidean" if signed or normalize == "clr" else "braycurtis"
    n = feature_matrix.height
    long = compute_pcoa(feature_matrix, metric=metric, n_components=min(5, max(2, n - 1)))
    wide = long.pivot(index="sample_id", on="component", values="value", aggregate_function="first")
    wide = wide.rename({str(c): f"PC{c}" for c in wide.columns if str(c).isdigit()})
    varying = []
    for column in [c for c in wide.columns if c != "sample_id"]:
        series = wide[column].drop_nulls()
        if series.len() and float(series.std() or 0) > 1e-8:
            varying.append(column)
    if varying:
        return wide.select(["sample_id", *varying]).fill_null(0.0), ""
    return feature_matrix, "A ordenação não separou as amostras; o agrupamento usou a matriz de features."


def cluster(state, body: dict):
    from flora.ml.clustering.clusterer import MicrobiomeClusterer
    from flora.ui.project_progress import record_project_step

    method = body.get("method", "kmeans")
    n_clusters = int(body.get("n_clusters", 4))
    normalize = body.get("normalize", "clr")

    try:
        feature_matrix = state.pipeline.get_feature_matrix(normalize=normalize)
        if len(feature_matrix) < 2:
            raise UiHttpError(
                "Clustering requires at least 2 samples in the feature matrix.",
                status=400,
                code="insufficient_samples",
            )
        if method == "kmeans" and n_clusters > len(feature_matrix):
            raise UiHttpError(
                f"k={n_clusters} é maior que o número de amostras ({len(feature_matrix)}).",
                status=400,
                code="invalid_k",
            )

        frame, embedding_note = _cluster_frame(feature_matrix, normalize)
        clusterer = MicrobiomeClusterer(
            method=method,
            n_clusters=n_clusters,
            random_state=int(body.get("seed", 42)),
        )
        result = clusterer.fit(frame)
        note = result.note or embedding_note
        record_project_step(state, "cluster", f"{method} k={result.n_clusters}")

        return json_success(
            data={
                "method": method,
                "requested_k": n_clusters,
                "n_clusters": result.n_clusters,
                "silhouette": result.silhouette,
                "davies_bouldin": result.davies_bouldin,
                "noise_fraction": result.noise_fraction,
                "note": note,
                "labels": result.labels.to_pandas().to_dict(orient="records"),
            }
        )
    except Exception as exc:
        if isinstance(exc, UiHttpError):
            raise
        if isinstance(exc, (DatabaseError, ValidationError, ValueError)):
            raise UiHttpError(str(exc), status=400, code="ml_clustering_failed") from exc
        raise
