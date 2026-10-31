"""Machine learning module for FLORA microbiome analysis."""

from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.clustering.clusterer import MicrobiomeClusterer
from flora.ml.regression.regressor import MicrobiomeRegressor
from flora.ml.evaluation.metrics import evaluate_classification, evaluate_regression
from flora.ml.evaluation.benchmark import (
    BenchmarkResult,
    map_top_features_to_taxonomy,
    run_classification_benchmark,
    run_prevalence_sensitivity,
    run_rarefaction_sensitivity,
    summarize_taxonomic_signal,
)
from flora.ml.explainability.shap_analysis import SHAPAnalyzer
from flora.ml.optimization.tuner import HyperparameterTuner
from flora.ml.evaluation.bias import DataQualityReport

__all__ = [
    "MicrobiomeClassifier",
    "MicrobiomeClusterer",
    "MicrobiomeRegressor",
    "evaluate_classification",
    "evaluate_regression",
    "BenchmarkResult",
    "run_classification_benchmark",
    "run_prevalence_sensitivity",
    "run_rarefaction_sensitivity",
    "map_top_features_to_taxonomy",
    "summarize_taxonomic_signal",
    "SHAPAnalyzer",
    "HyperparameterTuner",
    "DataQualityReport",
]
