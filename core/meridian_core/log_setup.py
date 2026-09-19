"""Logging setup for the sidecar (FR-M3-09).

stdout is reserved for framed RPC, so every log record goes to stderr AND a
rotating log file under ``~/.meridian/logs/sidecar.log``. The rotating file
survives the session for post-mortem diagnostics; stderr is captured by the
extension supervisor for the output channel.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".meridian" / "logs"
LOG_FILE = LOG_DIR / "sidecar.log"


def configure_logging(level: int = logging.INFO) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]  # stderr
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
        )
    except OSError:
        # A read-only home directory must not prevent startup; stderr remains.
        logging.getLogger("meridian_core.log_setup").warning(
            "log file %s unavailable; logging to stderr only", LOG_FILE
        )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
