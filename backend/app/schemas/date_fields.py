from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BeforeValidator


def validate_date_only(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError("Date must use YYYY-MM-DD format")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("Date must use YYYY-MM-DD format") from None
    raise ValueError("Date must use YYYY-MM-DD format")


DateOnly = Annotated[date, BeforeValidator(validate_date_only)]
