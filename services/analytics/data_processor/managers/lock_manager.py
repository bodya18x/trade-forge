"""
Distributed Lock Manager на базе Redis.

Предотвращает race conditions при параллельной batch-обработке индикаторов.
"""

import asyncio
import hashlib
import os
import time
from typing import Any

from redis import asyncio as aioredis
from tradeforge_logger import get_logger

from core.constants import (
    DEFAULT_LOCK_POLL_INTERVAL_SECONDS,
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_LOCK_TTL_SECONDS,
)
from settings import settings

logger = get_logger(__name__)


class DistributedLockManager:
    """
    Менеджер распределенных блокировок на Redis.

    Использует Redis SET NX EX для атомарного получения блокировок.
    Предотвращает race conditions при параллельной обработке batch-задач.

    Attributes:
        redis_client: Redis клиент.
        default_timeout: TTL блокировки по умолчанию (секунды).

    Example:
        >>> lock_manager = DistributedLockManager()
        >>> # Генерируем ключ для блокировки индикатора
        >>> lock_key = lock_manager.generate_indicator_lock_key(
        ...     "SBER", "1h", "rsi_timeperiod_14"
        ... )
        >>> # Получаем блокировку с ожиданием
        >>> acquired = await lock_manager.acquire_lock_with_blocking_wait(
        ...     lock_key=lock_key,
        ...     timeout_seconds=60,
        ...     poll_interval=0.5,
        ...     lock_ttl=300
        ... )
        >>> if acquired:
        ...     try:
        ...         # Критичная секция - расчет индикатора
        ...         process_indicator()
        ...     finally:
        ...         await lock_manager.release_lock(lock_key)
    """

    def __init__(self, default_timeout: int = DEFAULT_LOCK_TTL_SECONDS):
        """
        Инициализация менеджера блокировок.

        Args:
            default_timeout: TTL блокировки по умолчанию в секундах.
                После истечения таймаута блокировка автоматически освобождается.
        """
        self.redis_client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
        self.default_timeout = default_timeout
        logger.info("lock_manager.initialized")

    async def close(self) -> None:
        """Закрывает Redis соединение при graceful shutdown."""
        try:
            await self.redis_client.aclose()
            logger.info("lock_manager.closed")
        except Exception as e:
            logger.warning("lock_manager.close_error", error=str(e))

    @staticmethod
    def generate_task_key(
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        indicator_keys: list[str],
    ) -> str:
        """
        Генерирует уникальный ключ задачи для блокировки.

        Ключ формируется из параметров задачи и хэша списка индикаторов.
        Две задачи с одинаковыми параметрами получат одинаковый ключ.

        Args:
            ticker: Тикер (например, "SBER").
            timeframe: Таймфрейм (например, "1h").
            start_date: Дата начала периода (ISO format).
            end_date: Дата окончания периода (ISO format).
            indicator_keys: Список базовых ключей индикаторов.

        Returns:
            Уникальный ключ задачи для блокировки.

        Note:
            Используем SHA256 для минимизации риска коллизий.
            16 символов (64 бита) дают ~4 млрд комбинаций.
        """
        sorted_indicators = sorted(indicator_keys)
        indicators_str = ",".join(sorted_indicators)
        indicators_hash = hashlib.sha256(indicators_str.encode()).hexdigest()[
            :16
        ]

        return (
            f"{ticker}:{timeframe}:{start_date}:{end_date}:{indicators_hash}"
        )

    async def is_locked(self, task_key: str) -> bool:
        """
        Проверяет, заблокирована ли задача.

        Args:
            task_key: Ключ задачи.

        Returns:
            True если задача заблокирована, False иначе.
        """
        lock_key = f"batch_lock:{task_key}"
        return bool(await self.redis_client.exists(lock_key))

    async def get_lock_info(self, task_key: str) -> dict[str, Any] | None:
        """
        Получает информацию о блокировке.

        Args:
            task_key: Ключ задачи.

        Returns:
            Словарь с информацией о блокировке или None если блокировки нет.
        """
        lock_key = f"batch_lock:{task_key}"

        if not await self.redis_client.exists(lock_key):
            return None

        ttl = await self.redis_client.ttl(lock_key)
        value = await self.redis_client.get(lock_key)

        return {
            "task_key": task_key,
            "lock_key": lock_key,
            "ttl_seconds": ttl,
            "lock_value": value,
        }

    @staticmethod
    def generate_indicator_lock_key(
        ticker: str, timeframe: str, indicator_key: str
    ) -> str:
        """
        Генерирует ключ блокировки для конкретного индикатора.

        Ключ НЕ содержит даты - блокируем весь индикатор целиком
        для данного ticker:timeframe. Это предотвращает дубликаты
        при пересекающихся диапазонах дат.

        Args:
            ticker: Тикер (например, "SBER").
            timeframe: Таймфрейм (например, "1h").
            indicator_key: Базовый ключ индикатора (например, "macd_12_26_9").

        Returns:
            Уникальный ключ блокировки для индикатора.
        """
        return f"{ticker}:{timeframe}:{indicator_key}"

    async def acquire_lock_with_blocking_wait(
        self,
        lock_key: str,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_LOCK_POLL_INTERVAL_SECONDS,
        lock_ttl: int = DEFAULT_LOCK_TTL_SECONDS,
    ) -> bool:
        """
        Получает блокировку с блокирующим ожиданием.

        Если блокировка занята - ждет освобождения, периодически
        проверяя доступность. Защищает от deadlock через TTL.

        Args:
            lock_key: Ключ блокировки (ticker:timeframe:indicator_key).
            timeout_seconds: Максимальное время ожидания.
            poll_interval: Интервал проверки доступности.
            lock_ttl: TTL блокировки (защита от deadlock).

        Returns:
            True если блокировка получена, False если timeout.
        """
        start_time = time.time()
        lock_value = f"{os.getpid()}:{time.time()}"

        logger.debug(
            "lock_manager.acquiring",
            lock_key=lock_key,
            timeout_seconds=timeout_seconds,
        )

        attempt = 0
        while (time.time() - start_time) < timeout_seconds:
            attempt += 1

            acquired = await self.redis_client.set(
                f"batch_lock:{lock_key}",
                lock_value,
                nx=True,
                ex=lock_ttl,
            )

            if acquired:
                elapsed = round(time.time() - start_time, 2)
                logger.info(
                    "lock_manager.acquired",
                    lock_key=lock_key,
                    attempt=attempt,
                    wait_seconds=elapsed,
                )
                return True

            if attempt == 1:
                logger.debug(
                    "lock_manager.busy",
                    lock_key=lock_key,
                    timeout_seconds=timeout_seconds,
                )

            await asyncio.sleep(poll_interval)

        logger.warning(
            "lock_manager.timeout",
            lock_key=lock_key,
            timeout_seconds=timeout_seconds,
            attempts=attempt,
        )
        return False

    async def release_lock(self, lock_key: str) -> None:
        """
        Освобождает блокировку.

        Должен вызываться в блоке finally для гарантированного
        освобождения даже при исключении.

        Args:
            lock_key: Ключ блокировки (ticker:timeframe:indicator_key).
        """
        try:
            await self.redis_client.delete(f"batch_lock:{lock_key}")
            logger.debug("lock_manager.released", lock_key=lock_key)
        except Exception as e:
            logger.warning(
                "lock_manager.release_error",
                lock_key=lock_key,
                error=str(e),
            )
