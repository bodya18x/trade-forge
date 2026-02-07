"""
Мигратор для синхронизации системных индикаторов.

Синхронизирует определения индикаторов из JSON-файла
с таблицей trader_core.system_indicators в PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text

from config.settings import MigratorSettings
from indicators.manager import IndicatorsManager
from indicators.schemas import IndicatorValidator, SystemIndicatorsList

from .base import BaseMigrator, MigrationResult, MigrationStatus


class IndicatorsMigrator(BaseMigrator):
    """
    Мигратор для синхронизации системных индикаторов.

    Читает определения индикаторов из JSON, валидирует их
    и синхронизирует с базой данных PostgreSQL.
    """

    def __init__(self, settings: MigratorSettings):
        """
        Инициализация мигратора индикаторов.

        Args:
            settings: Настройки миграций
        """
        super().__init__(settings, "indicators_migrator")
        self.indicators_json_path = Path("indicators/data/indicators.json")
        self._manager: Optional[IndicatorsManager] = None
        self._validator = IndicatorValidator()

    @property
    def manager(self) -> IndicatorsManager:
        """
        Получить менеджер индикаторов.

        Returns:
            Менеджер индикаторов
        """
        if self._manager is None:
            self._manager = IndicatorsManager(self.settings.POSTGRES_URL)
        return self._manager

    async def health_check(self) -> bool:
        """
        Проверка доступности PostgreSQL.

        Returns:
            True если PostgreSQL доступен
        """
        self.logger.debug(
            "indicators_migrator.health_check_started",
            host=self.settings.POSTGRES_HOST,
            port=self.settings.POSTGRES_PORT,
        )

        try:
            # Используем health_check из менеджера
            if self.manager.health_check():
                self._log_health_check_success()
                return True
            else:
                self._log_health_check_failed()
                return False

        except Exception as e:
            self._log_health_check_failed(e)
            return False

    async def run(self) -> MigrationResult:
        """
        Выполнение синхронизации индикаторов.

        Returns:
            Результат синхронизации
        """
        try:
            # Проверяем существование файла
            if not self.indicators_json_path.exists():
                raise FileNotFoundError(
                    f"Indicators file not found: {self.indicators_json_path}"
                )

            self.logger.info(
                "indicators_migrator.loading_indicators",
                path=str(self.indicators_json_path),
            )

            # Загружаем и валидируем индикаторы
            indicators_list = await self._load_and_validate_indicators()

            indicators_count = len(indicators_list.indicators)
            self.logger.info(
                "indicators_migrator.indicators_validated",
                count=indicators_count,
            )

            # Получаем текущее состояние БД
            current_indicators = await self._get_current_indicators()
            current_count = len(current_indicators)

            self.logger.info(
                "indicators_migrator.current_indicators_in_db",
                count=current_count,
            )

            # Синхронизируем с БД
            await self._sync_indicators(indicators_list)

            # Проверяем результат
            new_indicators = await self._get_current_indicators()
            new_count = len(new_indicators)

            self.logger.info(
                "indicators_migrator.sync_completed",
                old_count=current_count,
                new_count=new_count,
                indicators_synced=indicators_count,
            )

            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.SUCCESS,
                duration_seconds=0.0,
                migrations_applied=indicators_count,
                details={
                    "indicators_synced": indicators_count,
                    "old_count": current_count,
                    "new_count": new_count,
                    "indicators": [
                        ind.name for ind in indicators_list.indicators
                    ],
                },
            )

        except Exception as e:
            self.logger.error(
                "indicators_migrator.sync_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.FAILED,
                duration_seconds=0.0,
                error=str(e),
            )

    async def get_migration_status(self) -> Dict[str, Any]:
        """
        Получение статуса индикаторов.

        Returns:
            Словарь со статусом индикаторов
        """
        try:
            indicators_list = await self._load_and_validate_indicators()
            current_indicators = await self._get_current_indicators()

            defined_names = {ind.name for ind in indicators_list.indicators}
            current_names = set(current_indicators.keys())

            missing = defined_names - current_names
            extra = current_names - defined_names

            return {
                "database": self.settings.POSTGRES_DB,
                "indicators_file": str(self.indicators_json_path),
                "defined_indicators": list(defined_names),
                "current_indicators": list(current_names),
                "missing_in_db": list(missing),
                "extra_in_db": list(extra),
                "is_up_to_date": len(missing) == 0 and len(extra) == 0,
            }
        except Exception as e:
            return {
                "database": self.settings.POSTGRES_DB,
                "error": str(e),
                "is_up_to_date": False,
            }

    async def _load_and_validate_indicators(self) -> SystemIndicatorsList:
        """
        Загрузить и валидировать индикаторы из JSON.

        Returns:
            Валидированный список индикаторов

        Raises:
            FileNotFoundError: Если файл не найден
            ValidationError: Если валидация не прошла
        """
        self.logger.debug(
            "indicators_migrator.reading_json",
            path=str(self.indicators_json_path),
        )

        with open(self.indicators_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # validate_indicators_list ожидает список и САМ оборачивает в {"indicators": ...}
        # Поэтому если data - словарь, извлекаем список, иначе передаем как есть
        if isinstance(data, dict):
            indicators_data = data.get("indicators", [])
        else:
            indicators_data = data

        raw_count = len(indicators_data)

        self.logger.debug(
            "indicators_migrator.validating_indicators",
            raw_count=raw_count,
        )

        # Валидируем через схему (метод сам обернет в {"indicators": ...})
        indicators_list = self._validator.validate_indicators_list(
            indicators_data
        )

        self.logger.info(
            "indicators_migrator.validation_successful",
            count=len(indicators_list.indicators),
        )

        return indicators_list

    async def _get_current_indicators(self) -> Dict[str, Any]:
        """
        Получить текущие индикаторы из БД.

        Returns:
            Словарь {name: indicator_data}
        """
        engine = create_engine(self.settings.POSTGRES_URL)

        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT name, display_name, is_enabled "
                        "FROM trader_core.system_indicators"
                    )
                )

                indicators = {
                    row[0]: {"display_name": row[1], "is_enabled": row[2]}
                    for row in result.fetchall()
                }

                return indicators

        except Exception:
            # Таблица может не существовать на первом запуске
            return {}
        finally:
            engine.dispose()

    async def _sync_indicators(
        self, indicators_list: SystemIndicatorsList
    ) -> None:
        """
        Синхронизировать индикаторы с БД.

        Args:
            indicators_list: Список индикаторов для синхронизации

        Raises:
            Exception: При ошибке синхронизации
        """
        self.logger.info(
            "indicators_migrator.starting_sync",
            count=len(indicators_list.indicators),
        )

        try:
            # Используем метод из менеджера
            self.manager.sync_to_database(indicators_list)

            self.logger.info(
                "indicators_migrator.sync_successful",
                count=len(indicators_list.indicators),
            )

        except Exception as e:
            self.logger.error(
                "indicators_migrator.sync_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
