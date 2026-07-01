"""
Thin logging helper — returns a named stdlib logger.

Usage:
    from transformer.util.logging import get_logger
    log = get_logger(__name__)
    log.warning("something went wrong")
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a Logger namespaced under 'transformer.<name>'."""
    return logging.getLogger(f"transformer.{name}")
