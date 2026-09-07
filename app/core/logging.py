"""Structured JSON logging with request correlation IDs.

Phase 13/14 requirement: never log credentials, tokens, full document
content, or full conversations. Callers must pass short, non-sensitive
summaries (e.g. document_id, chunk_count) — this module does not
sanitize payloads for you; keep call sites disciplined.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    return _request_id_ctx.get()


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Helper for structured, field-based logging without leaking content.

    Usage: log_event(logger, logging.INFO, "document_ingested",
                      document_id=doc_id, chunk_count=12, duration_ms=430)
    """
    logger.log(level, message, extra={"extra_fields": fields})
