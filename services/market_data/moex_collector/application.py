"""
MOEX Collector Application - точка входа сервиса.

CLI интерфейс для запуска scheduler и consumer режимов.
"""

from __future__ import annotations

import asyncio

import click
from tradeforge_db import close_db, init_db
from tradeforge_kafka import AsyncKafkaProducer, ConsumerConfig
from tradeforge_logger import configure_logging, get_logger

from clients import create_infrastructure_clients, create_kafka_producer_config
from consumers import CollectionConsumer
from handlers import create_candles_handler
from modules import CandlesCollectorService, TaskRegistry, Scheduler
from settings import settings

logger = get_logger(__name__)


@click.group()
def cli():
    """MOEX Collector CLI."""
    pass


@cli.command()
@click.option(
    "--collection-type",
    type=click.Choice(["candles"], case_sensitive=False),
    required=True,
    help="Тип собираемых данных",
)
@click.option(
    "--timeframes",
    "-t",
    multiple=True,
    help="Таймфреймы для сбора (например, 1h, 1d). Можно указать несколько раз.",
)
@click.option(
    "--market-code",
    "-m",
    default="moex_stock",
    help="Код рынка (moex_stock, moex_futures, moex_currency, moex_metals)",
)
@click.option(
    "--sync-tickers/--no-sync-tickers",
    default=True,
    help="Синхронизировать тикеры с MOEX",
)
@click.option(
    "--sync-redis/--no-sync-redis",
    default=False,
    help="Синхронизировать состояние Redis с ClickHouse",
)
def schedule(
    collection_type: str,
    timeframes: tuple[str, ...],
    market_code: str,
    sync_tickers: bool,
    sync_redis: bool,
):
    """
    Run scheduler to create collection tasks.

    Called from cron. Creates tasks and sends them to Kafka.

    Examples:
        python application.py schedule --collection-type candles -t 1h
        python application.py schedule --collection-type candles -t 1h -t 1d
        python application.py schedule --collection-type candles -t 1h -m moex_stock
        python application.py schedule --collection-type candles -t 1h --sync-redis
    """
    timeframes_list = list(timeframes) if timeframes else []

    click.echo(f"Scheduling collection: {collection_type}")
    click.echo(f"Market: {market_code}")
    click.echo(
        f"Timeframes: {', '.join(timeframes_list) if timeframes_list else 'None'}"
    )

    asyncio.run(
        _run_scheduler(
            collection_type,
            timeframes_list,
            market_code,
            sync_tickers,
            sync_redis,
        )
    )


@cli.command()
def consume():
    """
    Запуск consumer для сбора данных.

    Слушает топик с задачами и выполняет сбор через registered handlers.

    Examples:
        python application.py consume
    """
    click.echo("Starting collection consumer...")

    asyncio.run(_run_consumer())


