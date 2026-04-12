"""Tests for FLORA configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest
import yaml

from flora.config.settings import (
    DatabaseConfig,
    FloraConfig,
    MLConfig,
    PipelineConfig,
    load_config,
)


def test_default_config():
    cfg = FloraConfig()
    assert cfg.database.path == ":memory:"
    assert cfg.pipeline.n_threads == 4
    assert cfg.ml.random_state == 42
    assert cfg.logging.level == "INFO"


def test_load_config_none_returns_defaults():
    cfg = load_config(None)
    assert isinstance(cfg, FloraConfig)


def test_load_config_from_yaml():
    data = {
        "database": {"path": "test.duckdb", "threads": 2},
        "ml": {"random_state": 7, "cv_folds": 3},
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(data, f)
        path = f.name

    cfg = load_config(path)
    assert cfg.database.path == "test.duckdb"
    assert cfg.database.threads == 2
    assert cfg.ml.random_state == 7
    assert cfg.ml.cv_folds == 3

    Path(path).unlink()


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_config_roundtrip():
    cfg = FloraConfig()
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = Path(f.name)

    cfg.to_yaml(path)
    loaded = FloraConfig.from_yaml(path)
    assert loaded.database.path == cfg.database.path
    assert loaded.ml.random_state == cfg.ml.random_state

    path.unlink()


def test_pipeline_config_validation():
    with pytest.raises(Exception):
        PipelineConfig(taxonomy_confidence=1.5)


def test_database_config_defaults():
    db_cfg = DatabaseConfig()
    assert db_cfg.threads >= 1
    assert "GB" in db_cfg.memory_limit


def test_ml_config_test_size_validation():
    with pytest.raises(Exception):
        MLConfig(test_size=1.5)
    with pytest.raises(Exception):
        MLConfig(test_size=0.0)
