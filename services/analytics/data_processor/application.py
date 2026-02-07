"""
Application entry point для Data Processor сервиса.

CLI команды для запуска RT и Batch consumers.
"""

from __future__ import annotations

import asyncio

import click
from tradeforge_db import DatabaseSettings, close_db, init_db
from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_kafka.config import ConsumerConfig, ProducerConfig
from tradeforge_logger import configure_logging, get_logger

from managers.cache_manager import CacheManager
from managers.clickhouse_pool import ClickHouseClientPool
from managers.lock_manager import DistributedLockManager
from managers.storage_manager import AsyncStorageManager
from modules.consumers.batch_consumer import BatchIndicatorConsumer
from modules.consumers.rt_consumer import RealTimeIndicatorConsumer
from settings import settings

configure_logging(
    service_name=f"data-processor-{settings.RUN_ARG}",
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
    enable_json=True,
    enable_console_colors=False,
)
logger = get_logger(__name__)


async def run_rt_consumer() -> None:
    """
    Запускает Real-Time consumer для обработки индикаторов.

    Инициализирует все необходимые зависимости (БД, Kafka producer/consumer,
    managers) и запускает RT consumer для обработки свечей в реальном времени.

    Raises:
        Exception: При критической ошибке инициализации или работы consumer.
    """
    logger.info("rt_app.starting")

    db_settings = DatabaseSettings()
    init_db(db_settings)
    logger.info("rt_app.db_initialized")

    consumer_config = ConsumerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_RT_CANDLES_TOPIC,
        group_id=settings.KAFKA_RT_CALC_GROUP,
        max_poll_records=settings.KAFKA_RT_CONSUMER_MAX_POLL_RECORDS,
        max_concurrent_messages=settings.KAFKA_RT_CONSUMER_MAX_CONCURRENT,
        max_retries=settings.KAFKA_RT_CONSUMER_MAX_RETRIES,
        use_dlq=settings.KAFKA_RT_CONSUMER_USE_DLQ,
        auto_offset_reset="earliest",
        slow_threshold_ms=10000.0,
    )

    producer_config = ProducerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        acks=settings.KAFKA_PRODUCER_ACKS,
        compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
        batch_size=settings.KAFKA_PRODUCER_BATCH_SIZE,
        linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
    )

    storage_manager = AsyncStorageManager()
    await storage_manager.async_init()
    cache_manager = CacheManager()

    try:
        async with AsyncKafkaProducer(producer_config) as producer:
            logger.info("rt_app.producer_connected")

            consumer = RealTimeIndicatorConsumer(
                config=consumer_config,
                producer=producer,
                storage_manager=storage_manager,
                cache_manager=cache_manager,
            )

            await consumer.initialize()
            logger.info("rt_app.consumer_initialized")

            async with consumer:
                logger.info("rt_app.consumer_connected")
                await consumer.start()

    except KeyboardInterrupt:
        logger.info("rt_app.interrupted")
    except Exception as exc:
        logger.exception("rt_app.fatal_error", error=str(exc))
        raise
    finally:
        await storage_manager.close()
        await cache_manager.close()
        await close_db()
        logger.info("rt_app.shutdown_complete")


async def run_batch_consumer() -> None:
    """
    Запускает Batch consumer для обработки индикаторов.

    Инициализирует все необходимые зависимости (БД, Kafka producer/consumer,
    managers) и запускает Batch consumer для массовой обработки индикаторов.

    Raises:
        Exception: При критической ошибке инициализации или работы consumer.
    """
    logger.info("batch_app.starting")

    db_settings = DatabaseSettings()
    init_db(db_settings)
    logger.info("batch_app.db_initialized")

    consumer_config = ConsumerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_BATCH_CALCULATION_TOPIC,
        group_id=settings.KAFKA_BATCH_CALC_GROUP,
        max_poll_records=settings.KAFKA_BATCH_CONSUMER_MAX_POLL_RECORDS,
        max_concurrent_messages=settings.KAFKA_BATCH_CONSUMER_MAX_CONCURRENT,
        max_retries=settings.KAFKA_BATCH_CONSUMER_MAX_RETRIES,
        use_dlq=settings.KAFKA_BATCH_CONSUMER_USE_DLQ,
        auto_offset_reset="earliest",
        slow_threshold_ms=10000.0,
    )

    producer_config = ProducerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        acks=settings.KAFKA_PRODUCER_ACKS,
        compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
        batch_size=settings.KAFKA_PRODUCER_BATCH_SIZE,
        linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
    )

    storage_manager = AsyncStorageManager()
    lock_manager = DistributedLockManager(default_timeout=300)

    # Создаем пул ClickHouse клиентов с graceful shutdown
    clickhouse_pool = ClickHouseClientPool(
        size=settings.KAFKA_BATCH_CONSUMER_MAX_CONCURRENT,
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB,
        settings={
            "max_partitions_per_insert_block": settings.MAX_PARTITIONS_PER_INSERT
        },
    )
    await clickhouse_pool.initialize()

    try:
        async with AsyncKafkaProducer(producer_config) as producer:
            logger.info("batch_app.producer_connected")

            consumer = BatchIndicatorConsumer(
                config=consumer_config,
                producer=producer,
                storage_manager=storage_manager,
                lock_manager=lock_manager,
                ch_client_pool=clickhouse_pool.pool,
            )

            logger.info("batch_app.consumer_initialized")

            async with consumer:
                logger.info("batch_app.consumer_connected")
                await consumer.start()

    except KeyboardInterrupt:
        logger.info("batch_app.interrupted")
    except Exception as exc:
        logger.exception("batch_app.fatal_error", error=str(exc))
        raise
    finally:
        await clickhouse_pool.close()
        await storage_manager.close()
        await lock_manager.close()
        await close_db()
        logger.info("batch_app.shutdown_complete")


@click.group()
def cli():
    """CLI для управления сервисом калькуляции индикаторов."""
    pass


@cli.command()
def consume_rt():
    """Запуск Real-Time калькулятора индикаторов."""
    click.echo("Запуск Real-Time калькулятора...")
    try:
        asyncio.run(run_rt_consumer())
    except Exception as exc:
        raise click.ClickException(f"Fatal error: {exc}") from exc


@cli.command()
def consume_batch():
    """Запуск Batch калькулятора индикаторов."""
    click.echo("Запуск Batch калькулятора...")
    try:
        asyncio.run(run_batch_consumer())
    except Exception as exc:
        raise click.ClickException(f"Fatal error: {exc}") from exc


if __name__ == "__main__":
    cli()
