"""
tradeforge_kafka v2.0.0 - Асинхронная библиотека для работы с Apache Kafka.

Построена на confluent-kafka (librdkafka) с полностью асинхронным API.
Используется в Trade Forge для high-load обработки данных.

Ключевые возможности:
    - 100% async/await - Полностью асинхронный API
    - Pydantic валидация - Автоматическая валидация сообщений
    - Type safety - Generic типы для compile-time безопасности
    - Retry logic - Exponential backoff с настраиваемыми задержками
    - Dead Letter Queue - Автоматическая отправка failed сообщений
    - Observability - Correlation ID, tradeforge_logger, метрики
    - Graceful shutdown - Context managers для корректного завершения

Основные компоненты:
    - AsyncKafkaConsumer: Consumer с валидацией, retry, DLQ
    - AsyncKafkaProducer: Producer с батчингом и метриками
    - KafkaAdmin: Административный клиент для управления топиками
    - AsyncKafkaAdmin: Асинхронная обертка над KafkaAdmin

Примеры использования см. в директории examples/ и README.md
"""

from .admin.async_client import AsyncKafkaAdmin
from .admin.client import KafkaAdmin
from .config import ConsumerConfig, DLQConfig, ProducerConfig
from .consumer.base import AsyncKafkaConsumer
from .consumer.decorators import (
    CircuitBreakerOpenError,
    circuit_breaker,
    log_execution_time,
    retry,
    timeout,
)
from .datatypes import (
    DLQMessage,
    KafkaMessage,
    KafkaMessageMetadata,
    RecordMetadata,
)
from .exceptions import (
    AuthorizationError,
    ConsumerCalledError,
    DLQSendError,
    FatalError,
    MaxRetriesExceededError,
    MessageSizeError,
    MessageValidationError,
    NewTopicError,
    NoBrokersAvailable,
    PublisherIllegalError,
    RetryableError,
    TimeoutError,
    TopicExistsError,
    TransportException,
    UnknownTopicError,
)
from .metrics import ConsumerMetrics, MetricsCollector, ProducerMetrics
from .producer.base import AsyncKafkaProducer

__version__ = "2.0.0"

__all__ = [
    # Consumer
    "AsyncKafkaConsumer",
    # Producer
    "AsyncKafkaProducer",
    # Admin
    "KafkaAdmin",
    "AsyncKafkaAdmin",
    # Config
    "ConsumerConfig",
    "ProducerConfig",
    "DLQConfig",
    # Types
    "KafkaMessage",
    "KafkaMessageMetadata",
    "RecordMetadata",
    "DLQMessage",
    # Metrics
    "ConsumerMetrics",
    "ProducerMetrics",
    "MetricsCollector",
    # Decorators
    "retry",
    "timeout",
    "circuit_breaker",
    "log_execution_time",
    # Exceptions
    "TransportException",
    "TimeoutError",
    "AuthorizationError",
    "NoBrokersAvailable",
    "UnknownTopicError",
    "TopicExistsError",
    "NewTopicError",
    "MessageSizeError",
    "MessageValidationError",
    "ConsumerCalledError",
    "PublisherIllegalError",
    "RetryableError",
    "FatalError",
    "DLQSendError",
    "MaxRetriesExceededError",
    "CircuitBreakerOpenError",
]
