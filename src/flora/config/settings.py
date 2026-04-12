"""FLORA configuration model and YAML loader.

Configuration is loaded from a YAML file and validated via Pydantic. All
library components receive a FloraConfig instance rather than reading
environment variables or hardcoded constants directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """DuckDB storage configuration."""

    path: str = Field(":memory:", description="DuckDB file path or ':memory:'")
    threads: int = Field(4, ge=1, description="Number of DuckDB threads")
    memory_limit: str = Field("4GB", description="DuckDB memory limit string")
    read_only: bool = False


class PipelineConfig(BaseModel):
    """DADA2 and QIIME2 pipeline parameters."""

    trunc_len_f: int = Field(240, ge=0, description="Forward read truncation length")
    trunc_len_r: int = Field(200, ge=0, description="Reverse read truncation length")
    trim_left_f: int = Field(19, ge=0, description="Forward read left trim (primer removal)")
    trim_left_r: int = Field(20, ge=0, description="Reverse read left trim (primer removal)")
    n_threads: int = Field(4, ge=1, description="Threads for DADA2 denoising")
    taxonomy_confidence: float = Field(0.7, ge=0.0, le=1.0)
    sampling_depth: int = Field(10000, ge=1, description="Rarefaction sampling depth")


class MLConfig(BaseModel):
    """Machine learning pipeline defaults."""

    test_size: float = Field(0.2, gt=0.0, lt=1.0)
    random_state: int = 42
    cv_folds: int = Field(5, ge=2)
    n_jobs: int = Field(-1, description="Parallelism; -1 uses all cores")
    optuna_trials: int = Field(50, ge=1)
    mlflow_tracking_uri: str = "mlruns"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_file: str | None = None
    rich_output: bool = True


class StorageConfig(BaseModel):
    """Data storage paths."""

    raw_dir: str = "data/raw"
    parquet_dir: str = "data/parquet"
    results_dir: str = "results"
    classifiers_dir: str = "data/classifiers"

    @field_validator("raw_dir", "parquet_dir", "results_dir", "classifiers_dir", mode="before")
    @classmethod
    def stringify_path(cls, v: Any) -> str:
        return str(v)


class FloraConfig(BaseModel):
    """Top-level FLORA configuration.

    All library components accept a FloraConfig instance. Default values
    are production-sensible and can be overridden per project via YAML.

    Parameters
    ----------
    database : DatabaseConfig
        DuckDB connection and resource settings.
    pipeline : PipelineConfig
        DADA2 / QIIME2 processing parameters.
    ml : MLConfig
        Machine learning defaults.
    logging : LoggingConfig
        Logging level and output targets.
    storage : StorageConfig
        File system layout for raw data, Parquet files, and results.
    """

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "FloraConfig":
        """Load and validate configuration from a YAML file.

        Parameters
        ----------
        path : Path or str
            Path to the YAML configuration file.

        Returns
        -------
        FloraConfig
            Validated configuration instance.

        Raises
        ------
        FileNotFoundError
            If the YAML file does not exist.
        ValueError
            If the YAML content fails validation.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        return cls.model_validate(raw)

    def to_yaml(self, path: Path | str) -> None:
        """Serialize configuration to a YAML file.

        Parameters
        ----------
        path : Path or str
            Destination file path. Parent directories are created if needed.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            yaml.dump(self.model_dump(), fh, default_flow_style=False, allow_unicode=True)


def load_config(path: Path | str | None = None) -> FloraConfig:
    """Load FLORA configuration from a YAML file or return defaults.

    Parameters
    ----------
    path : Path or str, optional
        Path to a YAML file. If None, returns default configuration.

    Returns
    -------
    FloraConfig
        Validated configuration instance.
    """
    if path is None:
        return FloraConfig()
    return FloraConfig.from_yaml(path)
