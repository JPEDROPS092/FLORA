"""Which open-source engines are installed, their versions and what each can do.

Detection runs the tool's own version command with a short timeout and never raises: a missing or broken tool
is reported as unavailable with an install hint. Python libraries are probed by import.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import time
from dataclasses import dataclass, field
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


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if out.returncode == 0 and text else None


def _cli(binary: str, *args: str) -> Callable[[], str | None]:
    def probe() -> str | None:
        return _run([binary, *args]) if shutil.which(binary) else None

    return probe


def _r_package(package: str) -> Callable[[], str | None]:
    def probe() -> str | None:
        if not shutil.which("Rscript"):
            return None
        return _run(["Rscript", "--vanilla", "-e", f'cat(as.character(packageVersion("{package}")))'])

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
           "Instale o QIIME 2 num ambiente conda (https://docs.qiime2.org/) e inicie o FLORA com esse ambiente ativo.", _cli("qiime", "--version")),
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
           "pip install scikit-bio", _py("skbio")),
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
