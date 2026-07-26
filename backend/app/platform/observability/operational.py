"""Finite, PII-free JSON signals for API and worker process operations."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from math import isfinite
from threading import Lock
from typing import Literal

OPERATIONAL_LOGGER_NAME = "ik.operational"

_HTTP_REQUEST_COMPLETED = "http.request.completed"
_WORKER_STARTED = "worker.started"
_WORKER_HEARTBEAT = "worker.heartbeat"
_WORKER_FAILED = "worker.failed"
_WORKER_STOPPED = "worker.stopped"

_COMMON_FIELDS = (
    "timestamp",
    "level",
    "event",
    "service",
    "version",
    "commit_sha",
)
_EVENT_FIELDS = {
    _HTTP_REQUEST_COMPLETED: _COMMON_FIELDS
    + (
        "request_id",
        "trace_id",
        "http_method",
        "http_route",
        "http_status_code",
        "duration_ms",
    ),
    _WORKER_STARTED: _COMMON_FIELDS + ("worker",),
    _WORKER_HEARTBEAT: _COMMON_FIELDS
    + (
        "worker",
        "cycle_duration_ms",
        "processed_count",
    ),
    _WORKER_FAILED: (
        "timestamp",
        "level",
        "event",
        "worker",
        "error_class",
    ),
    _WORKER_STOPPED: _COMMON_FIELDS + ("worker",),
}
_EVENT_LEVELS = {
    _HTTP_REQUEST_COMPLETED: "INFO",
    _WORKER_STARTED: "INFO",
    _WORKER_HEARTBEAT: "INFO",
    _WORKER_FAILED: "ERROR",
    _WORKER_STOPPED: "INFO",
}
_STRING_FIELDS = frozenset(
    {
        "service",
        "version",
        "commit_sha",
        "request_id",
        "trace_id",
        "http_method",
        "http_route",
        "worker",
        "error_class",
    }
)
_HANDLER_MARKER = "_ik_operational_json_handler"
_FILTER_MARKER = "_ik_operational_event_filter"
_CONFIGURE_LOCK = Lock()
_WORKER_NAMES = frozenset({"notifications", "reporting"})

type WorkerName = Literal["notifications", "reporting"]


class _OperationalEventFilter(logging.Filter):
    """Drop records that did not pass through the finite operational API."""

    def filter(self, record: logging.LogRecord) -> bool:
        event = getattr(record, "event", None)
        return isinstance(event, str) and event in _EVENT_FIELDS


class _OperationalJsonFormatter(logging.Formatter):
    """Render only the explicit field tuple assigned to a known event code."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if not isinstance(event, str) or event not in _EVENT_FIELDS:
            return ""

        values: dict[str, str | int | float] = {}
        for field_name in _EVENT_FIELDS[event]:
            if field_name == "timestamp":
                values[field_name] = _utc_timestamp(record.created)
            elif field_name == "level":
                values[field_name] = _EVENT_LEVELS[event]
            elif field_name == "event":
                values[field_name] = event
            else:
                values[field_name] = _safe_record_value(record, field_name)
        return json.dumps(
            values,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )


def configure_operational_logger() -> logging.Logger:
    """Return the dedicated operational logger with exactly one owned JSON handler."""

    logger = logging.getLogger(OPERATIONAL_LOGGER_NAME)
    with _CONFIGURE_LOCK:
        logger.disabled = False
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for logger_filter in tuple(logger.filters):
            logger.removeFilter(logger_filter)

        owned_handlers = [
            handler for handler in logger.handlers if getattr(handler, _HANDLER_MARKER, False)
        ]
        if owned_handlers:
            handler = owned_handlers[0]
        else:
            handler = logging.StreamHandler()
            setattr(handler, _HANDLER_MARKER, True)
            logger.addHandler(handler)

        for existing_handler in tuple(logger.handlers):
            if existing_handler is handler:
                continue
            logger.removeHandler(existing_handler)
            if getattr(existing_handler, _HANDLER_MARKER, False):
                existing_handler.close()

        handler.setLevel(logging.INFO)
        handler.setFormatter(_OperationalJsonFormatter())
        for existing_filter in tuple(handler.filters):
            handler.removeFilter(existing_filter)
        event_filter = _OperationalEventFilter()
        setattr(event_filter, _FILTER_MARKER, True)
        handler.addFilter(event_filter)
    return logger


