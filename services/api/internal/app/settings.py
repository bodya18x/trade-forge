from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Централизованная конфигурация для сервиса Internal API.
    Загружает переменные из глобального platform/.env и локального .env файлов.
    """

    model_config = SettingsConfigDict(
        env_file=[
            ".env",
            "../../../platform/.env",
        ],  # Сначала локальный, потом глобальный
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Общие настройки сервиса ---
    SERVICE_VERSION: str = Field("0.1.0", description="Версия сервиса")
    SERVICE_NAME: str = Field("internal-api", description="Название сервиса")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        Field("INFO", description="Уровень логирования")
    )
    ENVIRONMENT: str = Field("development", description="Окружение сервиса")

    # --- PostgreSQL (используем компоненты из platform/.env) ---
    POSTGRES_HOST: str = Field("localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(25432, description="PostgreSQL port")
    POSTGRES_DB: str = Field("trader", description="PostgreSQL database name")
    POSTGRES_USER: str = Field("admin", description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(
        "strong_password", description="PostgreSQL password"
    )

    @computed_field
    @property
    def POSTGRES_DSN(self) -> str:
        """Строит асинхронный DSN для PostgreSQL из компонентов."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Redis (используем компоненты из platform/.env) ---
    REDIS_HOST: str = Field("localhost", description="Redis host")
    REDIS_PORT: int = Field(26379, description="Redis port")
    REDIS_PASSWORD: str = Field(
        "strong_password", description="Redis password"
    )
    REDIS_DB: int = Field(3, description="Redis database number для API")

    @computed_field
    @property
    def REDIS_DSN(self) -> str:
        """Строит DSN для Redis из компонентов."""
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    # --- ClickHouse (используем компоненты из platform/.env) ---
    CLICKHOUSE_HOST: str = Field("localhost", description="ClickHouse host")
    CLICKHOUSE_PORT: int = Field(28123, description="ClickHouse HTTP port")
    CLICKHOUSE_USER: str = Field("default", description="ClickHouse username")
    CLICKHOUSE_PASSWORD: str = Field(
        "strong_password", description="ClickHouse password"
    )
    CLICKHOUSE_DB: str = Field(
        "trader", description="ClickHouse database name"
    )

    # --- Kafka Configuration ---
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        "localhost:29093",
        description="Список Kafka-брокеров (comma-separated)",
    )
    KAFKA_BACKTEST_REQUEST_TOPIC: str = Field(
        "trade-forge.backtests.requests.v1",
        description="Топик для отправки задач на бэктест",
    )

    # --- Smart Kafka Producer Config ---
    KAFKA_PRODUCER_ACKS: str = Field(
        "all", description="Acknowledgment level (all, 1, 0)"
    )
    KAFKA_PRODUCER_COMPRESSION: str = Field(
        "gzip", description="Compression type (none, gzip, snappy, lz4, zstd)"
    )
    KAFKA_PRODUCER_BATCH_SIZE: int = Field(
        16384, description="Batch size in bytes"
    )
    KAFKA_PRODUCER_LINGER_MS: int = Field(
        10, description="Linger time in milliseconds"
    )

    # --- Квоты и Лимиты (с дефолтными значениями) ---
    MAX_CONCURRENT_JOBS_PER_USER: int = Field(
        10,
        description="Макс. число одновременных бэктестов на пользователя (унифицировано с Gateway)",
    )
    MAX_DAILY_JOBS_PER_USER: int = Field(
        50, description="Макс. число бэктестов в сутки на пользователя"
    )
    MAX_BARS_PER_BACKTEST: int = Field(
        200000, description="Макс. число свечей (баров) в одном бэктесте"
    )

    # TODO: Данная валидация работает через схемы. Нужно разобраться и
    # централизовано делать, а сейчас у нас и тут и там делается, дубли выходят
    # --- Валидация бэктестов (централизовано в Internal API) ---
    VALID_TIMEFRAMES: list[str] = Field(
        default=["1d", "10min", "1h", "1w", "1m"],
        description="Список допустимых таймфреймов для бэктестинга",
    )
    MAX_INITIAL_BALANCE: float = Field(
        10_000_000.0, description="Максимальный начальный баланс для симуляции"
    )
    MIN_INITIAL_BALANCE: float = Field(
        1000.0, description="Минимальный начальный баланс для симуляции"
    )
    MAX_COMMISSION_PCT: float = Field(
        10.0, description="Максимальная комиссия в процентах"
    )
    MIN_COMMISSION_PCT: float = Field(
        0.0, description="Минимальная комиссия в процентах"
    )
    MAX_POSITION_SIZE_PCT: float = Field(
        500.0, description="Максимальный размер позиции в процентах"
    )
    MIN_POSITION_SIZE_PCT: float = Field(
        0.1, description="Минимальный размер позиции в процентах"
    )
    MAX_TICKER_LENGTH: int = Field(20, description="Максимальная длина тикера")
    MIN_TICKER_LENGTH: int = Field(1, description="Минимальная длина тикера")


# Используем lru_cache для создания синглтона
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
