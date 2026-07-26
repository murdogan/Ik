"""Pure ASGI correlation middleware and request-context state helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from math import isfinite
from time import monotonic
from typing import Any, Protocol, cast
from uuid import uuid4

from fastapi.routing import RouteContext, iter_route_contexts
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.observability.operational import (
    configure_operational_logger,
    log_http_request_completed,
)
from app.platform.request_context import (
    RequestContext,
    is_valid_request_id,
    is_valid_trace_id,
)

REQUEST_CONTEXT_STATE_KEY = "request_context"
REQUEST_ID_HEADER = "X-Request-Id"
TRACE_ID_HEADER = "X-Trace-Id"
CORRELATION_ID_HEADER = "X-Correlation-Id"

_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("ascii")
_TRACE_ID_HEADER_BYTES = TRACE_ID_HEADER.lower().encode("ascii")
_CORRELATION_ID_HEADER_BYTES = CORRELATION_ID_HEADER.lower().encode("ascii")
_CORRELATION_RESPONSE_HEADER_NAMES = frozenset(
    {
        _REQUEST_ID_HEADER_BYTES,
        _TRACE_ID_HEADER_BYTES,
        _CORRELATION_ID_HEADER_BYTES,
    }
)
_LOGGER = configure_operational_logger()

type IdFactory = Callable[[], str]
type ScopeTarget = MutableMapping[str, Any] | HasScope


class HasScope(Protocol):
    """Structural type implemented by Starlette Request and HTTPConnection."""

    @property
    def scope(self) -> MutableMapping[str, Any]: ...


class CorrelationMiddleware:
    """Validate/generate opaque IDs, bind context, and propagate canonical headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        request_id_factory: IdFactory = lambda: uuid4().hex,
        trace_id_factory: IdFactory = lambda: uuid4().hex,
        logger: logging.Logger | None = _LOGGER,
        service: str = "IK Platform API",
        version: str = "0.1.0",
        commit_sha: str = "development",
        routes: Sequence[BaseRoute | RouteContext] | None = None,
    ) -> None:
        self._app = app
        self._request_id_factory = request_id_factory
        self._trace_id_factory = trace_id_factory
        self._logger = logger
        self._service = service
        self._version = version
        self._commit_sha = commit_sha
        self._routes = tuple(iter_route_contexts(routes)) if routes is not None else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started_at = monotonic()
        status_code = 500
        safe_metadata: Mapping[str, str] | None = None

        try:
            context = get_or_create_request_context(
                scope,
                request_id_factory=self._request_id_factory,
                trace_id_factory=self._trace_id_factory,
            )
            safe_metadata = context.safe_error_metadata()

            async def send_with_correlation(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    candidate_status = message["status"]
                    status_code = (
                        candidate_status
                        if isinstance(candidate_status, int)
                        and not isinstance(candidate_status, bool)
                        and 100 <= candidate_status <= 599
                        else 500
                    )
                    message = dict(message)
                    existing_headers = message.get("headers", [])
                    headers = [
                        (name, value)
                        for name, value in existing_headers
                        if name.lower() not in _CORRELATION_RESPONSE_HEADER_NAMES
                    ]
                    headers.extend(correlation_response_headers(context))
                    message["headers"] = headers
                await send(message)

            await self._app(scope, receive, send_with_correlation)
        except BaseException:
            status_code = 500
            raise
        finally:
            if self._logger is not None:
                final_metadata = safe_metadata or _fallback_correlation_metadata()
                log_http_request_completed(
                    self._logger,
                    service=self._service,
                    version=self._version,
                    commit_sha=self._commit_sha,
                    request_id=final_metadata["request_id"],
                    trace_id=final_metadata["trace_id"],
                    http_method=_safe_http_method(scope.get("method")),
                    http_route=_route_template(scope, routes=self._routes),
                    http_status_code=status_code,
                    duration_ms=_elapsed_milliseconds(started_at),
                )


def get_or_create_request_context(
    target: ScopeTarget,
    *,
    request_id_factory: IdFactory = lambda: uuid4().hex,
    trace_id_factory: IdFactory = lambda: uuid4().hex,
) -> RequestContext:
    """Return bound context or create one from untrusted ASGI request headers."""

    scope = _coerce_scope(target)
    state = _state(scope)
    existing = state.get(REQUEST_CONTEXT_STATE_KEY)
    if existing is not None:
        if not isinstance(existing, RequestContext):
            raise RuntimeError("Request context state contains an unexpected value")
        return existing

    request_values = _header_values(scope, _REQUEST_ID_HEADER_BYTES)
    correlation_values = _header_values(scope, _CORRELATION_ID_HEADER_BYTES)
    trace_values = _header_values(scope, _TRACE_ID_HEADER_BYTES)
    request_id = _resolve_request_id(
        request_values,
        correlation_values,
        factory=request_id_factory,
    )
    trace_id = _resolve_single_id(
        trace_values,
        validator=is_valid_trace_id,
        factory=trace_id_factory,
        field_name="trace_id",
    )
    context = RequestContext(request_id=request_id, trace_id=trace_id)
    state[REQUEST_CONTEXT_STATE_KEY] = context
    return context


def bind_request_context(target: ScopeTarget, context: RequestContext) -> RequestContext:
    """Bind an initial trusted context to state."""

    if not isinstance(context, RequestContext):
        raise TypeError("context must be a RequestContext")
    _state(_coerce_scope(target))[REQUEST_CONTEXT_STATE_KEY] = context
    return context


def replace_request_context(target: ScopeTarget, context: RequestContext) -> RequestContext:
    """Replace state with an enrichment while keeping correlation IDs invariant."""

    if not isinstance(context, RequestContext):
        raise TypeError("context must be a RequestContext")
    current = get_request_context(target)
    if (context.request_id, context.trace_id) != (current.request_id, current.trace_id):
        raise ValueError("Replacement context must preserve request_id and trace_id")
    return bind_request_context(target, context)


def get_request_context(target: ScopeTarget) -> RequestContext:
    """Read the immutable context previously bound by the middleware."""

    value = _state(_coerce_scope(target)).get(REQUEST_CONTEXT_STATE_KEY)
    if not isinstance(value, RequestContext):
        raise RuntimeError("Request context has not been initialized")
    return value


def correlation_response_headers(context: RequestContext) -> tuple[tuple[bytes, bytes], ...]:
    """Return the safe canonical response headers, including the Phase 0 alias."""

    request_id = context.request_id.encode("ascii")
    return (
        (_REQUEST_ID_HEADER_BYTES, request_id),
        (_TRACE_ID_HEADER_BYTES, context.trace_id.encode("ascii")),
        (_CORRELATION_ID_HEADER_BYTES, request_id),
    )


def _coerce_scope(target: ScopeTarget) -> MutableMapping[str, Any]:
    if isinstance(target, MutableMapping):
        return target
    scope = target.scope
    if not isinstance(scope, MutableMapping):  # pragma: no cover - Starlette contract guard
        raise TypeError("target.scope must be mutable")
    return scope


def _state(scope: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    existing = scope.get("state")
    if existing is None:
        state: MutableMapping[str, Any] = {}
        scope["state"] = state
        return state
    if not isinstance(existing, MutableMapping):
        raise RuntimeError("ASGI scope state must be a mutable mapping")
    return existing


def _header_values(scope: Mapping[str, Any], name: bytes) -> tuple[str | None, ...]:
    values: list[str | None] = []
    raw_headers = scope.get("headers", ())
    if not isinstance(raw_headers, (list, tuple)):
        return (None,)
    for raw_name, raw_value in raw_headers:
        if not isinstance(raw_name, bytes) or not isinstance(raw_value, bytes):
            return (None,)
        if raw_name.lower() != name:
            continue
        try:
            values.append(raw_value.decode("ascii"))
        except UnicodeDecodeError:
            values.append(None)
    return tuple(values)


def _resolve_request_id(
    request_values: tuple[str | None, ...],
    correlation_values: tuple[str | None, ...],
    *,
    factory: IdFactory,
) -> str:
    # Repeated instances are ambiguous even when their byte values happen to match.
    if len(request_values) > 1 or len(correlation_values) > 1:
        return _generated_id(factory, is_valid_request_id, "request_id")

    request_id = request_values[0] if request_values else None
    correlation_id = correlation_values[0] if correlation_values else None
    if request_values and correlation_values:
        if (
            request_id == correlation_id
            and is_valid_request_id(request_id)
            and is_valid_request_id(correlation_id)
        ):
            return cast(str, request_id)
        return _generated_id(factory, is_valid_request_id, "request_id")

    candidate = request_id if request_values else correlation_id
    if is_valid_request_id(candidate):
        return cast(str, candidate)
    return _generated_id(factory, is_valid_request_id, "request_id")


def _resolve_single_id(
    values: tuple[str | None, ...],
    *,
    validator: Callable[[object], bool],
    factory: IdFactory,
    field_name: str,
) -> str:
    if len(values) == 1 and validator(values[0]):
        return cast(str, values[0])
    return _generated_id(factory, validator, field_name)


def _generated_id(
    factory: IdFactory,
    validator: Callable[[object], bool],
    field_name: str,
) -> str:
    generated = factory()
    if not validator(generated):
        raise RuntimeError(f"{field_name} factory produced an invalid identifier")
    return generated


def _safe_http_method(value: object) -> str:
    if not isinstance(value, str) or not value.isascii() or not value.isalpha():
        return "UNKNOWN"
    return value.upper()[:16]


def _route_template(
    scope: Mapping[str, Any],
    *,
    routes: Sequence[RouteContext] | None = None,
) -> str:
    route = scope.get("route")
    if isinstance(route, BaseRoute):
        if routes is None:
            template = getattr(route, "path", None)
            return template if isinstance(template, str) else "unmatched"
        owned_route_contexts = [
            route_context
            for route_context in routes
            if route_context.original_route is route and isinstance(route_context.path, str)
        ]
        if len(owned_route_contexts) == 1:
            return cast(str, owned_route_contexts[0].path)

    if routes is None:
        return "unmatched"
    endpoint = scope.get("endpoint")
    if endpoint is None:
        return "unmatched"
    endpoint_route_contexts = [
        route_context
        for route_context in routes
        if route_context.endpoint is endpoint and isinstance(route_context.path, str)
    ]
    if len(endpoint_route_contexts) != 1:
        return "unmatched"
    return cast(str, endpoint_route_contexts[0].path)


def _fallback_correlation_metadata() -> Mapping[str, str]:
    return {
        "request_id": uuid4().hex,
        "trace_id": uuid4().hex,
    }


def _elapsed_milliseconds(started_at: float) -> float:
    elapsed_ms = (monotonic() - started_at) * 1000
    if not isfinite(elapsed_ms) or elapsed_ms < 0:
        return 0.0
    return round(elapsed_ms, 3)


__all__ = [
    "CORRELATION_ID_HEADER",
    "REQUEST_CONTEXT_STATE_KEY",
    "REQUEST_ID_HEADER",
    "TRACE_ID_HEADER",
    "CorrelationMiddleware",
    "bind_request_context",
    "correlation_response_headers",
    "get_or_create_request_context",
    "get_request_context",
    "is_valid_request_id",
    "is_valid_trace_id",
    "replace_request_context",
]
