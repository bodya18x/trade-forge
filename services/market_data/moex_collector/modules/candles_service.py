"""
Сервис для сбора свечей с MOEX.

Бизнес-логика сбора, валидации и сохранения свечей.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError
from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_logger import get_logger

from clients import AsyncMoexApiClient
from models import MoexCandle, get_timeframe_interval
from repositories import ClickHouseRepository, RedisStateManager

logger = get_logger(__name__)


class CandlesCollectorService:
    """
    Сервис сбора свечей с MOEX.

    Координирует работу всех компонентов для сбора свечей:
    - Получает последнюю дату из Redis/ClickHouse
    - Запрашивает свечи у MOEX API
    - Валидирует и фильтрует новые свечи
    - Сохраняет в ClickHouse
    - Публикует в Kafka (опционально)
    - Обновляет состояние в Redis
    """

    # Стандартная дата начала сбора свеч
    DEFAULT_CANDLE_START_DATE = "1812-08-26 00:00:00"

    # Размер пачки свечей получаемых по АПИ
    MOEX_API_BATCH_LIMIT = 500

    def __init__(
        self,
        moex_client: AsyncMoexApiClient,
        state_manager: RedisStateManager,
        clickhouse_repo: ClickHouseRepository,
        kafka_producer: AsyncKafkaProducer | None,
        publish_to_kafka: bool,
        candles_topic: str,
    ):
        """
        Инициализация сервиса.

        Args:
            moex_client: Async клиент MOEX API
            state_manager: Redis state manager
            clickhouse_repo: ClickHouse репозиторий
            kafka_producer: Kafka producer (опционально)
            publish_to_kafka: Публиковать ли в Kafka
            candles_topic: Топик для публикации
        """
        self.moex_client = moex_client
        self.state_manager = state_manager
        self.clickhouse_repo = clickhouse_repo
        self.kafka_producer = kafka_producer
        self.publish_to_kafka = publish_to_kafka
        self.candles_topic = candles_topic

    async def collect_candles(self, ticker: str, timeframe: str) -> int:
        """
        Собирает свечи для тикера и таймфрейма.

        Workflow:
        1. Получает дату последней свечи из Redis (fallback на ClickHouse)
        2. Запрашивает свечи у MOEX API
        3. Фильтрует новые свечи
        4. Валидирует через Pydantic
        5. Сохраняет в ClickHouse
        6. Публикует в Kafka (если publish_to_kafka=True)
        7. Обновляет состояние в Redis

        Args:
            ticker: Алиас тикера (например, "SBER")
            timeframe: Таймфрейм ("1h", "1d" и т.д.)

        Returns:
            Количество полученных свечей (до фильтрации).
            Возвращает 0 если новых свечей нет.

        Raises:
            KeyError: Если таймфрейм не поддерживается
            Exception: При критических ошибках
        """
        try:
            # 1. Получаем последнюю дату
            last_date = await self.state_manager.get_last_candle_date(
                ticker, timeframe
            )

            if last_date is None:
                last_date_str = self.DEFAULT_CANDLE_START_DATE
                logger.info(
                    "candles_service.no_previous_date",
                    ticker=ticker,
                    timeframe=timeframe,
                    using_default=self.DEFAULT_CANDLE_START_DATE,
                )
            else:
                last_date_str = last_date.strftime("%Y-%m-%d %H:%M:%S")

            # 2. Получаем interval для MOEX API
            try:
                interval = get_timeframe_interval(timeframe)
            except KeyError as e:
                logger.error(
                    "candles_service.invalid_timeframe",
                    ticker=ticker,
                    timeframe=timeframe,
                    error=str(e),
                )
                raise

            # 3. Запрашиваем свечи у MOEX
            candles_data = await self.moex_client.get_candles(
                ticker=ticker,
                interval=interval,
                from_date=last_date_str,
            )

            if not candles_data:
                logger.debug(
                    "candles_service.no_moex_data",
                    ticker=ticker,
                    timeframe=timeframe,
                )
                return 0

            total_candles = len(candles_data)
            logger.info(
                "candles_service.moex_data_received",
                ticker=ticker,
                timeframe=timeframe,
                count=total_candles,
            )

            # 4. Фильтруем новые свечи
            new_candles = []
            for candle_dict in candles_data:
                begin_str = candle_dict.get("begin")
                if not begin_str:
                    continue

                try:
                    begin_dt = datetime.strptime(
                        begin_str, "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError as ve:
                    logger.warning(
                        "candles_service.invalid_date",
                        ticker=ticker,
                        date=begin_str,
                        error=str(ve),
                    )
                    continue

                # Фильтруем только новые
                if last_date is None or begin_dt > last_date:
                    new_candles.append(candle_dict)

            if not new_candles:
                logger.info(
                    "candles_service.no_new_candles",
                    ticker=ticker,
                    timeframe=timeframe,
                )
                return 0

            logger.info(
                "candles_service.new_candles_found",
                ticker=ticker,
                timeframe=timeframe,
                count=len(new_candles),
            )

            # 5. Валидация через Pydantic
            validated_candles = []
            for candle_dict in new_candles:
                try:
                    # Добавляем метаданные
                    candle_dict["ticker"] = ticker
                    candle_dict["timeframe"] = timeframe
                    candle_dict.pop("value", None)

                    # Валидация
                    candle = MoexCandle(**candle_dict)
                    validated_candles.append(candle.model_dump(mode="json"))

                except ValidationError as ve:
                    logger.warning(
                        "candles_service.validation_failed",
                        ticker=ticker,
                        candle=candle_dict,
                        error=str(ve),
                    )
                    continue

            if not validated_candles:
                logger.warning(
                    "candles_service.no_valid_candles",
                    ticker=ticker,
                    timeframe=timeframe,
                )
                return total_candles

            # 6. Сохраняем в ClickHouse
            await self.clickhouse_repo.save_candles_batch(validated_candles)

            # 7. Публикуем в Kafka (опционально)
            if self.publish_to_kafka and self.kafka_producer:
                kafka_key = f"{ticker}:{timeframe}"

                await self.kafka_producer.send_batch(
                    topic=self.candles_topic,
                    messages=validated_candles,
                    key_fn=lambda _: kafka_key,
                )

                logger.info(
                    "candles_service.published_to_kafka",
                    ticker=ticker,
                    timeframe=timeframe,
                    count=len(validated_candles),
                )
            else:
                logger.debug(
                    "candles_service.kafka_publish_skipped",
                    ticker=ticker,
                    timeframe=timeframe,
                )

            # 8. Обновляем состояние в Redis
            last_candle = new_candles[-1]
            last_begin = datetime.strptime(
                last_candle["begin"], "%Y-%m-%d %H:%M:%S"
            )

            await self.state_manager.update_last_candle_date(
                ticker, timeframe, last_begin
            )

            # 9. Проверяем достигнут ли лимит
            # Если получено максимальное количество свечей - возможно есть еще
            if total_candles >= self.MOEX_API_BATCH_LIMIT:
                logger.info(
                    "candles_service.limit_reached",
                    ticker=ticker,
                    timeframe=timeframe,
                    count=total_candles,
                )
                return total_candles

            # Если меньше лимита - все собрали
            logger.info(
                "candles_service.collection_complete",
                ticker=ticker,
                timeframe=timeframe,
                total=total_candles,
                new=len(validated_candles),
            )

            return 0  # Сигнал что сбор завершен

        except KeyError:
            # Пробрасываем дальше для FatalError
            raise

        except Exception as e:
            logger.error(
                "candles_service.collection_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
                exc_info=True,
            )
            raise
