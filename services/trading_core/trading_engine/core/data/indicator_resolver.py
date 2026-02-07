"""
Indicator Resolver - проверка и запрос расчета индикаторов.

Отвечает за:
1. Проверку наличия индикаторов в ClickHouse
2. Отправку запросов на расчет недостающих индикаторов
3. Управление "кругом почета" (круговой обработкой)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from clickhouse_connect.driver.asyncclient import AsyncClient
from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_logger import get_logger

from models.kafka_messages import IndicatorCalculationRequestMessage
from repositories.clickhouse import ClickHouseRepository
from repositories.postgres import IndicatorRepository
from settings import settings

logger = get_logger(__name__)


class IndicatorResolver:
    """
    Проверяет наличие и запрашивает расчет индикаторов.

    "Круг почета": Если индикаторы отсутствуют, отправляет запрос в Kafka
    и прерывает выполнение бэктеста. Data Processor рассчитает индикаторы
    и отправит обратно сообщение, которое запустит бэктест снова.

    Attributes:
        clickhouse: Репозиторий для проверки наличия данных.
        producer: Kafka producer для отправки запросов.
        indicator_repo: Репозиторий для доступа к реестру индикаторов.
    """

    def __init__(
        self,
        clickhouse_repo: ClickHouseRepository,
        producer: AsyncKafkaProducer,
        indicator_repo: IndicatorRepository,
    ):
        """
        Инициализирует IndicatorResolver.

        Args:
            clickhouse_repo: Репозиторий ClickHouse.
            producer: Kafka producer.
            indicator_repo: Репозиторий индикаторов.
        """
        self.clickhouse = clickhouse_repo
        self.producer = producer
        self.indicator_repo = indicator_repo

    async def ensure_indicators_available(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        required_indicators: list[tuple[str, str]],
        job_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Проверяет наличие индикаторов и запрашивает расчет если нужно.

        Если какие-то индикаторы отсутствуют в ClickHouse, отправляет запрос
        на их расчет в Data Processor и возвращает False. После расчета
        Data Processor отправит сообщение обратно, и бэктест запустится снова.

        Args:
            client: Асинхронный клиент ClickHouse.
            ticker: Тикер инструмента (например, "SBER").
            timeframe: Таймфрейм (например, "1h").
            start_date: Начало периода.
            end_date: Конец периода.
            required_indicators: Список пар (base_key, value_key).
            job_id: ID задачи на бэктест.
            correlation_id: ID корреляции для трейсинга.

        Returns:
            True если все данные готовы, False если отправлен запрос на расчет.

        Examples:
            >>> resolver = IndicatorResolver(clickhouse_repo, producer, indicator_repo)
            >>> required = [("rsi_timeperiod_14", "value"), ("ema_timeperiod_50", "value")]
            >>> ready = await resolver.ensure_indicators_available(
            ...     client=ch_client,
            ...     ticker="SBER",
            ...     timeframe="1h",
            ...     start_date=datetime(2024, 1, 1),
            ...     end_date=datetime(2024, 12, 31),
            ...     required_indicators=required,
            ...     job_id=job_uuid
            ... )
            >>> if ready:
            ...     print("All indicators available, proceed with backtest")
            ... else:
            ...     print("Indicators requested, waiting for round trip")
        """
        # Проверяем наличие индикаторов в ClickHouse
        missing = await self.clickhouse.get_missing_indicator_periods(
            client=client,
            ticker=ticker,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            required_indicators=required_indicators,
        )

        # Если всё есть - возвращаем True
        if not missing:
            logger.info(
                "indicator_resolver.all_indicators_available",
                ticker=ticker,
                timeframe=timeframe,
                indicators_count=len(required_indicators),
                correlation_id=correlation_id,
            )
            return True

        # Если чего-то нет - запрашиваем расчет
        logger.info(
            "indicator_resolver.missing_indicators_detected",
            ticker=ticker,
            timeframe=timeframe,
            missing_count=len(missing),
            correlation_id=correlation_id,
        )

        await self._request_calculation(
            job_id=job_id,
            ticker=ticker,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            missing_indicators=missing,
            correlation_id=correlation_id,
        )

        return False  # Ждем "круг почета"

    async def _request_calculation(
        self,
        job_id: uuid.UUID,
        ticker: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        missing_indicators: list[tuple[str, str]],
        correlation_id: str | None = None,
    ) -> None:
        """
        Отправляет запрос на расчет недостающих индикаторов в Data Processor.

        Args:
            job_id: ID задачи на бэктест.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начало периода.
            end_date: Конец периода.
            missing_indicators: Список пар (base_key, value_key) для расчета.
            correlation_id: ID корреляции для трейсинга.
        """
        # Получаем полный реестр индикаторов для формирования запроса
        registry = await self.indicator_repo.get_full_indicator_registry()

        indicators_to_calculate = []
        for base_key, value_key in missing_indicators:
            if base_key in registry:
                indicators_to_calculate.append(
                    {
                        "name": registry[base_key]["name"],
                        "params": registry[base_key]["params"],
                    }
                )

        # Форматируем даты в ISO формат
        start_date_str = (
            start_date.isoformat()
            if hasattr(start_date, "isoformat")
            else str(start_date)
        )
        end_date_str = (
            end_date.isoformat()
            if hasattr(end_date, "isoformat")
            else str(end_date)
        )

        # Создаем сообщение для Kafka
        message_obj = IndicatorCalculationRequestMessage(
            job_id=str(job_id),
            ticker=ticker,
            timeframe=timeframe,
            start_date=start_date_str,
            end_date=end_date_str,
            indicators=indicators_to_calculate,
        )

        # Отправляем в Kafka
        await self.producer.send(
            topic=settings.KAFKA_TOPIC_INDICATOR_CALC_REQUEST,
            message=message_obj,
            correlation_id=correlation_id or str(job_id),
        )

        logger.info(
            "indicator_resolver.calculation_requested",
            job_id=str(job_id),
            indicators_count=len(indicators_to_calculate),
            correlation_id=correlation_id,
        )
