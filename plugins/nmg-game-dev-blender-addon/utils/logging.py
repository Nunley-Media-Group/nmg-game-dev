from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "nmg_game_dev_blender_addon"


def _get_logger() -> logging.Logger:
    # Log to stderr only; stdout is the MCP channel. Handler attachment is
    # guarded so repeated calls do not double-log.
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


def log_stub_invocation(op_name: str) -> None:
    _get_logger().info("%s: stub invoked", op_name)
