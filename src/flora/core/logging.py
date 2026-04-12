"""Centralized logging configuration for the FLORA library.

All modules should obtain loggers via ``get_logger(__name__)`` rather than
calling ``logging.getLogger`` directly. This ensures consistent formatting,
handler configuration, and level propagation across the library.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_configured: bool = False


def setup_logging(
    level: LogLevel = "INFO",
    log_file: Path | str | None = None,
    rich_output: bool = True,
) -> None:
    """Configure the FLORA root logger.

    Should be called once at application startup. Safe to call multiple times;
    subsequent calls reconfigure the existing handlers.

    Parameters
    ----------
    level : str
        Logging level for all FLORA loggers. One of DEBUG, INFO, WARNING,
        ERROR, CRITICAL.
    log_file : Path or str, optional
        If provided, also write logs to this file in addition to stdout.
    rich_output : bool
        Use rich-formatted console output when rich is available.
    """
    global _configured

    root = logging.getLogger("flora")
    root.setLevel(getattr(logging, level))
    root.handlers.clear()

    if rich_output:
        try:
            from rich.logging import RichHandler

            handler: logging.Handler = RichHandler(
                rich_tracebacks=True,
                show_time=True,
                show_path=False,
            )
            handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
        except ImportError:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(_FORMATTER)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_FORMATTER)

    root.addHandler(handler)

    if log_file is not None:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(_FORMATTER)
        root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the FLORA hierarchy.

    Parameters
    ----------
    name : str
        Typically ``__name__`` of the calling module.

    Returns
    -------
    logging.Logger
        Logger scoped to ``flora.<name>``.
    """
    if not _configured:
        setup_logging()

    if name.startswith("flora"):
        return logging.getLogger(name)
    return logging.getLogger(f"flora.{name}")
