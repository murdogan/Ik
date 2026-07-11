"""Explicit Phase-0 HTTP adapters retained during the Phase-1 contract migration."""

from fastapi import Response

from app.platform.pagination import NEXT_CURSOR_HEADER, CursorPage


def phase0_plain_cursor_list[T](
    response: Response,
    page: CursorPage[T],
) -> list[T]:
    """Keep the reviewed plain-array + header contract for employee/leave clients.

    New Phase-1 list endpoints must use the canonical ``{data, meta}`` response models. This
    adapter exists only for the pre-existing endpoints whose body migration requires a later
    versioned/deprecation window.
    """

    if page.next_cursor is not None:
        response.headers[NEXT_CURSOR_HEADER] = page.next_cursor
    return page.items


__all__ = ["phase0_plain_cursor_list"]
