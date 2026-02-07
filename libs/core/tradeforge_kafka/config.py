"""
Конфигурационные классы для Kafka компонентов через Pydantic Settings.

Все настройки выносятся в переменные окружения для гибкости в разных средах.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConsumerConfig(BaseSettings):
    """
    Конфигурация Kafka Consumer.

    Все параметры можно переопределить через переменные окружения
    с префиксом KAFKA_CONSUMER_.

    Example:
        ```bash
        export KAFKA_CONSUMER_BOOTSTRAP_SERVERS="localhost:9092"
        export KAFKA_CONSUMER_GROUP_ID="my-service"
        export KAFKA_CONSUMER_TOPIC="my-topic"
        ```
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_CONSUMER_")

    # Обязательные параметры
    bootstrap_servers: str = Field(
        ...,
        description="Адрес Kafka брокеров (host:port или host1:port1,host2:port2)",
    )
    topic: str = Field(..., description="Топик для подписки")
    group_id: str = Field(..., description="Consumer Group ID")

    # Стратегия чтения
    auto_offset_reset: Literal["earliest", "latest", "none"] = Field(
        default="earliest",
        description="Стратегия чтения офсетов при отсутствии committed offset",
    )

    # Производительность
    max_poll_records: int = Field(
        default=500, gt=0, description="Максимум сообщений за один poll"
    )
    max_poll_interval_ms: int = Field(
        default=300000,
        gt=0,
        description="Максимальный интервал между poll (мс)",
    )
    session_timeout_ms: int = Field(
        default=10000, gt=0, description="Таймаут сессии (мс)"
    )
    fetch_wait_max_ms: int = Field(
        default=500,
        gt=0,
        description="Максимальное время ожидания данных (мс)",
    )

    # Параллельная обработка
    max_concurrent_messages: int = Field(
        default=1,
        gt=0,
        description="Максимум сообщений, обрабатываемых одновременно (1 = последовательно, 100 = до 100 параллельно)",
    )

    # Retry логика
    retry_on_error: bool = Field(
        default=True, description="Повторять обработку при ошибках"
    )
    max_retries: int = Field(
        default=3, ge=0, description="Максимум попыток обработки"
    )
    retry_delays: list[float] = Field(
        default=[1.0, 5.0, 15.0],
        description="Задержки между retry (exponential backoff)",
    )

    # Dead Letter Queue
    use_dlq: bool = Field(
        default=True, description="Отправлять failed сообщения в DLQ"
    )
    dlq_topic_suffix: str = Field(
        default=".dlq", description="Суффикс для DLQ топика"
    )

    # Логирование
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Уровень логирования"
    )
    log_every_n_messages: int = Field(
        default=100,
        gt=0,
        description="Логировать каждое N-ое сообщение на уровне INFO",
    )
    log_slow_messages: bool = Field(
        default=True, description="Логировать медленные сообщения"
    )
    slow_threshold_ms: float = Field(
        default=1000.0, gt=0, description="Порог для slow message (мс)"
    )

    # Внутренние таймауты и задержки
    poll_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        description="Таймаут poll операции в секундах",
    )
    process_loop_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        description="Таймаут ожидания сообщения в process loop",
    )
    concurrent_task_sleep_ms: float = Field(
        default=10.0,
        gt=0,
        description="Задержка при ожидании освобождения слота для параллельной обработки (мс)",
    )

    # Graceful Shutdown (Two-Phase)
    shutdown_soft_timeout_seconds: int = Field(
        default=60,
        gt=0,
        description="Phase 1: Soft shutdown - время ожидания естественного завершения активных задач (секунды)",
    )
    shutdown_hard_timeout_seconds: int = Field(
        default=5,
        gt=0,
        description="Phase 2: Hard shutdown - время ожидания принудительной отмены задач (секунды)",
    )


class ProducerConfig(BaseSettings):
    """
    Конфигурация Kafka Producer.

    Все параметры можно переопределить через переменные окружения
    с префиксом KAFKA_PRODUCER_.

    Example:
        ```bash
        export KAFKA_PRODUCER_BOOTSTRAP_SERVERS="localhost:9092"
        export KAFKA_PRODUCER_ACKS="all"
        export KAFKA_PRODUCER_COMPRESSION_TYPE="gzip"
        ```
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_PRODUCER_")

    # Обязательные параметры
    bootstrap_servers: str = Field(..., description="Адрес Kafka брокеров")

    # Гарантии доставки
    acks: Literal["0", "1", "all"] = Field(
        default="all",
        description="Уровень подтверждения доставки (0=no wait, 1=leader, all=all replicas)",
    )
    retries: int = Field(
        default=3, ge=0, description="Количество повторов при ошибке отправки"
    )
    max_in_flight_requests_per_connection: int = Field(
        default=5, gt=0, description="Макс. неподтверждённых запросов"
    )

    # Производительность
    compression_type: Literal["none", "gzip", "snappy", "lz4", "zstd"] = Field(
        default="gzip", description="Тип компрессии"
    )
    batch_size: int = Field(
        default=16384, gt=0, description="Размер батча в байтах"
    )
    linger_ms: int = Field(
        default=10, ge=0, description="Задержка перед отправкой батча (мс)"
    )
    buffer_memory: int = Field(
        default=32768, gt=0, description="Размер буфера producer (килобайты)"
    )

    # Таймауты
    request_timeout_ms: int = Field(
        default=30000, gt=0, description="Таймаут запроса (мс)"
    )
    delivery_timeout_ms: int = Field(
        default=120000, gt=0, description="Таймаут доставки (мс)"
    )

    # Внутренние настройки poll loop
    poll_interval_seconds: float = Field(
        default=0.1,
        gt=0,
        description="Интервал вызова poll для обработки delivery callbacks (секунды)",
    )
    poll_sleep_seconds: float = Field(
        default=0.01,
        gt=0,
        description="Задержка между итерациями poll loop для снижения CPU нагрузки (секунды)",
    )
    shutdown_poll_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Таймаут ожидания завершения poll task при shutdown (секунды)",
    )
    shutdown_flush_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        description="Таймаут flush операции при shutdown (секунды)",
    )


class DLQConfig(BaseSettings):
    """
    Конфигурация Dead Letter Queue.

    Example:
        ```bash
        export KAFKA_DLQ_ENABLED="true"
        export KAFKA_DLQ_AUTO_REPLAY="false"
        ```
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_DLQ_")

    enabled: bool = Field(default=True, description="Включить DLQ")
    topic_suffix: str = Field(
        default=".dlq", description="Суффикс для DLQ топиков"
    )
    max_retries: int = Field(
        default=3, gt=0, description="Максимум попыток перед DLQ"
    )
    retry_delays: list[float] = Field(
        default=[1.0, 5.0, 15.0], description="Задержки между retry"
    )

    # Auto-replay из DLQ
    auto_replay: bool = Field(
        default=False,
        description="Автоматически переотправлять из DLQ в основной топик",
    )
    replay_delay_minutes: int = Field(
        default=30, gt=0, description="Задержка перед replay (минуты)"
    )
