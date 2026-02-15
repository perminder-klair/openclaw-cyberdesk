"""
Logging setup for Hardware Sidecar.
Call setup_logging() once at startup, then use get_logger(name) per module.
"""

import logging

_FORMAT = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'


def setup_logging(level: str = 'INFO'):
    """Configure root logger. Call once in server.py before controller imports."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format=_FORMAT, level=numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a module."""
    return logging.getLogger(name)
