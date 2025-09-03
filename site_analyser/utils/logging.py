"""Logging configuration for structured JSON logging."""

import logging
import sys
from typing import Optional

import structlog


def setup_logging(debug: bool = False, json_logs: bool = True) -> None:
    """Configure structured logging for the application."""
    
    # Set log level
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Configure processors
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    
    if json_logs:
        # JSON output for production/Kubernetes
        processors.extend([
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ])
    else:
        # Human-readable output for development
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True)
        ])
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )