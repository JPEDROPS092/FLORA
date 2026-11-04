"""Which open-source engines are installed, their versions and what each can do.

Detection runs the tool's own version command with a short timeout and never raises: a missing or broken tool
is reported as unavailable with an install hint. Python libraries are probed by import.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_CACHE_SECONDS = 30
_TIMEOUT = 25


@dataclass(frozen=True)
class Engine:
    id: str
    name: str
    kind: str  # cli | r | python
    capabilities: tuple[str, ...]
    install: str
    probe: Callable[[], str | None] = field(repr=False, default=lambda: None)


#: executables chosen by the user (see :mod:`flora.engines.envs`), keyed by the command name they replace
OVERRIDES: dict[str, str] = {}


#: ``bin`` folders of the connected environments: tools installed there (vsearch, cutadapt…) are found without PATH
BIN_DIRS: list[str] = []


def configure(config: dict[str, str]) -> None:
    """Apply the saved environment: ``qiime``, ``python`` (the QIIME 2 env's) and ``rscript`` paths."""
    OVERRIDES.clear()
    BIN_DIRS[:] = list(dict.fromkeys(str(Path(v).parent) for v in config.values() if v))
    for key, command in (("qiime", "qiime"), ("rscript", "Rscript")):
        if config.get(key):
            OVERRIDES[command] = config[key]
    if config.get("python"):
        OVERRIDES["python"] = config["python"]
    _cache.clear()


def exe(name: str) -> str | None:
    """Path of *name*: the configured one, else one in a connected environment's ``bin``, else PATH."""
    if OVERRIDES.get(name):
        return OVERRIDES[name]
    for folder in BIN_DIRS:
        candidate = Path(folder) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which(name)


def resolve_cmd(cmd: list[str]) -> list[str]:
    """Replace a bare ``qiime`` / ``Rscript`` / ``vsearch`` … by its configured path."""
    if not cmd:
        return cmd
    found = exe(cmd[0]) if cmd[0] in {"qiime", "Rscript", "vsearch", "cutadapt"} else None
    return [found or cmd[0], *cmd[1:]]


def skbio_python() -> str | None:
    """A Python that can ``import skbio``: FLORA's own, else the ``python`` of a connected environment."""
    import sys

    candidates = [sys.executable, OVERRIDES.get("python")]
    candidates += [str(Path(d) / "python") for d in BIN_DIRS]
    for candidate in dict.fromkeys(c for c in candidates if c):
        if Path(candidate).is_file() and _run([candidate, "-c", "import skbio; print(skbio.__version__)"]):
            return candidate
    return None


def _skbio() -> str | None:
    python = skbio_python()
    return _run([python, "-c", "import skbio; print(skbio.__version__)"]) if python else None


def qiime_python() -> str | None:
    """Python interpreter that can ``import qiime2``: the configured one, else FLORA's own."""
    import sys

    for candidate in (OVERRIDES.get("python"), sys.executable):
        if candidate and _run([candidate, "-c", "import qiime2; print(qiime2.__version__)"]):
            return candidate
    return None


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if out.returncode == 0 and text else None


def _cli(binary: str, *args: str) -> Callable[[], str | None]:
    def probe() -> str | None:
        path = exe(binary)
        return _run([path, *args]) if path else None

    return probe


def _qiime2() -> str | None:
    """QIIME 2 through its CLI, or (when there is no CLI) through the Python API of a configured interpreter."""
    version = _cli("qiime", "--version")()
    if version:
        return version
    python = qiime_python()
    return _run([python, "-c", "import qiime2; print('QIIME 2 ' + qiime2.__version__ + ' (API Python)')"]) if python else None


def _r_package(package: str) -> Callable[[], str | None]:
    def probe() -> str | None:
        rscript = exe("Rscript")
        if not rscript:
            return None
        return _run([rscript, "--vanilla", "-e", f'cat(as.character(packageVersion("{package}")))'])

    return probe


def _py(module: str) -> Callable[[], str | None]:
    def probe() -> str | None:
        try:
            return str(getattr(importlib.import_module(module), "__version__", "installed"))
        except Exception:  # noqa: BLE001 - a broken import is "not available"
            return None

    return probe


ENGINES: dict[str, Engine] = {e.id: e for e in (
    Engine("qiime2", "QIIME 2", "cli", ("import", "denoise", "classify", "phylogeny", "unifrac", "export"),
           "Instale o QIIME 2 num ambiente conda (https://docs.qiime2.org/) e aponte o FLORA para ele em Ambientes, ou inicie o FLORA com esse ambiente ativo.", _qiime2),
    Engine("dada2", "DADA2 (R)", "r", ("denoise",),
           "Instale R e o pacote: BiocManager::install('dada2').", _r_package("dada2")),
    Engine("aldex2", "ALDEx2 (R)", "r", ("differential",),
           "Instale R e o pacote: BiocManager::install('ALDEx2').", _r_package("ALDEx2")),
    Engine("ancombc2", "ANCOM-BC2 (R)", "r", ("differential",),
           "Instale R e o pacote: BiocManager::install('ANCOMBC').", _r_package("ANCOMBC")),
    Engine("vegan", "vegan (R)", "r", ("permanova", "ordination"),
           "Instale R e o pacote: install.packages('vegan').", _r_package("vegan")),
    Engine("vsearch", "VSEARCH", "cli", ("cluster", "chimera"),
           "conda install -c bioconda vsearch", _cli("vsearch", "--version")),
    Engine("cutadapt", "cutadapt", "cli", ("trim",),
           "pip install cutadapt", _cli("cutadapt", "--version")),
    Engine("skbio", "scikit-bio", "python", ("unifrac", "permanova", "diversity"),
           "pip install scikit-bio, ou conecte o ambiente que o contém (scripts/setup_engines.sh)", _skbio),
)}

_cache: dict[str, tuple[float, str | None]] = {}


def detect(engine_id: str, *, fresh: bool = False) -> str | None:
    """Version string when the engine works, else ``None``. Cached briefly because probes spawn processes."""
    engine = ENGINES[engine_id]
    now = time.monotonic()
    hit = _cache.get(engine_id)
    if hit and not fresh and now - hit[0] < _CACHE_SECONDS:
        return hit[1]
    version = engine.probe()
    _cache[engine_id] = (now, version)
    return version


def detect_all(*, fresh: bool = False) -> list[dict]:
    out = []
    for engine in ENGINES.values():
        version = detect(engine.id, fresh=fresh)
        out.append({
            "id": engine.id, "name": engine.name, "kind": engine.kind, "capabilities": list(engine.capabilities),
            "available": version is not None, "version": version or "", "install": "" if version else engine.install,
        })
    return out
