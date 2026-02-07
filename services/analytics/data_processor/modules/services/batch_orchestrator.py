"""
Batch Orchestrator для координации batch-обработки индикаторов.

Управляет всем процессом: создание pipeline, делегирование загрузки и обработки.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from clickhouse_connect.driver import Client
from tradeforge_logger import get_logger

from calc.factory import create_indicator_pipeline_from_defs
from core.protocols import ILockManager, IStorageManager
from core.timezone_utils import ensure_moscow_tz

from .data_loader import DataLoader
from .indicator_processor import IndicatorProcessor

logger = get_logger(__name__)


class BatchOrchestrator:
    """
    Координирует весь процесс batch-обработки индикаторов.

    Последовательность шагов:
    1. Создание pipeline индикаторов из определений
    2. Делегирование загрузки данных в DataLoader
    3. Делегирование расчета индикаторов в IndicatorProcessor

    Attributes:
        data_loader: Загрузчик данных.
        indicator_processor: Процессор индикаторов.
    """

    def __init__(
        self,
        storage_manager: IStorageManager,
        lock_manager: ILockManager,
    ):
        """
        Инициализирует оркестратор.

        Args:
            storage_manager: Менеджер хранилища.
            lock_manager: Менеджер блокировок.
        """
        self.data_loader = DataLoader(storage_manager)
        self.indicator_processor = IndicatorProcessor(
            storage_manager, lock_manager
        )

    async def process_task(
        self,
        task: dict[str, Any],
        client: Client,
        correlation_id: str | None = None,
    ) -> None:
        """
        Выполняет полный цикл обработки batch-задачи.

        Создает один ClickHouse клиент для всей задачи через context manager,
        обеспечивая эффективное использование ресурсов при обработке
        множественных индикаторов.

        Args:
            task: Словарь с параметрами задачи:
                - job_id: ID задачи
                - ticker: Тикер инструмента
                - timeframe: Таймфрейм
                - start_date: Дата начала (ISO format)
                - end_date: Дата окончания (ISO format)
                - indicators: Список определений индикаторов
            client: Клиент Clickhouse.
            correlation_id: Correlation ID для трейсинга.

        Raises:
            ValueError: При отсутствии данных или невалидных параметрах.
            RetryableError: При timeout получения блокировки.
        """
        job_id = task["job_id"]
        indicator_defs = task["indicators"]
        ticker = task["ticker"]
        timeframe = task["timeframe"]
        start_date = ensure_moscow_tz(
            datetime.fromisoformat(task["start_date"])
        )
        end_date = ensure_moscow_tz(datetime.fromisoformat(task["end_date"]))

        logger.info(
            "batch_orchestrator.task_started",
            job_id=job_id,
            ticker=ticker,
            timeframe=timeframe,
            indicators_count=len(indicator_defs),
            correlation_id=correlation_id,
        )

        pipeline = create_indicator_pipeline_from_defs(indicator_defs)
        if not pipeline.indicators:
            raise ValueError(f"No valid indicators defined for job {job_id}")

        max_lookback = max(ind.lookback for ind in pipeline.indicators)

        logger.info(
            "batch_orchestrator.pipeline_created",
            job_id=job_id,
            indicators_count=len(pipeline.indicators),
            max_lookback=max_lookback,
            correlation_id=correlation_id,
        )

        df = await self.data_loader.load_candles_with_lookback(
            client=client,
            ticker=ticker,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            lookback_candles=max_lookback,
            job_id=job_id,
            correlation_id=correlation_id,
        )

        # Валидация: проверяем что DataFrame не пустой и содержит валидные данные
        if df.empty:
            raise ValueError(
                f"Empty DataFrame after loading candles for {ticker} {timeframe} "
                f"from {start_date.date()} to {end_date.date()}. No data available."
            )

        # Проверка наличия критичных колонок
        required_columns = ["begin", "open", "high", "low", "close", "volume"]
        missing_columns = [
            col for col in required_columns if col not in df.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Missing required columns in DataFrame for {ticker} {timeframe}: "
                f"{missing_columns}"
            )

        # Проверка что есть хотя бы одна валидная свеча после lookback
        valid_candles_count = len(df[df["begin"] >= start_date])
        if valid_candles_count == 0:
            raise ValueError(
                f"No valid candles after start_date {start_date.date()} "
                f"for {ticker} {timeframe}. Only lookback data present."
            )

        logger.info(
            "batch_orchestrator.dataframe_validated",
            job_id=job_id,
            total_rows=len(df),
            valid_candles=valid_candles_count,
            correlation_id=correlation_id,
        )

        processed_count = await self.indicator_processor.process_indicators(
            client=client,
            pipeline=pipeline,
            df=df,
            ticker=ticker,
            timeframe=timeframe,
            original_start_date=start_date,
            job_id=job_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "batch_orchestrator.task_completed",
            job_id=job_id,
            processed_indicators=processed_count,
            correlation_id=correlation_id,
        )
