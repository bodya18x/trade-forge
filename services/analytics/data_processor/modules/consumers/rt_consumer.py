"""
Real-Time индикаторный consumer.

Обрабатывает сырые свечи в реальном времени, рассчитывает hot-индикаторы,
сохраняет в ClickHouse и публикует "жирные" свечи.
"""

from __future__ import annotations

import pandas as pd
from tradeforge_kafka import (
    AsyncKafkaConsumer,
    AsyncKafkaProducer,
    KafkaMessage,
)
from tradeforge_kafka.config import ConsumerConfig
from tradeforge_kafka.consumer.decorators import log_execution_time, timeout
from tradeforge_kafka.exceptions import RetryableError
from tradeforge_logger import get_logger, set_correlation_id

from calc.factory import create_indicator_pipeline_from_defs
from core.constants import DEFAULT_CONTEXT_CANDLES_SIZE
from core.protocols import ICacheManager, IStorageManager
from core.timezone_utils import ensure_moscow_tz
from models.kafka_messages import RawCandleMessage
from settings import settings

logger = get_logger(__name__)


class RealTimeIndicatorConsumer(AsyncKafkaConsumer[RawCandleMessage]):
    """
    Real-Time consumer для расчета hot-индикаторов.

    Архитектура:
    1. Получает сырую свечу из Kafka
    2. Загружает контекст из Redis (с fallback на ClickHouse при downtime)
    3. Рассчитывает все hot-индикаторы
    4. Сохраняет в ClickHouse
    5. Публикует "жирную" свечу

    Resilience:
    - Redis недоступен → автоматический fallback на ClickHouse (+50-100ms latency)
    - ClickHouse недоступен → RetryableError, Kafka retry
    - Kafka producer недоступен → RetryableError, Kafka retry
    - Cache update failed → Warning, продолжаем работу (не критично)

    Attributes:
        storage: Менеджер хранилища данных.
        cache: Менеджер кэша.
        producer: Producer для отправки результатов.
        hot_indicator_defs: Определения hot-индикаторов.
        indicator_pipeline: Пайплайн индикаторов.
    """

    def __init__(
        self,
        config: ConsumerConfig,
        producer: AsyncKafkaProducer,
        storage_manager: IStorageManager,
        cache_manager: ICacheManager,
    ):
        """
        Инициализирует RT consumer.

        Args:
            config: Конфигурация consumer.
            producer: Producer для отправки результатов.
            storage_manager: Менеджер хранилища.
            cache_manager: Менеджер кэша.
        """
        super().__init__(config=config, message_schema=RawCandleMessage)

        self.storage = storage_manager
        self.cache = cache_manager
        self.producer = producer

        self.hot_indicator_defs = []
        self.indicator_pipeline = None

    async def initialize(self) -> None:
        """
        Асинхронная инициализация consumer.

        Загружает определения hot-индикаторов из PostgreSQL
        и создает indicator pipeline.
        """
        logger.info("rt_consumer.initializing")

        try:
            self.hot_indicator_defs = (
                await self.storage.get_hot_indicators_definitions()
            )

            self.indicator_pipeline = create_indicator_pipeline_from_defs(
                self.hot_indicator_defs
            )

            logger.info(
                "rt_consumer.initialized",
                indicators_count=len(self.hot_indicator_defs),
            )

        except Exception as e:
            logger.exception(
                "rt_consumer.initialization_failed",
                error=str(e),
            )
            raise

    @timeout(30.0)
    @log_execution_time(threshold_ms=5000)
    async def on_message(
        self, message: KafkaMessage[RawCandleMessage]
    ) -> None:
        """
        Обрабатывает сырую свечу с расчетом индикаторов.

        Args:
            message: Kafka сообщение с валидированной свечой.

        Raises:
            RetryableError: При временной ошибке (Redis/ClickHouse недоступны).
        """
        set_correlation_id(message.correlation_id)

        candle = message.value
        ticker = candle.ticker
        timeframe = candle.timeframe
        begin = ensure_moscow_tz(candle.begin)

        logger.debug(
            "rt_consumer.processing",
            ticker=ticker,
            timeframe=timeframe,
            begin=begin.isoformat(),
        )

        # Загрузка контекста с fallback на ClickHouse при Redis downtime
        try:
            context_candles = await self.cache.get_context_candles(
                ticker, timeframe
            )
        except Exception as e:
            logger.warning(
                "rt_consumer.redis_unavailable_using_clickhouse_fallback",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )
            # Fallback: загружаем контекст из ClickHouse
            context_candles = (
                await self.storage.get_last_n_candles_for_context(
                    ticker=ticker,
                    timeframe=timeframe,
                    limit=DEFAULT_CONTEXT_CANDLES_SIZE,
                )
            )

        candle_dict = candle.model_dump(mode="json")
        context_candles.append(candle_dict)

        df = pd.DataFrame(context_candles)
        df["begin"] = pd.to_datetime(df["begin"]).apply(ensure_moscow_tz)

        processed_df = self.indicator_pipeline.compute_all(df)

        try:
            await self.storage.save_rt_indicators(
                ticker, timeframe, begin, processed_df, self.indicator_pipeline
            )
        except Exception as e:
            raise RetryableError(f"ClickHouse unavailable: {e}") from e

        try:
            await self.cache.update_context_cache(
                ticker, timeframe, candle_dict
            )
        except Exception as e:
            logger.warning(
                "rt_consumer.cache_update_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )

        processed_candle_dict = {
            k: (None if pd.isna(v) else v)
            for k, v in processed_df.iloc[-1].to_dict().items()
        }

        processed_candle_dict["begin"] = processed_candle_dict[
            "begin"
        ].isoformat()

        try:
            await self.producer.send(
                topic=settings.KAFKA_PROCESSED_CANDLES_RT_TOPIC,
                message=processed_candle_dict,
                key=f"{ticker}:{timeframe}",
                correlation_id=message.correlation_id,
            )
        except Exception as e:
            raise RetryableError(f"Kafka producer unavailable: {e}") from e

        logger.info(
            "rt_consumer.candle_processed",
            ticker=ticker,
            timeframe=timeframe,
        )
