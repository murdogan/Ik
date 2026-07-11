"""Canonical success envelopes for Phase-1 and later JSON API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.request_context import RequestContext

MAX_PAGE_LIMIT = 200


class ResponseMeta(BaseModel):
    """Safe correlation metadata shared by new success responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    trace_id: str
    correlation_id: str

    @model_validator(mode="after")
    def require_correlation_alias(self) -> ResponseMeta:
        if self.correlation_id != self.request_id:
            raise ValueError("correlation_id must alias request_id")
        return self

    @classmethod
    def from_context(cls, context: RequestContext) -> ResponseMeta:
        return cls(
            request_id=context.request_id,
            trace_id=context.trace_id,
            correlation_id=context.request_id,
        )


class PageMeta(ResponseMeta):
    """Bounded deterministic-list continuation metadata."""

    limit: int = Field(ge=1, le=MAX_PAGE_LIMIT)
    next_cursor: str | None = None

    @classmethod
    def from_context(
        cls,
        context: RequestContext,
        *,
        limit: int,
        next_cursor: str | None,
    ) -> PageMeta:
        return cls(
            request_id=context.request_id,
            trace_id=context.trace_id,
            correlation_id=context.request_id,
            limit=limit,
            next_cursor=next_cursor,
        )


class DataEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: T
    meta: ResponseMeta


class ListEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[T]
    meta: PageMeta


def data_envelope[T](data: T, context: RequestContext) -> DataEnvelope[T]:
    return DataEnvelope[T](data=data, meta=ResponseMeta.from_context(context))


def list_envelope[T](
    data: list[T],
    context: RequestContext,
    *,
    limit: int,
    next_cursor: str | None,
) -> ListEnvelope[T]:
    return ListEnvelope[T](
        data=data,
        meta=PageMeta.from_context(
            context,
            limit=limit,
            next_cursor=next_cursor,
        ),
    )


__all__ = [
    "DataEnvelope",
    "ListEnvelope",
    "PageMeta",
    "ResponseMeta",
    "data_envelope",
    "list_envelope",
]
