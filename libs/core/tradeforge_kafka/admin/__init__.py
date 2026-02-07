"""
Admin модуль для управления Kafka топиками.
"""

from .async_client import AsyncKafkaAdmin
from .client import KafkaAdmin

__all__ = ["KafkaAdmin", "AsyncKafkaAdmin"]
