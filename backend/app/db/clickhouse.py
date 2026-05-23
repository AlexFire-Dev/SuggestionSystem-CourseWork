from contextlib import contextmanager
from typing import Any, Iterator

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from app.core.config import get_settings


def get_clickhouse_client() -> Client:
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
    )


@contextmanager
def clickhouse_client() -> Iterator[Client]:
    client = get_clickhouse_client()
    try:
        yield client
    finally:
        client.close()


def rows_as_dicts(column_names: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(column_names, row)) for row in rows]
