"""Application logging setup.

Routes our ``app.*`` loggers to the console so stage activity (cloning,
discovery, etc.) is visible in the backend terminal alongside uvicorn's own
request logs.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a console handler to the ``app`` logger (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger = logging.getLogger("app")
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    # Don't double-log through the root logger.
    logger.propagate = False

    _CONFIGURED = True
