import logging
from collections.abc import Sequence

import pytest
from app.main import create_app
from app.platform.observability.correlation import (
    CORRELATION_ID_HEADER,
    REQUEST_CONTEXT_STATE_KEY,
    REQUEST_ID_HEADER,
    TRACE_ID_HEADER,
    CorrelationMiddleware,
    get_request_context,
    replace_request_context,
)
from app.platform.request_context import RequestContext
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient

GENERATED_REQUEST_ID = "generated-request-001"
GENERATED_TRACE_ID = "11111111111111111111111111111111"
CLIENT_REQUEST_ID = "client-request-001"
CLIENT_TRACE_ID = "0123456789abcdef0123456789abcdef"

type HeaderPairs = Sequence[tuple[str, str]]


def _app(*, logger: logging.Logger | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CorrelationMiddleware,
        request_id_factory=lambda: GENERATED_REQUEST_ID,
        trace_id_factory=lambda: GENERATED_TRACE_ID,
        logger=logger,
    )

    @app.get("/context")
    async def inspect_context(request: Request) -> dict[str, object]:
        context = get_request_context(request)
        return {
            "request_id": context.request_id,
            "trace_id": context.trace_id,
            "state_is_context": getattr(request.state, REQUEST_CONTEXT_STATE_KEY) is context,
        }

    @app.get("/spoofed-response")
    async def spoofed_response() -> Response:
        return Response(
            status_code=202,
            headers={
                REQUEST_ID_HEADER: "spoofed-request",
                TRACE_ID_HEADER: "22222222222222222222222222222222",
                CORRELATION_ID_HEADER: "spoofed-correlation",
            },
        )

    return app


async def _get(
    app: FastAPI,
    path: str = "/context",
    *,
    headers: HeaderPairs = (),
) -> object:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        return await client.get(path, headers=headers)


