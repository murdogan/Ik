from datetime import date, datetime
from re import Pattern, compile
from typing import Annotated, Any

from pydantic import BeforeValidator

DATE_ONLY_PATTERN: Pattern[str] = compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
DATE_ONLY_FORMAT_MESSAGE = "Date must use YYYY-MM-DD format"


def validate_date_only(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError(DATE_ONLY_FORMAT_MESSAGE)
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if DATE_ONLY_PATTERN.fullmatch(value) is None:
            raise ValueError(DATE_ONLY_FORMAT_MESSAGE)
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError(DATE_ONLY_FORMAT_MESSAGE) from None
    raise ValueError(DATE_ONLY_FORMAT_MESSAGE)


DateOnly = Annotated[date, BeforeValidator(validate_date_only)]
