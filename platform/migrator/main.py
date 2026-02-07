"""
Главный оркестратор миграций Trade Forge.

Координирует выполнение всех типов миграций в правильном порядке:
1. PostgreSQL (основная база данных)
2. ClickHouse (аналитическая база)
3. Kafka (топики сообщений)
4. Indicators (системные индикаторы)
"""

from __future__ import annotations

import asyncio
import sys

from tradeforge_logger import configure_logging, get_logger

from config.settings import get_settings
from migrators import (
    ClickHouseMigrator,
    IndicatorsMigrator,
    KafkaMigrator,
    MigrationResult,
    MigrationStatus,
)


class MigrationOrchestrator:
    """
    Оркестратор для координации выполнения всех миграций.

    Обеспечивает правильный порядок выполнения миграций,
    health checks и детальное логирование процесса.
    """

    def __init__(self):
        """Инициализация оркестратора."""
        self.settings = get_settings()

        configure_logging(
            service_name=self.settings.SERVICE_NAME,
            environment=self.settings.ENVIRONMENT,
            log_level=self.settings.LOG_LEVEL,
            enable_json=True,
            enable_console_colors=False,
        )
        self.logger = get_logger(__name__)

        # Создаем мигратов в нужном порядке
        self.migrators = [
            ClickHouseMigrator(self.settings),
            KafkaMigrator(self.settings),
            IndicatorsMigrator(self.settings),
        ]

    async def run(self) -> bool:
        """
        Запустить все миграции.

        Returns:
            True если все миграции выполнены успешно

        Raises:
            SystemExit: При критических ошибках
        """
        self.logger.info(
            "orchestrator.migration_process_started",
            total_migrators=len(self.migrators),
        )

        # Проверяем, включены ли миграции
        if not self.settings.is_migration_enabled():
            self.logger.error(
                "orchestrator.migrations_disabled",
                migrate_flag=self.settings.MIGRATE,
            )
            return False

        # Выполняем health checks
        if not await self._run_health_checks():
            self.logger.error("orchestrator.health_checks_failed")
            return False

        # Выполняем миграции
        results = await self._run_migrations()

        # Выводим итоговую статистику
        self._print_summary(results)

        # Проверяем результаты
        all_success = all(r.status == MigrationStatus.SUCCESS for r in results)

        if all_success:
            self.logger.info("orchestrator.all_migrations_successful")
        else:
            self.logger.error("orchestrator.some_migrations_failed")

        return all_success

    async def rollback(self) -> bool:
        """
        Откатить последнюю миграцию ClickHouse.

        Returns:
            True если откат выполнен успешно
        """
        self.logger.info("orchestrator.rollback_process_started")

        # Откатываем только ClickHouse миграции
        clickhouse_migrator = ClickHouseMigrator(self.settings)

        try:
            result = await clickhouse_migrator.rollback_last_migration()

            if result.status == MigrationStatus.SUCCESS:
                self.logger.info(
                    "orchestrator.rollback_successful",
                    migration=(
                        result.details.get("rolled_back")
                        if result.details
                        else None
                    ),
                )
                return True
            else:
                self.logger.error(
                    "orchestrator.rollback_failed",
                    error=result.error,
                )
                return False

        except Exception as e:
            self.logger.error(
                "orchestrator.rollback_exception",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def _run_health_checks(self) -> bool:
        """
        Выполнить health check для всех сервисов.

        Returns:
            True если все сервисы доступны
        """
        self.logger.info("orchestrator.health_checks_started")

        all_healthy = True

        for migrator in self.migrators:
            self.logger.debug(
                "orchestrator.health_check_running",
                migrator=migrator.component_name,
            )

            try:
                is_healthy = await migrator.health_check()

                if is_healthy:
                    self.logger.info(
                        "orchestrator.health_check_passed",
                        migrator=migrator.component_name,
                    )
                else:
                    self.logger.error(
                        "orchestrator.health_check_failed",
                        migrator=migrator.component_name,
                    )
                    all_healthy = False

            except Exception as e:
                self.logger.error(
                    "orchestrator.health_check_error",
                    migrator=migrator.component_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                all_healthy = False

        if all_healthy:
            self.logger.info("orchestrator.all_health_checks_passed")
        else:
            self.logger.error("orchestrator.health_checks_incomplete")

        return all_healthy

    async def _run_migrations(self) -> list[MigrationResult]:
        """
        Выполнить все миграции последовательно.

        Returns:
            Список результатов миграций
        """
        self.logger.info("orchestrator.migrations_execution_started")

        results: list[MigrationResult] = []

        for migrator in self.migrators:
            self.logger.info(
                "orchestrator.migrator_starting",
                migrator=migrator.component_name,
            )

            try:
                # Выполняем миграцию с замером времени
                result = await migrator.execute_with_timing()
                results.append(result)

                # Проверяем результат
                if result.status == MigrationStatus.SUCCESS:
                    self.logger.info(
                        "orchestrator.migrator_completed",
                        migrator=migrator.component_name,
                        migrations_applied=result.migrations_applied,
                        duration_seconds=round(result.duration_seconds, 3),
                    )
                else:
                    self.logger.error(
                        "orchestrator.migrator_failed",
                        migrator=migrator.component_name,
                        error=result.error,
                        duration_seconds=round(result.duration_seconds, 3),
                    )
                    # При провале миграции прерываем процесс
                    break

            except Exception as e:
                self.logger.error(
                    "orchestrator.migrator_exception",
                    migrator=migrator.component_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Добавляем результат с ошибкой
                results.append(
                    MigrationResult(
                        migrator_name=migrator.component_name,
                        status=MigrationStatus.FAILED,
                        duration_seconds=0.0,
                        error=str(e),
                    )
                )
                break

        return results

    def _print_summary(self, results: list[MigrationResult]) -> None:
        """
        Вывести итоговую статистику миграций.

        Args:
            results: Список результатов миграций
        """
        self.logger.info("orchestrator.migration_summary_start")
        self.logger.info("=" * 70)

        total_migrations = sum(r.migrations_applied for r in results)
        total_duration = sum(r.duration_seconds for r in results)

        for result in results:
            status_text = result.status.value.upper()

            self.logger.info(
                "orchestrator.migrator_summary",
                migrator=result.migrator_name,
                status=status_text,
                migrations_applied=result.migrations_applied,
                duration_seconds=round(result.duration_seconds, 3),
                error=result.error if result.error else None,
            )

        self.logger.info("=" * 70)
        self.logger.info(
            "orchestrator.total_summary",
            total_migrators=len(results),
            total_migrations_applied=total_migrations,
            total_duration_seconds=round(total_duration, 3),
        )


async def main() -> int:
    """
    Точка входа для миграций.

    Returns:
        Код возврата (0 = успех, 1 = ошибка)
    """
    # Проверяем аргументы командной строки
    is_rollback = len(sys.argv) > 1 and sys.argv[1] == "--rollback"

    orchestrator = MigrationOrchestrator()

    try:
        if is_rollback:
            success = await orchestrator.rollback()
        else:
            success = await orchestrator.run()

        return 0 if success else 1

    except KeyboardInterrupt:
        orchestrator.logger.warning("orchestrator.interrupted_by_user")
        return 1

    except Exception as e:
        orchestrator.logger.error(
            "orchestrator.unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
