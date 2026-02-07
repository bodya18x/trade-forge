"""
Kafka consumers.

CollectionConsumer - универсальный consumer с роутингом задач.
"""

from __future__ import annotations

from .collection_consumer import CollectionConsumer

__all__ = [
    "CollectionConsumer",
]
