"""
Settings для MOEX Collector сервиса.

Все конфигурационные параметры для Kafka, Redis, ClickHouse, PostgreSQL, MOEX API.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация для сервиса MOEX Collector."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application Mode ---
    PUBLISH_TO_KAFKA: bool = Field(
        True, description="Публиковать собранные данные в Kafka"
    )

    # --- Logging ---
    LOG_LEVEL: str = Field("INFO", description="Уровень логирования")
    ENVIRONMENT: str = Field(
        "development",
        description="Окружение (development, staging, production)",
    )

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        ..., description="Адреса Kafka bootstrap серверов"
    )

    # Топики
    KAFKA_COLLECTOR_TASKS_TOPIC: str = Field(
        "trade-forge.market-collectors.tasks",
        description="Топик с задачами для сбора данных",
    )
    KAFKA_CANDLES_TOPIC: str = Field(
        "trade-forge.marketdata.candles.raw.v1",
        description="Топик для публикации сырых свечей",
    )

    # Consumer settings
    KAFKA_CONSUMER_GROUP: str = Field(
        "moex-collector-group", description="ID группы консьюмера"
    )
    KAFKA_CONSUMER_MAX_CONCURRENT: int = Field(
        30, description="Параллельная обработка задач"
    )
    KAFKA_CONSUMER_MAX_RETRIES: int = Field(
        3, description="Максимум попыток повтора"
    )
    KAFKA_CONSUMER_USE_DLQ: bool = Field(True, description="Использовать DLQ")

    # Producer settings
    KAFKA_PRODUCER_ACKS: str = Field(
        "all", description="Подтверждения producer"
    )
    KAFKA_PRODUCER_COMPRESSION: str = Field("gzip", description="Сжатие")
    KAFKA_PRODUCER_BATCH_SIZE: int = Field(16384, description="Размер батча")
    KAFKA_PRODUCER_LINGER_MS: int = Field(
        10, description="Задержка батчирования (мс)"
    )

    # --- MOEX API ---
    MOEX_RATE_LIMIT_REQUESTS: int = Field(
        5, description="Максимум запросов к MOEX API за интервал"
    )
    MOEX_RATE_LIMIT_SECONDS: float = Field(
        1.0, description="Интервал для rate limiting (секунды)"
    )
    MOEX_TIMEOUT: int = Field(15, description="Таймаут запросов к MOEX (сек)")

    # --- Redis ---
    REDIS_HOST: str = Field(..., description="Хост Redis")
    REDIS_PORT: int = Field(6379, description="Порт Redis")
    REDIS_DB: int = Field(0, description="Номер базы данных Redis")
    REDIS_PASSWORD: str = Field(..., description="Пароль Redis")

    # --- ClickHouse ---
    CLICKHOUSE_HOST: str = Field(..., description="Хост ClickHouse")
    CLICKHOUSE_PORT: int = Field(8123, description="HTTP порт ClickHouse")
    CLICKHOUSE_USER: str = Field(..., description="Пользователь ClickHouse")
    CLICKHOUSE_PASSWORD: str = Field(..., description="Пароль ClickHouse")
    CLICKHOUSE_DB: str = Field(..., description="База данных ClickHouse")

    # --- PostgreSQL ---
    POSTGRES_HOST: str = Field(..., description="Хост PostgreSQL")
    POSTGRES_PORT: int = Field(5432, description="Порт PostgreSQL")
    POSTGRES_USER: str = Field(..., description="Пользователь PostgreSQL")
    POSTGRES_PASSWORD: str = Field(..., description="Пароль PostgreSQL")
    POSTGRES_DB: str = Field(..., description="База данных PostgreSQL")

    @field_validator("CLICKHOUSE_PORT", "REDIS_PORT", "POSTGRES_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Валидация портов."""
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    @field_validator("REDIS_DB")
    @classmethod
    def validate_redis_db(cls, v: int) -> int:
        """Валидация Redis database number."""
        if not 0 <= v <= 15:
            raise ValueError(f"Redis DB must be between 0 and 15, got {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Валидация log level."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got '{v}'")
        return v_upper

    @field_validator("KAFKA_CONSUMER_MAX_CONCURRENT")
    @classmethod
    def validate_consumer_concurrent(cls, v: int) -> int:
        """Валидация consumer max_concurrent."""
        if v <= 0:
            raise ValueError(
                f"KAFKA_CONSUMER_MAX_CONCURRENT must be positive, got {v}"
            )
        if v > 100:
            raise ValueError(
                f"KAFKA_CONSUMER_MAX_CONCURRENT is too high ({v}), "
                "recommend <= 100 to avoid resource exhaustion"
            )
        return v

    @field_validator("KAFKA_PRODUCER_ACKS")
    @classmethod
    def validate_producer_acks(cls, v: str) -> str:
        """Валидация producer acks для надежности."""
        allowed = ["all", "-1", "1", "0"]
        if v not in allowed:
            raise ValueError(
                f"KAFKA_PRODUCER_ACKS must be one of {allowed}, got '{v}'"
            )
        if v in ["0", "1"]:
            import warnings

            warnings.warn(
                f"KAFKA_PRODUCER_ACKS='{v}' may lead to data loss. "
                "Recommended value is 'all' for production.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("MOEX_RATE_LIMIT_REQUESTS")
    @classmethod
    def validate_moex_rate_limit(cls, v: int) -> int:
        """Валидация MOEX rate limit."""
        if v <= 0:
            raise ValueError(
                f"MOEX_RATE_LIMIT_REQUESTS must be positive, got {v}"
            )
        if v > 100:
            import warnings

            warnings.warn(
                f"MOEX_RATE_LIMIT_REQUESTS is high ({v}), "
                "may hit MOEX API limits",
                UserWarning,
                stacklevel=2,
            )
        return v


# Создаем единый экземпляр настроек для всего приложения
settings = Settings()
