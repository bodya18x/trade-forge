"""
Базовый класс для всех мигратов Trade Forge.

Определяет общий интерфейс и утилиты для выполнения миграций.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tradeforge_logger import get_logger

from config.settings import MigratorSettings


class MigrationStatus(str, Enum):
    """Статус выполнения миграции."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MigrationResult:
    """
    Результат выполнения миграции.

    Attributes:
        migrator_name: Название мигратора
        status: Статус выполнения
        duration_seconds: Время выполнения в секундах
        migrations_applied: Количество примененных миграций
        error: Описание ошибки (если есть)
        details: Дополнительные детали
    """

    migrator_name: str
    status: MigrationStatus
    duration_seconds: float
    migrations_applied: int = 0
    error: str | None = None
    details: dict[str, Any] | None = None


class BaseMigrator(ABC):
    """
    Базовый класс для всех мигратов.

    Определяет общий интерфейс для:
    - Health check сервисов
    - Выполнения миграций
    - Получения статуса миграций
    - Retry логики
    - Структурированного логирования
    """

    def __init__(self, settings: MigratorSettings, component_name: str):
        """
        Инициализация базового мигратора.

        Args:
            settings: Настройки миграций
            component_name: Название компонента для логирования
        """
        self.settings = settings
        self.component_name = component_name
        self.logger = get_logger(__name__)

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Проверка доступности сервиса перед миграцией.

        Returns:
            True если сервис доступен
        """
        pass

    @abstractmethod
    async def run(self) -> MigrationResult:
        """
        Выполнение миграций.

        Returns:
            Результат выполнения миграций
        """
        pass

    @abstractmethod
    async def get_migration_status(self) -> dict[str, Any]:
        """
        Получение текущего статуса миграций.

        Returns:
            Словарь со статусом миграций
        """
        pass

    async def _retry_with_backoff(
        self,
        func,
        *args,
        max_attempts: int | None = None,
        delay: int | None = None,
        **kwargs,
    ) -> Any:
        """
        Выполнение функции с повторами и экспоненциальной задержкой.

        Args:
            func: Функция для выполнения
            *args: Позиционные аргументы функции
            max_attempts: Максимальное количество попыток
            delay: Начальная задержка между попытками
            **kwargs: Именованные аргументы функции

        Returns:
            Результат выполнения функции

        Raises:
            Exception: Последнее исключение после всех попыток
        """
        if max_attempts is None:
            max_attempts = self.settings.MIGRATION_RETRY_MAX_ATTEMPTS
        if delay is None:
            delay = self.settings.MIGRATION_RETRY_DELAY

        last_exception = None
        current_delay = delay

        for attempt in range(1, max_attempts + 1):
            try:
                self.logger.debug(
                    "retry.attempt_started",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    function=func.__name__,
                )
                return await func(*args, **kwargs)

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "retry.attempt_failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    function=func.__name__,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                if attempt < max_attempts:
                    self.logger.info(
                        "retry.waiting_before_next_attempt",
                        delay_seconds=current_delay,
                        next_attempt=attempt + 1,
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff

        # Все попытки исчерпаны
        self.logger.error(
            "retry.all_attempts_failed",
            max_attempts=max_attempts,
            function=func.__name__,
            final_error=str(last_exception),
        )
        raise last_exception

    def _log_migration_start(self) -> None:
        """Логирует начало выполнения миграции."""
        self.logger.info(
            f"{self.component_name}.migration_started",
            migrator=self.component_name,
        )

    def _log_migration_complete(
        self, duration: float, migrations_count: int
    ) -> None:
        """
        Логирует успешное завершение миграции.

        Args:
            duration: Время выполнения в секундах
            migrations_count: Количество примененных миграций
        """
        self.logger.info(
            f"{self.component_name}.migration_completed",
            migrator=self.component_name,
            duration_seconds=round(duration, 3),
            migrations_applied=migrations_count,
        )

    def _log_migration_failed(self, duration: float, error: Exception) -> None:
        """
        Логирует провал миграции.

        Args:
            duration: Время выполнения до провала
            error: Исключение
        """
        self.logger.error(
            f"{self.component_name}.migration_failed",
            migrator=self.component_name,
            duration_seconds=round(duration, 3),
            error=str(error),
            error_type=type(error).__name__,
        )

    def _log_health_check_success(self) -> None:
        """Логирует успешный health check."""
        self.logger.info(
            f"{self.component_name}.health_check_success",
            migrator=self.component_name,
        )

    def _log_health_check_failed(self, error: Exception | None = None) -> None:
        """
        Логирует провал health check.

        Args:
            error: Исключение (если есть)
        """
        self.logger.error(
            f"{self.component_name}.health_check_failed",
            migrator=self.component_name,
            error=str(error) if error else None,
            error_type=type(error).__name__ if error else None,
        )

    async def execute_with_timing(self) -> MigrationResult:
        """
        Обертка для выполнения миграции с замером времени и логированием.

        Returns:
            Результат выполнения миграции
        """
        start_time = time.time()
        self._log_migration_start()

        try:
            result = await self.run()
            duration = time.time() - start_time
            result.duration_seconds = duration

            if result.status == MigrationStatus.SUCCESS:
                self._log_migration_complete(
                    duration, result.migrations_applied
                )
            elif result.status == MigrationStatus.FAILED:
                self._log_migration_failed(duration, Exception(result.error))

            return result

        except Exception as e:
            duration = time.time() - start_time
            self._log_migration_failed(duration, e)

            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.FAILED,
                duration_seconds=duration,
                error=str(e),
            )