async def _run_scheduler(
    collection_type: str,
    timeframes: list[str],
    market_code: str,
    sync_tickers: bool,
    sync_redis: bool,
):
    """
    Запускает scheduler для формирования задач.

    Args:
        collection_type: Тип сбора ('candles')
        timeframes: Список таймфреймов для сбора
        market_code: Код рынка ('moex_stock', 'moex_futures', и т.д.)
        sync_tickers: Синхронизировать ли тикеры
        sync_redis: Синхронизировать ли Redis
    """
    # Инициализация логирования
    configure_logging(
        service_name="moex-collector-scheduler",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
        enable_json=True,
        enable_console_colors=False,
    )

    logger.info(
        "scheduler.starting",
        collection_type=collection_type,
        market_code=market_code,
        timeframes=timeframes,
        sync_tickers=sync_tickers,
        sync_redis=sync_redis,
    )

    # Инициализация PostgreSQL
    init_db()
    logger.info("scheduler.db_initialized")

    # Инициализация инфраструктурных клиентов
    infra = await create_infrastructure_clients(settings)
    producer_config = create_kafka_producer_config(settings)

    try:
        async with AsyncKafkaProducer(producer_config) as producer:
            logger.info("scheduler.producer_connected")

            # Create scheduler
            scheduler = Scheduler(
                moex_client=infra.moex_client,
                producer=producer,
                state_manager=infra.state_manager,
                tasks_topic=settings.KAFKA_COLLECTOR_TASKS_TOPIC,
                market_code=market_code,
            )

            # Schedule collection
            tasks_count = await scheduler.schedule_collection(
                collection_type=collection_type,
                timeframes=timeframes,
                sync_tickers=sync_tickers,
                sync_redis=sync_redis,
            )

            logger.info(
                "scheduler.completed",
                tasks_sent=tasks_count,
                timeframes=timeframes,
            )

            click.echo(f"Tasks sent: {tasks_count}")

    except KeyboardInterrupt:
        logger.info("scheduler.interrupted")
    except Exception as exc:
        logger.exception("scheduler.fatal_error", error=str(exc))
        raise click.ClickException(f"Scheduler failed: {exc}") from exc
    finally:
        # Graceful shutdown всех клиентов
        await close_db()
        await infra.moex_client.close()
        await infra.redis_client.aclose()
        await infra.clickhouse_pool.close()
        logger.info("scheduler.shutdown_complete")


async def _run_consumer():
    """Запускает collection consumer."""
    # Инициализация логирования
    configure_logging(
        service_name="moex-collector-consumer",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
        enable_json=True,
        enable_console_colors=False,
    )

    logger.info("consumer.starting")

    # Инициализация PostgreSQL
    init_db()
    logger.info("consumer.db_initialized")

    # Инициализация инфраструктурных клиентов
    infra = await create_infrastructure_clients(settings)
    producer_config = create_kafka_producer_config(settings)

    consumer_config = ConsumerConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_COLLECTOR_TASKS_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP,
        max_concurrent_messages=settings.KAFKA_CONSUMER_MAX_CONCURRENT,
        max_retries=settings.KAFKA_CONSUMER_MAX_RETRIES,
        use_dlq=settings.KAFKA_CONSUMER_USE_DLQ,
        auto_offset_reset="earliest",
    )

    try:
        async with AsyncKafkaProducer(producer_config) as producer:
            logger.info("consumer.producer_connected")

            # Create candles service
            candles_service = CandlesCollectorService(
                moex_client=infra.moex_client,
                state_manager=infra.state_manager,
                clickhouse_repo=infra.clickhouse_repo,
                kafka_producer=producer if settings.PUBLISH_TO_KAFKA else None,
                publish_to_kafka=settings.PUBLISH_TO_KAFKA,
                candles_topic=settings.KAFKA_CANDLES_TOPIC,
            )

            # Create task registry and register handlers
            registry = TaskRegistry()
            candles_handler = create_candles_handler(candles_service)
            registry.register("collect_candles", candles_handler)

            logger.info(
                "consumer.registry_configured",
                registered_types=registry.get_registered_types(),
            )

            # Create consumer
            consumer = CollectionConsumer(
                config=consumer_config,
                registry=registry,
                producer=producer,
                tasks_topic=settings.KAFKA_COLLECTOR_TASKS_TOPIC,
            )

            logger.info("consumer.initialized")

            # Start consumer
            async with consumer:
                logger.info("consumer.connected")
                await consumer.start()

    except KeyboardInterrupt:
        logger.info("consumer.interrupted")
    except Exception as exc:
        logger.exception("consumer.fatal_error", error=str(exc))
        raise click.ClickException(f"Consumer failed: {exc}") from exc
    finally:
        # Graceful shutdown всех клиентов
        await close_db()
        await infra.moex_client.close()
        await infra.redis_client.aclose()
        await infra.clickhouse_pool.close()
        logger.info("consumer.shutdown_complete")


if __name__ == "__main__":
    cli()