async def test_valid_request_and_trace_ids_propagate_to_state_and_response() -> None:
    response = await _get(
        _app(logger=None),
        headers=[
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "request_id": CLIENT_REQUEST_ID,
        "trace_id": CLIENT_TRACE_ID,
        "state_is_context": True,
    }
    assert response.headers[REQUEST_ID_HEADER] == CLIENT_REQUEST_ID
    assert response.headers[TRACE_ID_HEADER] == CLIENT_TRACE_ID
    assert response.headers[CORRELATION_ID_HEADER] == CLIENT_REQUEST_ID


async def test_deprecated_correlation_header_is_an_input_and_response_alias() -> None:
    response = await _get(
        _app(logger=None),
        headers=[
            (CORRELATION_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ],
    )

    assert response.json()["request_id"] == CLIENT_REQUEST_ID
    assert response.headers[REQUEST_ID_HEADER] == CLIENT_REQUEST_ID
    assert response.headers[CORRELATION_ID_HEADER] == CLIENT_REQUEST_ID


@pytest.mark.parametrize(
    "headers",
    [
        (),
        ((REQUEST_ID_HEADER, "unsafe value with spaces"),),
        ((REQUEST_ID_HEADER, "eyJhbGciOi.none.signature"),),
        ((TRACE_ID_HEADER, "0" * 32),),
        (
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ),
        (
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (CORRELATION_ID_HEADER, "conflicting-request-002"),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ),
        (
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ),
    ],
)
async def test_missing_invalid_duplicate_or_conflicting_ids_generate(
    headers: HeaderPairs,
) -> None:
    response = await _get(_app(logger=None), headers=headers)

    supplied_request_ids = [value for name, value in headers if name == REQUEST_ID_HEADER]
    supplied_trace_ids = [value for name, value in headers if name == TRACE_ID_HEADER]
    expected_request_id = (
        CLIENT_REQUEST_ID
        if supplied_request_ids == [CLIENT_REQUEST_ID]
        and not any(name == CORRELATION_ID_HEADER for name, _ in headers)
        else GENERATED_REQUEST_ID
    )
    expected_trace_id = (
        CLIENT_TRACE_ID
        if supplied_trace_ids == [CLIENT_TRACE_ID]
        else GENERATED_TRACE_ID
    )
    assert response.headers[REQUEST_ID_HEADER] == expected_request_id
    assert response.headers[TRACE_ID_HEADER] == expected_trace_id
    assert response.headers[CORRELATION_ID_HEADER] == expected_request_id


async def test_matching_primary_and_deprecated_alias_are_not_a_conflict() -> None:
    response = await _get(
        _app(logger=None),
        headers=[
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (CORRELATION_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ],
    )

    assert response.headers[REQUEST_ID_HEADER] == CLIENT_REQUEST_ID


async def test_middleware_replaces_app_supplied_correlation_response_headers() -> None:
    response = await _get(
        _app(logger=None),
        "/spoofed-response",
        headers=[
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
        ],
    )

    assert response.status_code == 202
    assert response.headers.get_list(REQUEST_ID_HEADER) == [CLIENT_REQUEST_ID]
    assert response.headers.get_list(TRACE_ID_HEADER) == [CLIENT_TRACE_ID]
    assert response.headers.get_list(CORRELATION_ID_HEADER) == [CLIENT_REQUEST_ID]


async def test_completion_log_is_allowlisted_and_omits_path_query_and_auth(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tests.correlation")
    caplog.set_level(logging.INFO, logger=logger.name)

    response = await _get(
        _app(logger=logger),
        "/context?email=ada@example.test",
        headers=[
            (REQUEST_ID_HEADER, CLIENT_REQUEST_ID),
            (TRACE_ID_HEADER, CLIENT_TRACE_ID),
            ("Authorization", "Bearer raw-secret-material"),
            ("Cookie", "session=raw-cookie-material"),
        ],
    )

    assert response.status_code == 200
    record = next(record for record in caplog.records if record.message == "http.request.completed")
    assert record.request_id == CLIENT_REQUEST_ID
    assert record.trace_id == CLIENT_TRACE_ID
    assert record.authentication_strength == "unauthenticated"
    assert record.http_method == "GET"
    assert record.http_status_code == 200
    serialized_record = repr(record.__dict__)
    assert "ada@example.test" not in serialized_record
    assert "raw-secret-material" not in serialized_record
    assert "raw-cookie-material" not in serialized_record


def test_replace_context_only_accepts_correlation_preserving_enrichment() -> None:
    scope: dict[str, object] = {"state": {}}
    current = RequestContext(request_id=CLIENT_REQUEST_ID, trace_id=CLIENT_TRACE_ID)
    scope["state"][REQUEST_CONTEXT_STATE_KEY] = current  # type: ignore[index]

    assert replace_request_context(scope, current.derive()) is not current
    with pytest.raises(ValueError, match="preserve"):
        replace_request_context(
            scope,
            RequestContext(
                request_id="different-request-002",
                trace_id=CLIENT_TRACE_ID,
            ),
        )


async def test_phase1_error_and_log_use_generated_safe_metadata_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="app.platform.observability.correlation",
    )
    unsafe_values = {
        "ada@example.test",
        "eyJhbGciOi.none.signature",
        "Bearer raw-secret-material",
    }
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="https://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/platform/tenants",
            headers={
                REQUEST_ID_HEADER: "ada@example.test",
                CORRELATION_ID_HEADER: "eyJhbGciOi.none.signature",
                TRACE_ID_HEADER: "not-a-trace",
                "Authorization": "Bearer raw-secret-material",
            },
        )

    assert response.status_code == 403
    request_id = response.headers[REQUEST_ID_HEADER]
    trace_id = response.headers[TRACE_ID_HEADER]
    assert response.json()["error"]["correlation_id"] == request_id
    assert response.headers[CORRELATION_ID_HEADER] == request_id
    assert all(value not in response.text for value in unsafe_values)
    record = next(record for record in caplog.records if record.message == "http.request.completed")
    assert record.request_id == request_id
    assert record.trace_id == trace_id
    assert all(value not in repr(record.__dict__) for value in unsafe_values)


async def test_unexpected_error_keeps_safe_correlation_without_exception_details() -> None:
    app = create_app()

    @app.get("/api/v1/platform/f1b-unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("private failure with ada@example.test and raw-secret")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/platform/f1b-unexpected-error",
            headers={
                REQUEST_ID_HEADER: CLIENT_REQUEST_ID,
                TRACE_ID_HEADER: CLIENT_TRACE_ID,
            },
        )

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == CLIENT_REQUEST_ID
    assert response.headers[TRACE_ID_HEADER] == CLIENT_TRACE_ID
    assert response.json() == {
        "error": {
            "code": "application_command_failed",
            "message": "Application command failed",
            "details": None,
            "correlation_id": CLIENT_REQUEST_ID,
        }
    }
    assert "ada@example.test" not in response.text
    assert "raw-secret" not in response.text
