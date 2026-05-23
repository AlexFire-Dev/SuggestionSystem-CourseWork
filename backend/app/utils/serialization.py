from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    return value


def jsonable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [jsonable(row) for row in rows]
