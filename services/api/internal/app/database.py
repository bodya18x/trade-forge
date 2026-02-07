"""
Модуль управления подключениями к базам данных.

Использует tradeforge_db для PostgreSQL и ClickHouse клиент для аналитики.
"""

from __future__ import annotations

import clickhouse_connect
from clickhouse_connect.driver.client import Client as ClickHouseClient

from app.settings import settings

# ClickHouse клиент (синглтон)
_clickhouse_client: ClickHouseClient | None = None


def get_clickhouse_client() -> ClickHouseClient:
    """
    Получает ClickHouse клиент (синглтон).

    Используется для проверки наличия исторических данных.
    """
    global _clickhouse_client

    if _clickhouse_client is None:
        _clickhouse_client = clickhouse_connect.get_client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DB,
        )

    return _clickhouse_client
