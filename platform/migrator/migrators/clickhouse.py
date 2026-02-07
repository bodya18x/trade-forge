"""
ClickHouse мигратор с раздельными upgrade/downgrade миграциями.

Структура:
    database/clickhouse/
        ├── upgrade/     # Миграции для применения
        │   └── V0001-description.sql
        └── downgrade/   # Миграции для отката
            └── V0001-description.sql

Политика безопасности:
    - Upgrade может быть применен ТОЛЬКО если существует соответствующий downgrade
    - Это гарантирует возможность отката в любой момент
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import clickhouse_connect
from clickhouse_connect.driver import Client

from config.settings import MigratorSettings

from .base import BaseMigrator, MigrationResult, MigrationStatus


@dataclass
class ClickHouseMigration:
    """
    Информация о миграции ClickHouse.

    Attributes:
        version: Номер версии (например, "0001")
        name: Название миграции
        filename: Имя файла миграции
        upgrade_sql: SQL для применения миграции
        has_downgrade: Флаг наличия downgrade файла
    """

    version: str
    name: str
    filename: str
    upgrade_sql: str
    has_downgrade: bool

    @property
    def migration_name(self) -> str:
        """Полное название миграции."""
        return f"V{self.version}-{self.name}"


class ClickHouseMigrator(BaseMigrator):
    """
    Мигратор для ClickHouse с раздельными upgrade/downgrade файлами.

    Обеспечивает безопасность через требование наличия downgrade для каждого upgrade.
    """

    def __init__(self, settings: MigratorSettings):
        """
        Инициализация ClickHouse мигратора.

        Args:
            settings: Настройки миграций
        """
        super().__init__(settings, "clickhouse_migrator")
        self.upgrade_path = Path("database/clickhouse/upgrade")
        self.downgrade_path = Path("database/clickhouse/downgrade")
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """
        Получить клиент ClickHouse.

        Returns:
            Клиент ClickHouse
        """
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self.settings.CLICKHOUSE_HOST,
                port=self.settings.CLICKHOUSE_PORT,
                username=self.settings.CLICKHOUSE_USER,
                password=self.settings.CLICKHOUSE_PASSWORD,
                database=self.settings.CLICKHOUSE_DATABASE,
                connect_timeout=self.settings.CLICKHOUSE_CONNECT_TIMEOUT,
                send_receive_timeout=self.settings.CLICKHOUSE_SEND_RECEIVE_TIMEOUT,
            )
        return self._client

    async def health_check(self) -> bool:
        """
        Проверка доступности ClickHouse.

        Returns:
            True если ClickHouse доступен
        """
        self.logger.debug(
            "clickhouse_migrator.health_check_started",
            host=self.settings.CLICKHOUSE_HOST,
            port=self.settings.CLICKHOUSE_PORT,
            database=self.settings.CLICKHOUSE_DATABASE,
        )

        try:
            result = self.client.query("SELECT 1")
            if result.result_rows and result.result_rows[0][0] == 1:
                self._log_health_check_success()
                return True
            return False

        except Exception as e:
            self._log_health_check_failed(e)
            return False

    async def run(self) -> MigrationResult:
        """
        Выполнение миграций ClickHouse.

        Returns:
            Результат выполнения миграций
        """
        try:
            # Убеждаемся, что таблица миграций существует
            await self._ensure_migrations_table()

            # Получаем список примененных миграций
            applied_migrations = await self._get_applied_migrations()
            self.logger.info(
                "clickhouse_migrator.applied_migrations",
                count=len(applied_migrations),
            )

            # Получаем список всех миграций из upgrade/
            all_migrations = await self._load_migrations_from_files()
            self.logger.info(
                "clickhouse_migrator.total_migrations",
                count=len(all_migrations),
            )

            # Находим pending миграции
            pending = [
                m
                for m in all_migrations
                if m.migration_name not in applied_migrations
            ]

            if not pending:
                self.logger.info("clickhouse_migrator.no_pending_migrations")
                return MigrationResult(
                    migrator_name=self.component_name,
                    status=MigrationStatus.SUCCESS,
                    duration_seconds=0.0,
                    migrations_applied=0,
                    details={"message": "No pending migrations"},
                )

            # Валидируем безопасность ТОЛЬКО pending миграций
            # Уже примененные миграции не требуют downgrade (legacy)
            validation_result = await self._validate_all_migrations_safety(
                pending
            )
            if not validation_result["is_safe"]:
                error_msg = (
                    f"Обнаружены небезопасные pending миграции без downgrade: "
                    f"{validation_result['missing_downgrades']}"
                )
                self.logger.error(
                    "clickhouse_migrator.unsafe_migrations_detected",
                    missing_downgrades=validation_result["missing_downgrades"],
                )
                raise ValueError(error_msg)

            self.logger.info(
                "clickhouse_migrator.pending_migrations_found",
                count=len(pending),
                migrations=[m.migration_name for m in pending],
            )

            # Применяем pending миграции
            applied_count = 0
            for migration in pending:
                await self._apply_migration(migration)
                applied_count += 1

            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.SUCCESS,
                duration_seconds=0.0,
                migrations_applied=applied_count,
                details={
                    "applied_migrations": [m.migration_name for m in pending],
                },
            )

        except Exception as e:
            self.logger.error(
                "clickhouse_migrator.migration_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.FAILED,
                duration_seconds=0.0,
                error=str(e),
            )
        finally:
            if self._client:
                self._client.close()
                self._client = None

    async def get_migration_status(self) -> Dict[str, Any]:
        """
        Получение статуса миграций ClickHouse.

        Returns:
            Словарь со статусом миграций
        """
        try:
            applied = await self._get_applied_migrations()
            all_migrations = await self._load_migrations_from_files()
            pending = [
                m.migration_name
                for m in all_migrations
                if m.migration_name not in applied
            ]

            # Проверка безопасности
            validation = await self._validate_all_migrations_safety(
                all_migrations
            )

            return {
                "database": self.settings.CLICKHOUSE_DATABASE,
                "applied_migrations": applied,
                "applied_count": len(applied),
                "pending_migrations": pending,
                "pending_count": len(pending),
                "is_up_to_date": len(pending) == 0,
                "is_safe": validation["is_safe"],
                "missing_downgrades": validation["missing_downgrades"],
            }
        except Exception as e:
            return {
                "database": self.settings.CLICKHOUSE_DATABASE,
                "error": str(e),
                "is_up_to_date": False,
                "is_safe": False,
            }

    async def rollback_last_migration(self) -> MigrationResult:
        """
        Откатить последнюю примененную миграцию.

        Returns:
            Результат отката миграции

        Raises:
            ValueError: Если нет миграций для отката
        """
        self.logger.info("clickhouse_migrator.rollback_started")

        try:
            # Получаем последнюю примененную миграцию
            applied = await self._get_applied_migrations()
            if not applied:
                raise ValueError("No migrations to rollback")

            last_migration_name = applied[-1]
            self.logger.info(
                "clickhouse_migrator.rollback_target",
                migration=last_migration_name,
            )

            # Загружаем downgrade SQL
            downgrade_sql = await self._load_downgrade_sql(last_migration_name)

            # Выполняем откат
            await self._execute_downgrade(last_migration_name, downgrade_sql)

            self.logger.info(
                "clickhouse_migrator.rollback_completed",
                migration=last_migration_name,
            )

            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.SUCCESS,
                duration_seconds=0.0,
                migrations_applied=1,
                details={
                    "rolled_back": last_migration_name,
                },
            )

        except Exception as e:
            self.logger.error(
                "clickhouse_migrator.rollback_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.FAILED,
                duration_seconds=0.0,
                error=str(e),
            )

    async def _ensure_migrations_table(self) -> None:
        """Создать таблицу миграций, если она не существует."""
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.settings.CLICKHOUSE_DATABASE}.migrations
            (
                migration_name String,
                applied_at DateTime DEFAULT now()
            )
            ENGINE = MergeTree()
            ORDER BY migration_name
        """

        self.logger.debug("clickhouse_migrator.creating_migrations_table")
        self.client.command(create_table_sql)
        self.logger.debug("clickhouse_migrator.migrations_table_ready")

    async def _get_applied_migrations(self) -> List[str]:
        """
        Получить список примененных миграций.

        Returns:
            Список названий примененных миграций
        """
        try:
            result = self.client.query(
                f"SELECT migration_name FROM {self.settings.CLICKHOUSE_DATABASE}.migrations "
                f"ORDER BY migration_name"
            )
            return [row[0] for row in result.result_rows]
        except Exception:
            return []

    async def _load_migrations_from_files(self) -> List[ClickHouseMigration]:
        """
        Загрузить миграции из upgrade/ папки.

        Returns:
            Список миграций, отсортированных по версии
        """
        migrations = []

        if not self.upgrade_path.exists():
            self.logger.warning(
                "clickhouse_migrator.upgrade_path_not_found",
                path=str(self.upgrade_path),
            )
            return migrations

        # Паттерн для имени файла: V{version}-{name}.sql
        pattern = re.compile(r"^V(\d+)-(.+)\.sql$")

        for sql_file in sorted(self.upgrade_path.glob("*.sql")):
            match = pattern.match(sql_file.name)
            if not match:
                self.logger.warning(
                    "clickhouse_migrator.invalid_migration_filename",
                    filename=sql_file.name,
                )
                continue

            version = match.group(1)
            name = match.group(2)

            # Читаем upgrade SQL
            upgrade_sql = sql_file.read_text(encoding="utf-8")

            # Проверяем наличие downgrade файла
            downgrade_file = self.downgrade_path / sql_file.name
            has_downgrade = downgrade_file.exists()

            migration = ClickHouseMigration(
                version=version,
                name=name,
                filename=sql_file.name,
                upgrade_sql=upgrade_sql,
                has_downgrade=has_downgrade,
            )
            migrations.append(migration)

        return migrations

    async def _validate_all_migrations_safety(
        self, migrations: List[ClickHouseMigration]
    ) -> Dict[str, Any]:
        """
        Валидация безопасности всех миграций.

        Проверяет, что для каждого upgrade существует downgrade.

        Args:
            migrations: Список миграций для проверки

        Returns:
            Словарь с результатами валидации
        """
        missing_downgrades = []

        for migration in migrations:
            if int(migration.version) < 10:
                self.logger.info("clickhouse_migrator.first_iteration.skip")
                continue
            if not migration.has_downgrade:
                missing_downgrades.append(migration.migration_name)
                self.logger.warning(
                    "clickhouse_migrator.missing_downgrade",
                    migration=migration.migration_name,
                    upgrade_file=migration.filename,
                )

        is_safe = len(missing_downgrades) == 0

        if is_safe:
            self.logger.info(
                "clickhouse_migrator.all_migrations_safe",
                total_migrations=len(migrations),
            )
        else:
            self.logger.error(
                "clickhouse_migrator.unsafe_migrations_found",
                count=len(missing_downgrades),
                migrations=missing_downgrades,
            )

        return {
            "is_safe": is_safe,
            "total_migrations": len(migrations),
            "missing_downgrades": missing_downgrades,
        }

    async def _load_downgrade_sql(self, migration_name: str) -> str:
        """
        Загрузить SQL для отката миграции.

        Args:
            migration_name: Название миграции (например, "V0001-create_migrations")

        Returns:
            SQL для отката

        Raises:
            FileNotFoundError: Если downgrade файл не найден
        """
        # Конструируем имя файла из названия миграции
        filename = f"{migration_name}.sql"
        downgrade_file = self.downgrade_path / filename

        if not downgrade_file.exists():
            raise FileNotFoundError(
                f"Downgrade file not found: {downgrade_file}. "
                f"Cannot rollback migration {migration_name}"
            )

        self.logger.debug(
            "clickhouse_migrator.loading_downgrade_sql",
            migration=migration_name,
            file=str(downgrade_file),
        )

        return downgrade_file.read_text(encoding="utf-8")

    async def _apply_migration(self, migration: ClickHouseMigration) -> None:
        """
        Применить upgrade миграцию.

        Args:
            migration: Миграция для применения
        """
        self.logger.info(
            "clickhouse_migrator.applying_migration",
            migration=migration.migration_name,
            filename=migration.filename,
            has_downgrade=migration.has_downgrade,
        )

        # Разделяем на отдельные SQL statements
        statements = [
            stmt.strip()
            for stmt in migration.upgrade_sql.split(";")
            if stmt.strip()
        ]

        for i, statement in enumerate(statements, 1):
            self.logger.debug(
                "clickhouse_migrator.executing_statement",
                migration=migration.migration_name,
                statement_num=i,
                total_statements=len(statements),
            )
            self.client.command(statement)

        # Записываем в таблицу миграций
        self.client.command(
            f"INSERT INTO {self.settings.CLICKHOUSE_DATABASE}.migrations "
            f"(migration_name) VALUES ('{migration.migration_name}')"
        )

        self.logger.info(
            "clickhouse_migrator.migration_applied",
            migration=migration.migration_name,
        )

    async def _execute_downgrade(
        self, migration_name: str, downgrade_sql: str
    ) -> None:
        """
        Выполнить downgrade SQL.

        Args:
            migration_name: Название миграции
            downgrade_sql: SQL для отката
        """
        self.logger.info(
            "clickhouse_migrator.executing_downgrade",
            migration=migration_name,
        )

        # Выполняем downgrade SQL
        statements = [
            stmt.strip() for stmt in downgrade_sql.split(";") if stmt.strip()
        ]

        for i, statement in enumerate(statements, 1):
            self.logger.debug(
                "clickhouse_migrator.executing_downgrade_statement",
                migration=migration_name,
                statement_num=i,
                total_statements=len(statements),
            )
            self.client.command(statement)

        # Удаляем из таблицы миграций
        self.client.command(
            f"ALTER TABLE {self.settings.CLICKHOUSE_DATABASE}.migrations "
            f"DELETE WHERE migration_name = '{migration_name}'"
        )

        self.logger.info(
            "clickhouse_migrator.downgrade_executed",
            migration=migration_name,
        )
