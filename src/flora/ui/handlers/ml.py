"""Machine-learning UI handlers."""

from __future__ import annotations

from flora.core.exceptions import DatabaseError, ValidationError
from flora.ui.http import UiHttpError, json_success


def classify(state, body: dict):
    from flora.ml.classification.classifier import MicrobiomeClassifier

    try:
        model_type = body.get("model", "random_forest")
        target = body.get("target_column", "biome")
        train_filter = body.get("train_filter", "")
        test_filter = body.get("test_filter", "")
        cv_folds = int(body.get("cv_folds", 5))
        normalize = body.get("normalize", "clr")

        if not train_filter or not test_filter:
            raise UiHttpError(
                "train_filter and test_filter are required",
                code="missing_filters",
            )

        train, test = state.db.slice(
            train_filter=train_filter,
            test_filter=test_filter,
            features=normalize,
            target_column=target,
        )

        classifier = MicrobiomeClassifier(
            model=model_type,
            target_column=target,
            random_state=42,
            mlflow_tracking_uri=None,
        )
        result = classifier.fit(train, test, cv_folds=cv_folds)

        scores = result.cv_scores["accuracy"]
        top_features = []
        if result.feature_importances is not None:
            top_features = result.feature_importances.head(10).to_pandas().to_dict(orient="records")

        return json_success(
            data={
                "model": model_type,
                "accuracy": result.accuracy,
                "f1_macro": result.f1_macro,
                "roc_auc": result.roc_auc,
                "cv_accuracy_mean": sum(scores) / len(scores),
                "classification_report": result.classification_report_str,
                "top_features": top_features,
            }
        )
    except Exception as exc:
        if isinstance(exc, (DatabaseError, ValidationError, ValueError)):
            raise UiHttpError(str(exc), status=400, code="ml_classification_failed") from exc
        raise


def cluster(state, body: dict):
    from flora.feature_engineering.reduction import compute_pcoa
    from flora.ml.clustering.clusterer import MicrobiomeClusterer

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

        pcoa_long = compute_pcoa(feature_matrix, metric="braycurtis", n_components=2)
        if pcoa_long.is_empty():
            raise UiHttpError(
                "PCoA returned no coordinates for clustering.",
                status=400,
                code="empty_embedding",
            )

        pcoa_wide = pcoa_long.pivot(
            index="sample_id",
            on="component",
            values="value",
            aggregate_function="first",
        ).rename({"1": "PC1", "2": "PC2"})

        clusterer = MicrobiomeClusterer(
            method=method,
            n_clusters=n_clusters,
            random_state=42,
        )
        result = clusterer.fit(pcoa_wide)

        return json_success(
            data={
                "method": method,
                "n_clusters": result.n_clusters,
                "silhouette": result.silhouette,
                "davies_bouldin": result.davies_bouldin,
                "noise_fraction": result.noise_fraction,
                "labels": result.labels.to_pandas().to_dict(orient="records"),
            }
        )
    except Exception as exc:
        if isinstance(exc, UiHttpError):
            raise
        if isinstance(exc, (DatabaseError, ValidationError, ValueError)):
            raise UiHttpError(str(exc), status=400, code="ml_clustering_failed") from exc
        raise
