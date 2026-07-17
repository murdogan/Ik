"""Pure ASGI request-body limits for narrowly scoped streaming endpoints."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.errors import ApiError, api_error_handler


class _RequestBodyLimitExceeded(RuntimeError):
    pass


class RequestBodyLimitMiddleware:
    """Reject dishonest or oversized bodies before form parsing can spool them."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        method: str,
        path: str,
        maximum_bytes: int,
        error_code: str,
        error_message: str,
    ) -> None:
        if maximum_bytes < 1:
            raise ValueError("maximum_bytes must be positive")
        self._app = app
        self._method = method.upper()
        self._path = path
        self._maximum_bytes = maximum_bytes
        self._error_code = error_code
        self._error_message = error_message

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != self._method
            or scope.get("path") != self._path
        ):
            await self._app(scope, receive, send)
            return

        declared, valid_declaration = _content_length(scope)
        if (
            not valid_declaration
            or (declared is not None and (declared < 1 or declared > self._maximum_bytes))
        ):
            await self._reject(scope, receive, send)
            return

        received = 0
        response_started = False

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if (
                    received > self._maximum_bytes
                    or (declared is not None and received > declared)
                    or (
                        declared is not None
                        and not message.get("more_body", False)
                        and received != declared
                    )
                ):
                    raise _RequestBodyLimitExceeded
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, bounded_receive, tracked_send)
        except _RequestBodyLimitExceeded:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = await api_error_handler(
            Request(scope),
            ApiError(
                status_code=413,
                code=self._error_code,
                message=self._error_message,
            ),
        )
        await response(scope, receive, send)


def _content_length(scope: Scope) -> tuple[int | None, bool]:
    values: list[bytes] = []
    for name, value in scope.get("headers", ()):
        if name.lower() == b"content-length":
            values.append(value)
    if not values:
        return None, True
    if len(values) != 1:
        return None, False
    try:
        rendered = values[0].decode("ascii")
        if not rendered.isdecimal():
            return None, False
        return int(rendered), True
    except (UnicodeDecodeError, ValueError):
        return None, False


__all__ = ["RequestBodyLimitMiddleware"]
