"""
Scheduler для формирования задач на сбор данных.

Вызывается из cron через CLI, формирует задачи и отправляет в Kafka.
"""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db.session import get_db_manager
from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_logger import get_logger

from clients import AsyncMoexApiClient
from models import CollectionTaskMessage, MoexTicker
from repositories import PostgresRepository, RedisStateManager

logger = get_logger(__name__)


class Scheduler:
    """
    Scheduler для планирования задач сбора данных.

    Workflow:
    1. Синхронизирует тикеры с MOEX (опционально)
    2. Получает активные конфигурации сбора из БД
    3. Получает список активных тикеров
    4. Формирует задачи для каждого тикера
    5. Отправляет задачи батчем в Kafka
    """

    def __init__(
        self,
        moex_client: AsyncMoexApiClient,
        producer: AsyncKafkaProducer,
        state_manager: RedisStateManager,
        tasks_topic: str,
        market_code: str = "moex_stock",
    ):
        """
        Инициализация scheduler.

        Args:
            moex_client: Асинхронный клиент MOEX API
            producer: Kafka producer
            state_manager: Redis state manager
            tasks_topic: Топик для отправки задач
            market_code: Код рынка
        """
        self.moex_client = moex_client
        self.producer = producer
        self.state_manager = state_manager
        self.tasks_topic = tasks_topic
        self.market_code = market_code

    async def sync_tickers(self, db_session: AsyncSession) -> list[str]:
        """
        Синхронизирует справочник тикеров с MOEX API.

        Args:
            db_session: Асинхронная сессия БД

        Returns:
            Список символов тикеров
        """
        logger.info("scheduler.syncing_tickers")

        postgres_repo = PostgresRepository(db_session)

        # Получаем ID рынка
        market_id = await postgres_repo.get_market_id(self.market_code)

        if not market_id:
            logger.error(
                "scheduler.market_not_found",
                market_code=self.market_code,
            )
            return []

        # Получаем данные с MOEX
        securities_data = await self.moex_client.get_all_securities()

        if not securities_data:
            logger.warning("scheduler.no_moex_securities")
            return []

        # Подготавливаем для БД
        tickers_for_db = []
        ticker_symbols = []

        for sec_data in securities_data:
            try:
                model = MoexTicker.model_validate(sec_data)
                ticker_dict = model.model_dump()
                ticker_dict["market_id"] = market_id

                tickers_for_db.append(ticker_dict)
                ticker_symbols.append(model.symbol)
            except ValidationError as e:
                logger.debug(
                    "scheduler.ticker_validation_failed",
                    ticker=sec_data.get("SECID"),
                    error=str(e),
                )

        # Сохраняем в БД
        try:
            await postgres_repo.upsert_tickers(tickers_for_db)
        except Exception as e:
            logger.error(
                "scheduler.upsert_tickers_failed",
                error=str(e),
                exc_info=True,
            )
            # Не прерываем - задачи важнее

        logger.info(
            "scheduler.tickers_synced",
            count=len(ticker_symbols),
        )

        return ticker_symbols

    async def schedule_collection(
        self,
        collection_type: str,
        timeframes: list[str] | None = None,
        sync_tickers: bool = True,
        sync_redis: bool = False,
    ) -> int:
        """
        Планирует сбор данных для типа.

        Args:
            collection_type: Тип сбора ('candles', 'orderbook' и т.д.)
            timeframes: Список таймфреймов для сбора (для candles). Если None - ошибка
            sync_tickers: Синхронизировать ли тикеры с MOEX
            sync_redis: Синхронизировать ли Redis с ClickHouse

        Returns:
            Количество отправленных задач

        Raises:
            ValueError: Если timeframes не указан для collection_type='candles'
        """
        logger.info(
            "scheduler.scheduling",
            collection_type=collection_type,
            timeframes=timeframes,
        )

        # Валидация параметров для candles
        if collection_type == "candles":
            if not timeframes:
                raise ValueError(
                    "timeframes parameter is required for candles collection"
                )

        # Синхронизация Redis с ClickHouse (опционально)
        if sync_redis:
            try:
                updated = await self.state_manager.sync_with_clickhouse()
                logger.info("scheduler.redis_synced", updated=updated)
            except Exception as e:
                logger.warning(
                    "scheduler.redis_sync_failed",
                    error=str(e),
                )

        # Получаем тикеры
        db_manager = get_db_manager()
        async with db_manager.session() as session:
            # Синхронизация тикеров (опционально)
            if sync_tickers:
                await self.sync_tickers(session)

            # Получаем активные тикеры для текущего рынка
            postgres_repo = PostgresRepository(session)
            tickers = await postgres_repo.get_active_tickers(self.market_code)

            if not tickers:
                logger.warning(
                    "scheduler.no_active_tickers",
                    market_code=self.market_code,
                )
                return 0

            logger.info(
                "scheduler.tickers_loaded",
                market_code=self.market_code,
                tickers_count=len(tickers),
            )

        # Формируем задачи на основе переданных параметров
        tasks = []

        if collection_type == "candles":
            # Для каждого тикера и каждого таймфрейма создаем задачу
            for ticker in tickers:
                for timeframe in timeframes:
                    task = CollectionTaskMessage(
                        task_type="collect_candles",
                        ticker=ticker,
                        params={"timeframe": timeframe},
                    )
                    tasks.append(task)
        else:
            # Для будущих типов сборов (orderbook, trades и т.д.)
            logger.error(
                "scheduler.unsupported_collection_type",
                collection_type=collection_type,
            )
            raise ValueError(f"Unsupported collection_type: {collection_type}")

        if not tasks:
            logger.warning("scheduler.no_tasks_generated")
            return 0

        # Отправляем батчем в Kafka
        try:
            await self.producer.send_batch(
                topic=self.tasks_topic,
                messages=tasks,
                key_fn=lambda msg: f"{msg.ticker}:{msg.task_type}",
            )

            logger.info(
                "scheduler.tasks_published",
                collection_type=collection_type,
                timeframes=timeframes,
                count=len(tasks),
            )

            return len(tasks)

        except Exception as e:
            logger.error(
                "scheduler.publish_failed",
                collection_type=collection_type,
                error=str(e),
                exc_info=True,
            )
            raise
