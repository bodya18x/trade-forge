"""
Репозитории для работы с данными.

Data access layer для ClickHouse, PostgreSQL и Redis.
"""

from __future__ import annotations

from .clickhouse import ClickHouseRepository
from .postgres import PostgresRepository
from .redis_state import RedisStateManager

__all__ = [
    "ClickHouseRepository",
    "PostgresRepository",
    "RedisStateManager",
]
