"""
Settings для Data Processor сервиса.

Все конфигурационные параметры для Kafka, Redis, ClickHouse, PostgreSQL.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация data_processor сервиса."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        ..., description="Kafka bootstrap servers"
    )
    KAFKA_RT_CANDLES_TOPIC: str = Field(
        ..., description="Topic для сырых свечей (RT)"
    )
    KAFKA_RT_CALC_GROUP: str = Field(..., description="Consumer group для RT")
    KAFKA_PROCESSED_CANDLES_RT_TOPIC: str = Field(
        ..., description="Topic для обработанных свечей (RT)"
    )
    KAFKA_BATCH_CALCULATION_TOPIC: str = Field(
        ..., description="Topic для запросов на batch расчет"
    )
    KAFKA_BATCH_CALC_GROUP: str = Field(
        ..., description="Consumer group для batch"
    )
    KAFKA_BACKTESTS_TOPIC: str = Field(
        ..., description="Topic для ответов в Trading Engine"
    )

    KAFKA_RT_CONSUMER_MAX_POLL_RECORDS: int = Field(
        500, description="Max poll records для RT"
    )
    KAFKA_RT_CONSUMER_MAX_CONCURRENT: int = Field(
        1, description="Последовательная обработка для RT"
    )
    KAFKA_RT_CONSUMER_MAX_RETRIES: int = Field(
        3, description="Max retries для RT"
    )
    KAFKA_RT_CONSUMER_USE_DLQ: bool = Field(
        True, description="Использовать DLQ для RT"
    )

    KAFKA_BATCH_CONSUMER_MAX_POLL_RECORDS: int = Field(
        100, description="Max poll records для batch"
    )
    KAFKA_BATCH_CONSUMER_MAX_CONCURRENT: int = Field(
        5, description="Параллельная обработка для batch"
    )
    KAFKA_BATCH_CONSUMER_MAX_RETRIES: int = Field(
        3, description="Max retries для batch"
    )
    KAFKA_BATCH_CONSUMER_USE_DLQ: bool = Field(
        True, description="Использовать DLQ для batch"
    )

    KAFKA_PRODUCER_ACKS: str = Field("all", description="Producer acks")
    KAFKA_PRODUCER_COMPRESSION: str = Field("gzip", description="Тип сжатия")
    KAFKA_PRODUCER_BATCH_SIZE: int = Field(16384, description="Размер батча")
    KAFKA_PRODUCER_LINGER_MS: int = Field(10, description="Linger ms")

    LOG_LEVEL: str = Field("INFO", description="Уровень логирования")
    ENVIRONMENT: str = Field("development", description="Окружение")
    RUN_ARG: str = Field(
        "realtime", description="Режим запуска (realtime|batch)"
    )

    REDIS_HOST: str = Field(..., description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_DB: int = Field(0, description="Redis database number")
    REDIS_PASSWORD: str = Field(..., description="Redis password")

    CLICKHOUSE_HOST: str = Field(..., description="ClickHouse host")
    CLICKHOUSE_PORT: int = Field(8123, description="ClickHouse HTTP port")
    CLICKHOUSE_USER: str = Field(..., description="ClickHouse user")
    CLICKHOUSE_PASSWORD: str = Field(..., description="ClickHouse password")
    CLICKHOUSE_DB: str = Field(..., description="ClickHouse database")
    MAX_PARTITIONS_PER_INSERT: int = Field(
        1000, description="Max partitions per insert"
    )

    @field_validator("KAFKA_RT_CONSUMER_MAX_CONCURRENT")
    @classmethod
    def validate_rt_concurrent(cls, v: int) -> int:
        """
        Валидация RT consumer max_concurrent.

        RT consumer использует общий ClickHouse клиент,
        поэтому ДОЛЖЕН работать последовательно (max_concurrent=1).
        """
        if v != 1:
            raise ValueError(
                "RT consumer MUST use max_concurrent=1 for current implementation. "
                "This is required because RT consumer shares a single ClickHouse "
                "client which is not thread-safe."
            )
        return v

    @field_validator("MAX_PARTITIONS_PER_INSERT")
    @classmethod
    def validate_max_partitions(cls, v: int) -> int:
        """Валидация MAX_PARTITIONS_PER_INSERT."""
        if v <= 0:
            raise ValueError(
                f"MAX_PARTITIONS_PER_INSERT must be positive, got {v}"
            )
        if v > 10000:
            raise ValueError(
                f"MAX_PARTITIONS_PER_INSERT is too high ({v}), "
                "recommend <= 10000 to avoid ClickHouse performance issues"
            )
        return v

    @field_validator("KAFKA_BATCH_CONSUMER_MAX_CONCURRENT")
    @classmethod
    def validate_batch_concurrent(cls, v: int) -> int:
        """Валидация Batch consumer max_concurrent."""
        if v <= 0:
            raise ValueError(
                f"KAFKA_BATCH_CONSUMER_MAX_CONCURRENT must be positive, got {v}"
            )
        if v > 20:
            raise ValueError(
                f"KAFKA_BATCH_CONSUMER_MAX_CONCURRENT is too high ({v}), "
                "recommend <= 20 to avoid resource exhaustion"
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
            # Warning: не останавливаем, но логируем
            import warnings

            warnings.warn(
                f"KAFKA_PRODUCER_ACKS='{v}' may lead to data loss. "
                "Recommended value is 'all' for production.",
                UserWarning,
            )
        return v

    @field_validator("REDIS_PORT", "CLICKHOUSE_PORT")
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

    @field_validator("RUN_ARG")
    @classmethod
    def validate_run_arg(cls, v: str) -> str:
        """Валидация режима запуска."""
        allowed = ["realtime", "batch"]
        if v not in allowed:
            raise ValueError(f"RUN_ARG must be one of {allowed}, got '{v}'")
        return v


settings = Settings()
