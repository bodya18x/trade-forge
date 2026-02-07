"""
Trading Engine Application - точка входа сервиса.

CLI интерфейс для запуска backtest и RT режимов.
"""

from __future__ import annotations

import asyncio

import click
from tradeforge_db import close_db, init_db
from tradeforge_kafka import AsyncKafkaProducer, ConsumerConfig, ProducerConfig
from tradeforge_logger import configure_logging, get_logger

from consumers.backtest_consumer import BacktestConsumer
from consumers.rt_consumer import RTConsumer
from models.kafka_messages import FatCandleMessage
from repositories.clickhouse import ClickHouseClientPool, ClickHouseRepository
from repositories.postgres import (
    BacktestRepository,
    IndicatorRepository,
    TickerRepository,
)
from settings import settings

logger = get_logger(__name__)


async def _initialize_common_resources(
    mode: str,
) -> tuple[BacktestRepository, TickerRepository, IndicatorRepository]:
    """
    Инициализирует общие ресурсы для всех режимов работы.

    Выполняет общую инициализацию:
    - Настраивает логирование
    - Инициализирует PostgreSQL соединение
    - Создает репозитории

    Args:
        mode: Режим работы ("backtest" или "realtime").

    Returns:
        Tuple из трех репозиториев: (BacktestRepository, TickerRepository, IndicatorRepository).
    """
    # 1. Инициализируем логирование
    configure_logging(
        service_name=f"trading-engine-{mode}",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
        enable_json=True,
        enable_console_colors=False,
    )

    logger.info(
        "app.starting",
        mode=mode,
        environment=settings.ENVIRONMENT,
    )

    # 2. Инициализируем PostgreSQL
    init_db()
    logger.info("app.database_initialized")

    # 3. Создаем репозитории (Dependency Injection)
    logger.info("app.initializing_repositories")
    backtest_repo = BacktestRepository()
    ticker_repo = TickerRepository(cache_ttl_hours=1)
    indicator_repo = IndicatorRepository()

    logger.info(
        "app.repositories_initialized",
        repositories=[
            "BacktestRepository",
            "TickerRepository(TTL=1h)",
            "IndicatorRepository",
        ],
    )

    return backtest_repo, ticker_repo, indicator_repo


@click.group()
def cli():
    """Trading Engine CLI."""
    pass


@cli.command()
def consume_backtest():
    """Запуск Backtest Worker для обработки задач на бэктест."""
    asyncio.run(start_backtest_worker())


@cli.command()
def consume_rt():
    """Запуск RT Processor для обработки real-time свечей."""
    asyncio.run(start_rt_processor())


async def start_backtest_worker():
    """
    Запускает Backtest Worker с Dependency Injection.

    Инициализирует:
    - Общие ресурсы (логирование, PostgreSQL, репозитории)
    - ClickHouse пул
    - Kafka producer и consumer
    - Graceful shutdown
    """
    # 1. Инициализируем общие ресурсы
    backtest_repo, ticker_repo, indicator_repo = (
        await _initialize_common_resources("backtest")
    )

    # 2. Создаем ClickHouse repository
    clickhouse_repo = ClickHouseRepository()
    logger.info("app.clickhouse_repository_initialized")

    # 3. Создаем ClickHouse pool
    ch_pool = ClickHouseClientPool(
        size=settings.KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT,
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB,
    )
    await ch_pool.initialize()
    logger.info("app.clickhouse_pool_initialized")

    # 4. Создаем Конфиги
    producer_config = ProducerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        acks=settings.KAFKA_PRODUCER_ACKS,
        compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
        batch_size=settings.KAFKA_PRODUCER_BATCH_SIZE,
        linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
    )

    consumer_config = ConsumerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_BACKTEST_WORKER,
        topic=settings.KAFKA_TOPIC_BACKTEST_REQUESTS,
        max_poll_records=settings.KAFKA_BACKTEST_CONSUMER_MAX_POLL_RECORDS,
        max_concurrent_messages=settings.KAFKA_BACKTEST_CONSUMER_MAX_CONCURRENT,
        max_retries=settings.KAFKA_BACKTEST_CONSUMER_MAX_RETRIES,
        use_dlq=settings.KAFKA_BACKTEST_CONSUMER_USE_DLQ,
    )

    try:
        # 5. Запускаем Kafka consumer с инжекцией зависимостей
        async with AsyncKafkaProducer(producer_config) as producer:
            logger.info("app.producer_connected")

            # Инжектим все зависимости в consumer
            consumer = BacktestConsumer(
                config=consumer_config,
                ch_client_pool=ch_pool,
                producer=producer,
                backtest_repo=backtest_repo,
                ticker_repo=ticker_repo,
                indicator_repo=indicator_repo,
                clickhouse_repo=clickhouse_repo,
            )

            logger.info(
                "app.consumer_initialized", injection="dependencies_injected"
            )

            async with consumer:
                logger.info("app.consumer_connected")
                await consumer.start()

    except KeyboardInterrupt:
        logger.info("app.interrupted")
    except Exception as exc:
        logger.exception("app.fatal_error", error=str(exc))
        raise
    finally:
        # Graceful shutdown
        logger.info("app.shutting_down")
        await ch_pool.close()
        await close_db()
        logger.info("app.shutdown_complete")


async def start_rt_processor():
    """
    Запускает RT Processor (ЗАГОТОВКА).

    См. TODO.md #1 - запланировано к реализации после завершения MVP бэктестов.
    """
    # 1. Инициализируем общие ресурсы
    _backtest_repo, _ticker_repo, _indicator_repo = (
        await _initialize_common_resources("realtime")
    )

    # Запланировано: инициализировать Redis для состояния позиций (TODO.md #1)

    # Создаем Kafka producer для торговых приказов
    producer_config = ProducerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        acks=settings.KAFKA_PRODUCER_ACKS,
        compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
    )
    producer = AsyncKafkaProducer(producer_config)
    await producer.start()
    logger.info("app.producer_started")

    # Создаем RT consumer
    consumer_config = ConsumerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_RT_PROCESSOR,
        topics=[settings.KAFKA_TOPIC_RT_CANDLES],
        max_concurrent_messages=settings.KAFKA_RT_CONSUMER_MAX_CONCURRENT,
        schema=FatCandleMessage,
    )

    consumer = RTConsumer(config=consumer_config)

    logger.info("app.rt_consumer_created")

    try:
        async with consumer:
            logger.info("app.rt_consumer_started")
            logger.warning("app.rt_mode_not_fully_implemented")
            await consumer.start()
    except KeyboardInterrupt:
        logger.info("app.interrupted")
    finally:
        logger.info("app.shutting_down")
        await producer.stop()
        await close_db()
        logger.info("app.shutdown_complete")


if __name__ == "__main__":
    cli()
