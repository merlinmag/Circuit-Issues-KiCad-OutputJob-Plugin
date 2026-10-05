"""Logging utilities for the KiCad post-design automation plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def get_logger(name: str = "kicad_library_automation", log_file: Optional[Path] = None) -> logging.Logger:
    """Create or return a configured logger instance.

    The console handler is added once. When ``log_file`` is given, the logger writes to
    that file (replacing a file handler from an earlier run that pointed elsewhere).
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(_FORMAT)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if log_file is not None:
        target = str(Path(log_file).resolve())
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                if handler.baseFilename == target:
                    return logger
                logger.removeHandler(handler)
                handler.close()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def close_file_handlers(logger: logging.Logger) -> None:
    """Flush and detach file handlers (releases the log file, e.g. on Windows)."""
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()
