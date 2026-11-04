"""Connect FLORA to QIIME 2 / DADA2 installed in *another* environment (usually a conda env).

FLORA rarely runs inside the QIIME 2 environment, so the executables are configured explicitly (or discovered by
looking at the usual conda locations, without starting any process). The configuration lives in
``<workdir>/engines.json`` and only ever holds paths to executables that exist.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

CONFIG_NAME = "engines.json"
KEYS = ("qiime", "python", "rscript")
_ENV_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


class EnvError(ValueError):
    """A configured path is not a usable executable."""


def _roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    roots = [home / n for n in ("miniconda3", "anaconda3", "mambaforge", "miniforge3", "micromamba", ".conda")]
    roots += [Path("/opt/conda"), Path("/opt/miniconda3"), Path("/opt/anaconda3")]
    for var in ("CONDA_PREFIX", "CONDA_EXE", "MAMBA_ROOT_PREFIX"):
        value = os.environ.get(var)
        if value:
            p = Path(value)
            roots.append(p.parent.parent if var == "CONDA_EXE" else p)
    seen: list[Path] = []
    for r in roots:
        if r not in seen and r.is_dir():
            seen.append(r)
    return seen


def _executable(path: Path) -> str | None:
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def _inspect(prefix: Path, name: str) -> dict[str, Any] | None:
    """Cheap, file-system-only check of one environment prefix."""
    bin_dir = prefix / "bin"
    qiime, python, rscript = (_executable(bin_dir / n) for n in ("qiime", "python", "Rscript"))
    site = list(prefix.glob("lib/python*/site-packages"))
    q2_python = any((s / "qiime2").is_dir() for s in site)
    dada2 = (prefix / "lib" / "R" / "library" / "dada2").is_dir()
    if not (qiime or q2_python or dada2):
        return None
    return {"name": name, "prefix": str(prefix), "qiime": qiime, "python": python if (qiime or q2_python) else None,
            "rscript": rscript, "qiime2_python_api": q2_python, "dada2_r_package": dada2}


def discover(home: Path | None = None) -> list[dict[str, Any]]:
    """Conda environments that contain QIIME 2 or R's DADA2 (looked up on disk, nothing is executed)."""
    found: list[dict[str, Any]] = []
    for root in _roots(home):
        candidates = [(root, "base"), *[(p, p.name) for p in sorted((root / "envs").glob("*")) if p.is_dir()]]
        for prefix, name in candidates:
            info = _inspect(prefix, name)
            if info and all(info["prefix"] != f["prefix"] for f in found):
                found.append(info)
    return found


def validate(config: dict[str, Any]) -> dict[str, str]:
    """Keep only known keys; every non-empty value must be an existing executable file."""
    clean: dict[str, str] = {}
    for key in KEYS:
        value = str(config.get(key) or "").strip()
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise EnvError(f"{key}: use o caminho completo (começando por /).")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise EnvError(f"{key}: '{value}' não existe ou não é executável.")
        clean[key] = str(path)
    return clean


def load(workdir: Path) -> dict[str, str]:
    path = Path(workdir) / CONFIG_NAME
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in KEYS and isinstance(v, str) and Path(v).is_file()}


def save(workdir: Path, config: dict[str, Any]) -> dict[str, str]:
    clean = validate(config)
    path = Path(workdir) / CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return clean
