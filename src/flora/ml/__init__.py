"""Machine learning module for FLORA microbiome analysis."""

from flora.ml.classification.classifier import MicrobiomeClassifier
from flora.ml.clustering.clusterer import MicrobiomeClusterer
from flora.ml.regression.regressor import MicrobiomeRegressor
from flora.ml.evaluation.metrics import evaluate_classification, evaluate_regression
from flora.ml.explainability.shap_analysis import SHAPAnalyzer
from flora.ml.optimization.tuner import HyperparameterTuner
from flora.ml.evaluation.bias import DataQualityReport

__all__ = [
    "MicrobiomeClassifier",
    "MicrobiomeClusterer",
    "MicrobiomeRegressor",
    "evaluate_classification",
    "evaluate_regression",
    "SHAPAnalyzer",
    "HyperparameterTuner",
    "DataQualityReport",
]