def log_http_request_completed(
    logger: logging.Logger,
    *,
    service: str,
    version: str,
    commit_sha: str,
    request_id: str,
    trace_id: str,
    http_method: str,
    http_route: str,
    http_status_code: int,
    duration_ms: int | float,
) -> None:
    """Emit the sole finite request-completion event."""

    _emit(
        logger,
        logging.INFO,
        _HTTP_REQUEST_COMPLETED,
        service=service,
        version=version,
        commit_sha=commit_sha,
        request_id=request_id,
        trace_id=trace_id,
        http_method=http_method,
        http_route=http_route,
        http_status_code=_http_status_code(http_status_code),
        duration_ms=_duration_ms(duration_ms),
    )


def log_worker_started(
    logger: logging.Logger,
    *,
    service: str,
    version: str,
    commit_sha: str,
    worker: WorkerName,
) -> None:
    """Emit a worker process-start signal."""

    _emit_worker(
        logger,
        logging.INFO,
        _WORKER_STARTED,
        service=service,
        version=version,
        commit_sha=commit_sha,
        worker=worker,
    )


def log_worker_heartbeat(
    logger: logging.Logger,
    *,
    service: str,
    version: str,
    commit_sha: str,
    worker: WorkerName,
    cycle_duration_ms: int | float,
    processed_count: int,
) -> None:
    """Emit a bounded worker heartbeat with aggregate cycle information."""

    _emit_worker(
        logger,
        logging.INFO,
        _WORKER_HEARTBEAT,
        service=service,
        version=version,
        commit_sha=commit_sha,
        worker=worker,
        cycle_duration_ms=_duration_ms(cycle_duration_ms),
        processed_count=_processed_count(processed_count),
    )


def log_worker_failed(
    logger: logging.Logger,
    *,
    worker: WorkerName,
    error: BaseException,
) -> None:
    """Emit a fatal worker signal containing only its exception class name."""

    if worker not in _WORKER_NAMES:
        raise ValueError("worker must be notifications or reporting")
    logger.error(
        _WORKER_FAILED,
        extra={
            "event": _WORKER_FAILED,
            "worker": worker,
            "error_class": type(error).__name__,
        },
    )


def log_worker_stopped(
    logger: logging.Logger,
    *,
    service: str,
    version: str,
    commit_sha: str,
    worker: WorkerName,
) -> None:
    """Emit a worker process-stop signal."""

    _emit_worker(
        logger,
        logging.INFO,
        _WORKER_STOPPED,
        service=service,
        version=version,
        commit_sha=commit_sha,
        worker=worker,
    )


def _emit_worker(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    service: str,
    version: str,
    commit_sha: str,
    worker: WorkerName,
    **fields: str | int | float,
) -> None:
    if worker not in _WORKER_NAMES:
        raise ValueError("worker must be notifications or reporting")
    _emit(
        logger,
        level,
        event,
        service=service,
        version=version,
        commit_sha=commit_sha,
        worker=worker,
        **fields,
    )


def _emit(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    service: str,
    version: str,
    commit_sha: str,
    **fields: str | int | float,
) -> None:
    if event not in _EVENT_FIELDS:
        raise ValueError("Unknown operational event")
    extra: dict[str, str | int | float] = {
        "event": event,
        "service": _required_text("service", service),
        "version": _required_text("version", version),
        "commit_sha": _required_text("commit_sha", commit_sha),
        **fields,
    }
    if level == logging.ERROR:
        logger.error(event, extra=extra)
    else:
        logger.info(event, extra=extra)


def _required_text(field_name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _http_status_code(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        raise ValueError("http_status_code must be an integer from 100 through 599")
    return value


def _duration_ms(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("duration must be an integer or float")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError("duration must be finite and non-negative")
    return round(normalized, 3)


def _processed_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("processed_count must be a non-negative integer")
    return value


def _safe_record_value(record: logging.LogRecord, field_name: str) -> str | int | float:
    value = getattr(record, field_name, None)
    if field_name in _STRING_FIELDS:
        return value if isinstance(value, str) else "unknown"
    if field_name == "http_status_code":
        return value if isinstance(value, int) and not isinstance(value, bool) else 500
    if field_name == "processed_count":
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    if field_name in {"duration_ms", "cycle_duration_ms"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        normalized = float(value)
        return normalized if isfinite(normalized) and normalized >= 0 else 0.0
    return "unknown"


def _utc_timestamp(created: float) -> str:
    try:
        timestamp = datetime.fromtimestamp(created, UTC)
    except (OverflowError, OSError, ValueError):
        timestamp = datetime.now(UTC)
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "OPERATIONAL_LOGGER_NAME",
    "WorkerName",
    "configure_operational_logger",
    "log_http_request_completed",
    "log_worker_failed",
    "log_worker_heartbeat",
    "log_worker_started",
    "log_worker_stopped",
]
