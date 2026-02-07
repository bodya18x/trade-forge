"""
Менеджеры для управления пулами соединений.

Содержит пулы для асинхронной работы с внешними системами.
"""

from __future__ import annotations

from .clickhouse_pool import ClickHouseClientPool

__all__ = [
    "ClickHouseClientPool",
]
