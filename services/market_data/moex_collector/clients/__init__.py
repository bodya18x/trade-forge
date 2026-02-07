"""
API клиенты для работы с внешними сервисами.

Клиенты для работы с MOEX ISS API и другими внешними источниками данных.
"""

from __future__ import annotations

from .factory import (
    InfrastructureClients,
    create_clickhouse_pool,
    create_clickhouse_repository,
    create_infrastructure_clients,
    create_kafka_producer_config,
    create_moex_client,
    create_redis_client,
    create_state_manager,
)
from .moex_client import AsyncMoexApiClient

__all__ = [
    "AsyncMoexApiClient",
    "InfrastructureClients",
    "create_moex_client",
    "create_redis_client",
    "create_clickhouse_pool",
    "create_clickhouse_repository",
    "create_state_manager",
    "create_kafka_producer_config",
    "create_infrastructure_clients",
]
