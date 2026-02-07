"""
Protocols (interfaces) for dependency injection and testing.

Определяет контракты для менеджеров, что позволяет:
1. Легко мокать зависимости в тестах
2. Соблюдать Dependency Inversion Principle
3. Делать код слабо связанным и легко расширяемым
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

import pandas as pd
from clickhouse_connect.driver.asyncclient import AsyncClient


class IStorageManager(Protocol):
    """
    Протокол для менеджера хранилища данных.

    Определяет интерфейс для работы с PostgreSQL и ClickHouse.
    """

    async def async_init(self) -> None:
        """Асинхронная инициализация ClickHouse клиента."""
        ...

    async def get_hot_indicators_definitions(self) -> list[dict[str, Any]]:
        """Загружает определения hot-индикаторов из PostgreSQL."""
        ...

    async def save_rt_indicators(
        self,
        ticker: str,
        timeframe: str,
        begin: datetime,
        processed_df: pd.DataFrame,
        indicator_pipeline: Any,
    ) -> None:
        """Сохраняет RT индикаторы в ClickHouse."""
        ...

    async def get_base_candles_for_period(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Загружает базовые свечи из ClickHouse за период."""
        ...

    async def save_batch_indicators(
        self, client: AsyncClient, long_format_df: pd.DataFrame
    ) -> None:
        """Сохраняет batch индикаторы в ClickHouse."""
        ...

    async def get_start_date_with_lookback(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        original_start_date: datetime,
        lookback_candles: int,
    ) -> datetime:
        """Вычисляет дату начала с учетом lookback периода."""
        ...

    async def get_last_n_candles_for_context(
        self,
        ticker: str,
        timeframe: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Загружает последние N свечей для RT контекста (fallback при Redis downtime)."""
        ...

    async def close(self) -> None:
        """Закрывает соединения при graceful shutdown."""
        ...


class ICacheManager(Protocol):
    """
    Протокол для менеджера кэша.

    Определяет интерфейс для работы с Redis.
    """

    async def get_context_candles(
        self, ticker: str, timeframe: str
    ) -> list[dict[str, Any]]:
        """Получает контекст свечей из Redis."""
        ...

    async def update_context_cache(
        self, ticker: str, timeframe: str, new_candle: dict[str, Any]
    ) -> None:
        """Обновляет контекст свечей в Redis."""
        ...

    async def close(self) -> None:
        """Закрывает Redis соединение при graceful shutdown."""
        ...


class ILockManager(Protocol):
    """
    Протокол для менеджера распределенных блокировок.

    Определяет интерфейс для работы с Redis locks.
    """

    async def acquire_lock_with_blocking_wait(
        self,
        lock_key: str,
        timeout_seconds: int,
        poll_interval: float,
        lock_ttl: int,
    ) -> bool:
        """Получает блокировку с ожиданием."""
        ...

    async def release_lock(self, lock_key: str) -> None:
        """Освобождает блокировку."""
        ...

    async def close(self) -> None:
        """Закрывает Redis соединение при graceful shutdown."""
        ...

    @staticmethod
    def generate_indicator_lock_key(
        ticker: str, timeframe: str, indicator_key: str
    ) -> str:
        """Генерирует ключ блокировки для индикатора."""
        ...
