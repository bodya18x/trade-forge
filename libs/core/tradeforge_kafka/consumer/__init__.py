"""
Consumer модуль для работы с Kafka.
"""

from .base import AsyncKafkaConsumer
from .decorators import (
    CircuitBreakerOpenError,
    circuit_breaker,
    log_execution_time,
    retry,
    timeout,
)

__all__ = [
    "AsyncKafkaConsumer",
    "retry",
    "timeout",
    "circuit_breaker",
    "log_execution_time",
    "CircuitBreakerOpenError",
]
