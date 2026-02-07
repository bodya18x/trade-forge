"""
Настройки сервиса миграций Trade Forge.

Все настройки загружаются из переменных окружения с использованием Pydantic Settings.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MigratorSettings(BaseSettings):
    """
    Настройки для всех типов миграций в Trade Forge.

    Attributes:
        POSTGRES_*: Настройки PostgreSQL
        CLICKHOUSE_*: Настройки ClickHouse
        KAFKA_*: Настройки Kafka
        MIGRATION_*: Общие настройки миграций
        ENVIRONMENT: Окружение (development/staging/production)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # ===================================================================
    # PostgreSQL Settings
    # ===================================================================
    POSTGRES_HOST: str = Field(description="PostgreSQL хост")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL порт")
    POSTGRES_DB: str = Field(description="Имя базы данных")
    POSTGRES_USER: str = Field(description="Пользователь PostgreSQL")
    POSTGRES_PASSWORD: str = Field(description="Пароль PostgreSQL")
    POSTGRES_POOL_SIZE: int = Field(
        default=5, description="Размер пула соединений"
    )
    POSTGRES_MAX_OVERFLOW: int = Field(
        default=10, description="Максимальное переполнение пула"
    )
    POSTGRES_ENCODING: str = Field(default="utf8", description="Кодировка БД")

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        """Полный URL подключения к PostgreSQL."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ===================================================================
    # ClickHouse Settings
    # ===================================================================
    CLICKHOUSE_HOST: str = Field(
        default="clickhouse", description="ClickHouse хост"
    )
    CLICKHOUSE_PORT: int = Field(
        default=8123, description="ClickHouse HTTP порт"
    )
    CLICKHOUSE_USER: str = Field(
        default="admin", description="ClickHouse пользователь"
    )
    CLICKHOUSE_PASSWORD: str = Field(description="ClickHouse пароль")
    CLICKHOUSE_DATABASE: str = Field(
        default="trader", description="ClickHouse база данных"
    )
    CLICKHOUSE_CONNECT_TIMEOUT: int = Field(
        default=30, description="Таймаут подключения (сек)"
    )
    CLICKHOUSE_SEND_RECEIVE_TIMEOUT: int = Field(
        default=300, description="Таймаут отправки/получения (сек)"
    )

    # ===================================================================
    # Kafka Settings
    # ===================================================================
    KAFKA_BOOTSTRAP_SERVERS: str = Field(description="Kafka bootstrap серверы")
    KAFKA_REQUEST_TIMEOUT_MS: int = Field(
        default=30000, description="Таймаут запроса к Kafka (мс)"
    )
    KAFKA_CONNECTIONS_MAX_IDLE_MS: int = Field(
        default=540000,
        description="Максимальное время простоя соединения (мс)",
    )

    # ===================================================================
    # Migration Settings
    # ===================================================================
    MIGRATION_RETRY_MAX_ATTEMPTS: int = Field(
        default=3, description="Максимальное количество попыток"
    )
    MIGRATION_RETRY_DELAY: int = Field(
        default=5, description="Задержка между попытками (сек)"
    )
    MIGRATION_TIMEOUT: int = Field(
        default=300, description="Общий таймаут миграций (сек)"
    )
    MIGRATION_HEALTH_CHECK_TIMEOUT: int = Field(
        default=30, description="Таймаут health check (сек)"
    )

    # Флаг для включения миграций
    MIGRATE: str = Field(
        default="disabled",
        description='Флаг включения миграций ("enabled")',
    )

    # ===================================================================
    # Application Settings
    # ===================================================================
    LOG_LEVEL: str = Field(default="INFO", description="Уровень логирования")
    ENVIRONMENT: str = Field(
        default="development", description="Окружение приложения"
    )
    SERVICE_NAME: str = Field(
        default="migrator", description="Имя сервиса для логов"
    )

    def is_migration_enabled(self) -> bool:
        """
        Проверяет, включены ли миграции.
        """
        return self.MIGRATE.lower() == "enabled"


@lru_cache
def get_settings() -> MigratorSettings:
    """
    Получить экземпляр настроек (синглтон).

    Returns:
        Настройки миграций
    """
    return MigratorSettings()
