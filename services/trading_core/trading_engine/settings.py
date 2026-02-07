"""
Настройки для Trading Engine сервиса.

Все конфигурационные параметры для Kafka, ClickHouse, PostgreSQL.
Включает валидаторы Pydantic V2 для обеспечения корректности конфигурации.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация Trading Engine сервиса."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- ClickHouse ---
    CLICKHOUSE_HOST: str = Field(..., description="ClickHouse host")
    CLICKHOUSE_PORT: int = Field(8123, description="ClickHouse HTTP port")
    CLICKHOUSE_USER: str = Field("default", description="ClickHouse user")
    CLICKHOUSE_PASSWORD: str = Field("", description="ClickHouse password")
    CLICKHOUSE_DB: str = Field("trader", description="ClickHouse database")

    # --- Redis ---
    REDIS_HOST: str = Field(..., description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_DB: int = Field(0, description="Redis database number")
    REDIS_PASSWORD: str | None = Field(None, description="Redis password")

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        ..., description="Kafka bootstrap servers (comma-separated)"
    )

    # Входящие топики
    KAFKA_TOPIC_RT_CANDLES: str = Field(
        "trade-forge.indicators.candles.processed.rt.v1",
        description="Топик с жирными свечами для RT",
    )
    KAFKA_TOPIC_BACKTEST_REQUESTS: str = Field(
        "trade-forge.backtests.requests.v1",
        description="Топик с задачами на бэктест",
    )

    # Исходящие топики
    KAFKA_TOPIC_TRADE_ORDERS: str = Field(
        "trade-forge.trading.orders.v1",
        description="Топик с торговыми приказами",
    )
    KAFKA_TOPIC_INDICATOR_CALC_REQUEST: str = Field(
        "trade-forge.backtesting.indicators.calculation-requested.v1",
        description="Топик с запросами на расчет индикаторов",
    )

    # Группы консьюмеров
    KAFKA_GROUP_RT_PROCESSOR: str = Field(
        "trading-engine-rt-processor-group",
        description="Group ID для RT-процессора",
    )
    KAFKA_GROUP_BACKTEST_WORKER: str = Field(
        "trading-engine-backtest-worker-group",
        description="Group ID для Backtest воркера",
    )

    # Настройки Backtest Consumer
    KAFKA_BACKTEST_CONSUMER_MAX_POLL_RECORDS: int = Field(
        100, description="Max poll records для backtest consumer"
    )
    KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT: int = Field(
        5, description="Параллельная обработка бэктестов"
    )
    KAFKA_BACKTEST_CONSUMER_MAX_RETRIES: int = Field(
        3, description="Max retries для backtest consumer"
    )
    KAFKA_BACKTEST_CONSUMER_USE_DLQ: bool = Field(
        True, description="Использовать DLQ для backtest consumer"
    )

    # Настройки RT Consumer
    KAFKA_RT_CONSUMER_MAX_CONCURRENT: int = Field(
        1, description="Последовательная обработка для RT"
    )

    # Настройки Producer
    KAFKA_PRODUCER_ACKS: str = Field("all", description="Producer acks")
    KAFKA_PRODUCER_COMPRESSION: str = Field("gzip", description="Тип сжатия")
    KAFKA_PRODUCER_BATCH_SIZE: int = Field(16384, description="Размер батча")
    KAFKA_PRODUCER_LINGER_MS: int = Field(10, description="Linger ms")

    # --- Общие настройки сервиса ---
    LOG_LEVEL: str = Field("INFO", description="Уровень логирования")
    ENVIRONMENT: str = Field("development", description="Окружение")
    RUN_ARG: str = Field(
        "backtest", description="Режим запуска (backtest|realtime)"
    )

    @field_validator("CLICKHOUSE_PORT", "REDIS_PORT")
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
        allowed = ["backtest", "realtime"]
        if v not in allowed:
            raise ValueError(f"RUN_ARG must be one of {allowed}, got '{v}'")
        return v

    @field_validator("KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT")
    @classmethod
    def validate_backtest_concurrent(cls, v: int) -> int:
        """Валидация Backtest consumer max_concurrent."""
        if v <= 0:
            raise ValueError(
                f"KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT must be positive, got {v}"
            )
        if v > 20:
            raise ValueError(
                f"KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT is too high ({v}), "
                "recommend <= 20 to avoid resource exhaustion"
            )
        return v

    @field_validator("KAFKA_RT_CONSUMER_MAX_CONCURRENT")
    @classmethod
    def validate_rt_concurrent(cls, v: int) -> int:
        """Валидация RT consumer max_concurrent."""
        if v != 1:
            raise ValueError(
                "RT consumer MUST use max_concurrent=1 for sequential processing"
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


# Создаем единый экземпляр настроек для всего приложения
settings = Settings()
