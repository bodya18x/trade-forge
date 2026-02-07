"""
Базовый репозиторий для PostgreSQL.

Содержит общую логику для всех репозиториев:
- Подключение к БД через DBManager
- Retry логика для операций
- Обработка ошибок
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tradeforge_db import get_db_manager
from tradeforge_logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BaseRepository:
    """
    Базовый репозиторий с общей логикой для всех PostgreSQL репозиториев.

    Предоставляет:
    - Подключение к БД через DBManager
    - Retry логику с экспоненциальной задержкой
    - Единообразную обработку ошибок

    Attributes:
        db_manager: Менеджер подключений к PostgreSQL.
    """

    def __init__(self):
        """Инициализирует базовый репозиторий."""
        self.db_manager = get_db_manager()

    async def _execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Выполняет функцию с автоматическими повторами при ошибках БД.

        Retry стратегия:
        - 3 попытки с экспоненциальной задержкой (1s, 2s, 4s)
        - Retry только на SQLAlchemyError и asyncio.TimeoutError
        - Reraise исключения после последней попытки

        Args:
            func: Асинхронная функция для выполнения.
            *args: Позиционные аргументы для функции.
            **kwargs: Именованные аргументы для функции.

        Returns:
            Результат выполнения функции.

        Raises:
            SQLAlchemyError: При ошибках БД после всех попыток.
            asyncio.TimeoutError: При таймауте после всех попыток.
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (SQLAlchemyError, asyncio.TimeoutError)
            ),
            reraise=True,
        ):
            with attempt:
                return await func(*args, **kwargs)
