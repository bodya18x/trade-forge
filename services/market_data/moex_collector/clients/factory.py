"""
Фабрика для создания инфраструктурных клиентов и репозиториев.

Централизует создание клиентов для избежания дублирования кода.
"""

from __future__ import annotations

from redis.asyncio import Redis
from tradeforge_kafka import ProducerConfig

from clients.moex_client import AsyncMoexApiClient
from managers import ClickHouseClientPool
from repositories import ClickHouseRepository, RedisStateManager
from settings import Settings


def create_moex_client(settings: Settings) -> AsyncMoexApiClient:
    """
    Создает MOEX API клиент с rate limiting.

    Args:
        settings: Настройки приложения

    Returns:
        Сконфигурированный MOEX API клиент
    """
    return AsyncMoexApiClient(
        rate_limit_requests=settings.MOEX_RATE_LIMIT_REQUESTS,
        rate_limit_seconds=settings.MOEX_RATE_LIMIT_SECONDS,
        timeout=settings.MOEX_TIMEOUT,
    )


def create_redis_client(settings: Settings) -> Redis:
    """
    Создает асинхронный Redis клиент.

    Args:
        settings: Настройки приложения

    Returns:
        Сконфигурированный асинхронный Redis клиент
    """
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
    )


async def create_clickhouse_pool(settings: Settings) -> ClickHouseClientPool:
    """
    Создает и инициализирует пул ClickHouse клиентов.

    Args:
        settings: Настройки приложения

    Returns:
        Инициализированный пул ClickHouse клиентов
    """
    pool = ClickHouseClientPool(
        size=settings.KAFKA_CONSUMER_MAX_CONCURRENT,
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB,
    )
    await pool.initialize()
    return pool


def create_clickhouse_repository(
    pool: ClickHouseClientPool,
) -> ClickHouseRepository:
    """
    Создает ClickHouse репозиторий с пулом клиентов.

    Args:
        pool: Пул ClickHouse клиентов

    Returns:
        Сконфигурированный ClickHouse репозиторий
    """
    return ClickHouseRepository(pool=pool)


def create_state_manager(
    redis_client: Redis,
    clickhouse_repo: ClickHouseRepository,
) -> RedisStateManager:
    """
    Создает менеджер состояния Redis.

    Args:
        redis_client: Асинхронный клиент Redis
        clickhouse_repo: ClickHouse репозиторий для fallback

    Returns:
        Сконфигурированный state manager
    """
    return RedisStateManager(redis_client, clickhouse_repo)


def create_kafka_producer_config(settings: Settings) -> ProducerConfig:
    """
    Создает конфигурацию Kafka producer.

    Args:
        settings: Настройки приложения

    Returns:
        Конфигурация Kafka producer
    """
    return ProducerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        acks=settings.KAFKA_PRODUCER_ACKS,
        compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
        batch_size=settings.KAFKA_PRODUCER_BATCH_SIZE,
        linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
    )


class InfrastructureClients:
    """Контейнер для всех инфраструктурных клиентов."""

    def __init__(
        self,
        moex_client: AsyncMoexApiClient,
        redis_client: Redis,
        clickhouse_pool: ClickHouseClientPool,
        clickhouse_repo: ClickHouseRepository,
        state_manager: RedisStateManager,
    ):
        """
        Инициализирует контейнер инфраструктурных клиентов.

        Args:
            moex_client: MOEX API клиент
            redis_client: Асинхронный Redis клиент
            clickhouse_pool: Пул ClickHouse клиентов
            clickhouse_repo: ClickHouse репозиторий
            state_manager: Менеджер состояния Redis
        """
        self.moex_client = moex_client
        self.redis_client = redis_client
        self.clickhouse_pool = clickhouse_pool
        self.clickhouse_repo = clickhouse_repo
        self.state_manager = state_manager


async def create_infrastructure_clients(
    settings: Settings,
) -> InfrastructureClients:
    """
    Создает все инфраструктурные клиенты одновременно.

    ВАЖНО: Это асинхронная функция, так как инициализирует
    асинхронные клиенты (Redis и ClickHouse пул).

    Args:
        settings: Настройки приложения

    Returns:
        Контейнер со всеми инфраструктурными клиентами
    """
    moex_client = create_moex_client(settings)
    redis_client = create_redis_client(settings)
    clickhouse_pool = await create_clickhouse_pool(settings)
    clickhouse_repo = create_clickhouse_repository(clickhouse_pool)
    state_manager = create_state_manager(redis_client, clickhouse_repo)

    return InfrastructureClients(
        moex_client=moex_client,
        redis_client=redis_client,
        clickhouse_pool=clickhouse_pool,
        clickhouse_repo=clickhouse_repo,
        state_manager=state_manager,
    )
