"""
Data Loader для загрузки и подготовки данных для batch-обработки.

Отвечает за загрузку базовых свечей из ClickHouse с учетом lookback периода
и преобразование данных в DataFrame.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from clickhouse_connect.driver import Client
from tradeforge_logger import get_logger

from core.protocols import IStorageManager
from core.timezone_utils import from_clickhouse

logger = get_logger(__name__)


class DataLoader:
    """
    Загружает и подготавливает данные для batch-обработки индикаторов.

    Ответственность:
    - Расчет даты начала с учетом lookback периода
    - Загрузка базовых свечей из ClickHouse
    - Преобразование данных в pandas DataFrame

    Attributes:
        storage: Менеджер хранилища данных.
    """

    def __init__(self, storage_manager: IStorageManager):
        """
        Инициализирует data loader.

        Args:
            storage_manager: Менеджер хранилища данных.
        """
        self.storage = storage_manager

    async def load_candles_with_lookback(
        self,
        client: Client,
        ticker: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        lookback_candles: int,
        job_id: str,
        correlation_id: str | None = None,
    ) -> pd.DataFrame:
        """
        Загружает свечи с учетом lookback периода и возвращает DataFrame.

        Сначала вычисляет расширенную дату начала (start_date - lookback),
        затем загружает все свечи за этот период и преобразует в DataFrame
        с правильным timezone.

        Args:
            client: Клиент Clickhouse.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Дата начала периода (без lookback).
            end_date: Дата окончания периода.
            lookback_candles: Количество свечей для lookback.
            job_id: ID задачи для логирования.
            correlation_id: Correlation ID для трейсинга.

        Returns:
            DataFrame с базовыми свечами (OHLCV) и timezone-aware датами.

        Raises:
            ValueError: Если не найдено свечей за период.

        Example:
            >>> loader = DataLoader(storage_manager)
            >>> df = await loader.load_candles_with_lookback(
            ...     client=client,
            ...     ticker="SBER",
            ...     timeframe="1h",
            ...     start_date=datetime(2024, 1, 1),
            ...     end_date=datetime(2024, 12, 31),
            ...     lookback_candles=50,
            ...     job_id="job-123"
            ... )
            >>> print(len(df))
            8760  # ~365 дней * 24 часа
        """
        logger.info(
            "data_loader.loading_candles",
            job_id=job_id,
            ticker=ticker,
            timeframe=timeframe,
            lookback_candles=lookback_candles,
            correlation_id=correlation_id,
        )

        # Шаг 1: Рассчитать дату начала с учетом lookback
        start_with_lookback = await self.storage.get_start_date_with_lookback(
            client=client,
            ticker=ticker,
            timeframe=timeframe,
            original_start_date=start_date,
            lookback_candles=lookback_candles,
        )

        logger.debug(
            "data_loader.lookback_calculated",
            job_id=job_id,
            original_start=start_date.date().isoformat(),
            extended_start=start_with_lookback.date().isoformat(),
            correlation_id=correlation_id,
        )

        # Шаг 2: Загрузить базовые свечи
        base_candles = await self.storage.get_base_candles_for_period(
            client, ticker, timeframe, start_with_lookback, end_date
        )

        if not base_candles:
            raise ValueError(
                f"No candles found for {ticker} {timeframe} "
                f"from {start_with_lookback.date()} to {end_date.date()}"
            )

        logger.info(
            "data_loader.candles_loaded",
            job_id=job_id,
            candles_count=len(base_candles),
            correlation_id=correlation_id,
        )

        # Шаг 3: Преобразовать в DataFrame с правильным timezone
        df = pd.DataFrame(base_candles)
        df["begin"] = pd.to_datetime(df["begin"]).apply(from_clickhouse)

        logger.debug(
            "data_loader.dataframe_prepared",
            job_id=job_id,
            rows=len(df),
            columns=len(df.columns),
            correlation_id=correlation_id,
        )

        return df
