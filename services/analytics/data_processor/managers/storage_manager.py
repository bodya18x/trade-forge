"""
Storage Manager для работы с ClickHouse и PostgreSQL.

Async-first реализация с единой стратегией работы с timezone.
Все datetime работают в московском часовом поясе (Europe/Moscow).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import clickhouse_connect
import pandas as pd
import pyarrow as pa
from clickhouse_connect.driver.asyncclient import AsyncClient
from sqlalchemy import select
from tradeforge_db import UsersIndicators, get_db_manager
from tradeforge_logger import get_logger

from calc.base import IndicatorPipeline
from core.constants import (
    CLICKHOUSE_CANDLES_INDICATORS_TABLE,
    MICROSECONDS_MULTIPLIER,
)
from core.timezone_utils import (
    ensure_moscow_tz,
    from_clickhouse,
    to_clickhouse,
    to_clickhouse_query,
)
from settings import settings

logger = get_logger(__name__)


class AsyncStorageManager:
    """
    Async-first менеджер для взаимодействия с ClickHouse и PostgreSQL.

    Все операции с БД выполняются асинхронно с использованием официального
    AsyncClient из clickhouse-connect (версия 0.7.16+).
    Единая стратегия работы с timezone через core.timezone_utils.

    Attributes:
        _ch_client: Асинхронный ClickHouse клиент для RT операций.
    """

    def __init__(self):
        """Инициализирует storage manager. Требует вызова async_init() после создания."""
        self._ch_client: AsyncClient | None = None
        logger.info("storage_manager.created")

    async def async_init(self) -> None:
        """Асинхронная инициализация ClickHouse AsyncClient."""
        self._ch_client = await clickhouse_connect.get_async_client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DB,
            settings={
                "max_partitions_per_insert_block": settings.MAX_PARTITIONS_PER_INSERT
            },
        )
        logger.info("storage_manager.initialized")

    async def close(self) -> None:
        """Закрывает ClickHouse соединение при graceful shutdown."""
        try:
            if self._ch_client:
                await self._ch_client.close()
            logger.info("storage_manager.closed")
        except Exception as e:
            logger.warning("storage_manager.close_error", error=str(e))

    async def get_hot_indicators_definitions(self) -> list[dict[str, Any]]:
        """
        Загружает определения hot-индикаторов из PostgreSQL.

        Returns:
            Список определений индикаторов с полями name и params.
        """
        logger.info("storage_manager.loading_hot_indicators")

        try:
            db_manager = get_db_manager()

            async with db_manager.session() as session:
                stmt = select(
                    UsersIndicators.name, UsersIndicators.params
                ).where(
                    UsersIndicators.is_hot == True
                )  # noqa: E712

                result = await session.execute(stmt)
                rows = result.all()

                records = [
                    {"name": row.name, "params": row.params} for row in rows
                ]

                logger.info(
                    "storage_manager.hot_indicators_loaded",
                    count=len(records),
                )
                return records

        except Exception as e:
            logger.exception(
                "storage_manager.hot_indicators_load_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def save_rt_indicators(
        self,
        ticker: str,
        timeframe: str,
        begin: datetime,
        processed_df: pd.DataFrame,
        indicator_pipeline: IndicatorPipeline,
    ) -> None:
        """
        Сохраняет RT индикаторы в ClickHouse с асинхронной вставкой.

        Использует async_insert=1 для минимизации задержек в реальном времени.
        ReplacingMergeTree(version) автоматически дедуплицирует записи.

        NOTE: Использует общий self._ch_client, т.к. RT consumer работает
        с max_concurrent_messages=1 (последовательная обработка), поэтому
        нет риска concurrent queries.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            begin: Время начала свечи (timezone-aware).
            processed_df: DataFrame с рассчитанными индикаторами.
            indicator_pipeline: Пайплайн индикаторов.
        """
        if processed_df.empty:
            return

        version = int(time.time() * MICROSECONDS_MULTIPLIER)
        begin_moscow = to_clickhouse(ensure_moscow_tz(begin))

        records_to_insert = []
        last_row = processed_df.iloc[-1]

        for indicator in indicator_pipeline.indicators:
            base_key = indicator.get_base_key()

            for value_key, full_column_name in indicator.outputs.items():
                # Безопасное извлечение значения из Series
                if full_column_name not in last_row.index:
                    continue

                try:
                    value = last_row[full_column_name]

                    # Если value это Series (дублирующиеся индексы), берем первое значение
                    if isinstance(value, pd.Series):
                        logger.warning(
                            "storage_manager.duplicate_columns_detected",
                            ticker=ticker,
                            timeframe=timeframe,
                            column_name=full_column_name,
                            indicator_key=base_key,
                        )
                        value = value.iloc[0]

                    # Пропускаем NaN значения
                    if pd.isna(value):
                        continue

                    records_to_insert.append(
                        {
                            "ticker": ticker,
                            "timeframe": timeframe,
                            "begin": begin_moscow,
                            "indicator_key": base_key,
                            "value_key": value_key,
                            "value": float(value),
                            "version": version,
                        }
                    )

                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(
                        "storage_manager.rt_value_extraction_error",
                        ticker=ticker,
                        timeframe=timeframe,
                        column_name=full_column_name,
                        indicator_key=base_key,
                        error=str(e),
                    )
                    continue

        if not records_to_insert:
            return

        try:
            table = pa.Table.from_pylist(records_to_insert)

            await self._ch_client.insert_arrow(
                CLICKHOUSE_CANDLES_INDICATORS_TABLE,
                table,
                settings={"async_insert": 1, "wait_for_async_insert": 0},
            )

            logger.debug(
                "storage_manager.rt_indicators_saved",
                ticker=ticker,
                timeframe=timeframe,
                records_count=len(records_to_insert),
            )

        except Exception as e:
            logger.exception(
                "storage_manager.rt_save_error",
                error=str(e),
                ticker=ticker,
                timeframe=timeframe,
            )
            raise

    async def save_batch_indicators(
        self, client: AsyncClient, long_format_df: pd.DataFrame
    ) -> None:
        """
        Сохраняет batch индикаторы в ClickHouse с версионированием.

        ReplacingMergeTree(version) обеспечивает идемпотентность.
        При дубликатах ClickHouse автоматически выбирает запись с MAX(version).

        Args:
            client: Асинхронный клиент Clickhouse.
            long_format_df: DataFrame в long format
                (ticker, timeframe, begin, indicator_key, value_key, value).
        """
        if long_format_df.empty:
            return

        version = int(time.time() * MICROSECONDS_MULTIPLIER)

        df_to_insert = long_format_df.copy()
        df_to_insert["version"] = version

        required_columns = [
            "ticker",
            "timeframe",
            "begin",
            "indicator_key",
            "value_key",
            "value",
            "version",
        ]
        df_to_insert = df_to_insert[required_columns]

        try:
            table = pa.Table.from_pandas(df_to_insert, preserve_index=False)
            insert_start = time.time()

            await client.insert_arrow(
                CLICKHOUSE_CANDLES_INDICATORS_TABLE,
                table,
                settings={"async_insert": 0, "wait_end_of_query": 1},
            )

            insert_duration = round((time.time() - insert_start) * 1000, 2)

            logger.info(
                "storage_manager.batch_indicators_saved",
                records_count=len(df_to_insert),
                insert_duration_ms=insert_duration,
                version=version,
            )

        except Exception as e:
            logger.exception(
                "storage_manager.batch_save_error",
                error=str(e),
                records_count=len(df_to_insert),
                version=version,
            )
            raise

    async def get_start_date_with_lookback(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        original_start_date: datetime,
        lookback_candles: int,
    ) -> datetime:
        """
        Находит дату начала с учетом lookback периода.

        Отступает на N свечей назад от original_start_date
        по фактическим данным в ClickHouse.

        Оптимизирован: использует один SQL запрос вместо двух
        через UNION для fallback на earliest дату.

        Args:
            client: Асинхронный клиент Clickhouse.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            original_start_date: Исходная дата начала.
            lookback_candles: Количество свечей для lookback.

        Returns:
            Дата начала с учетом lookback.
        """
        if lookback_candles == 0:
            return original_start_date

        start_date_moscow = to_clickhouse_query(original_start_date)

        query = """
            SELECT begin FROM (
                SELECT begin FROM trader.candles_base
                WHERE ticker = %(ticker)s
                  AND timeframe = %(timeframe)s
                  AND begin <= %(start_date)s
                ORDER BY begin DESC
                LIMIT 1 OFFSET %(offset)s

                UNION ALL

                SELECT min(begin) as begin FROM trader.candles_base
                WHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
            )
            WHERE begin IS NOT NULL
            ORDER BY begin DESC
            LIMIT 1
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "start_date": start_date_moscow,
            "offset": lookback_candles,
        }

        try:
            result = await client.query(query, parameters=params)

            if result.result_rows and result.result_rows[0][0]:
                smart_start = from_clickhouse(result.result_rows[0][0])

                if smart_start < original_start_date:
                    logger.info(
                        "storage_manager.lookback_calculated",
                        ticker=ticker,
                        lookback_candles=lookback_candles,
                        original_start=original_start_date.date().isoformat(),
                        smart_start=smart_start.date().isoformat(),
                    )
                else:
                    logger.warning(
                        "storage_manager.lookback_insufficient_data",
                        ticker=ticker,
                        lookback_candles=lookback_candles,
                        using_earliest=True,
                    )

                return smart_start

            return original_start_date

        except Exception as e:
            logger.exception(
                "storage_manager.lookback_error",
                error=str(e),
                ticker=ticker,
                lookback_candles=lookback_candles,
                error_type=type(e).__name__,
                fallback="using_original_start_date",
            )
            return original_start_date

    async def get_base_candles_for_period(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Загружает базовые свечи (OHLCV) из ClickHouse за период.

        Args:
            client: Асинхронный клиент Clickhouse.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Дата начала периода.
            end_date: Дата окончания периода.

        Returns:
            Список свечей в формате dict.
        """
        start_moscow = to_clickhouse_query(start_date)
        end_moscow = to_clickhouse_query(end_date)

        query = """
            SELECT * FROM trader.candles_base
            WHERE ticker = %(ticker)s
              AND timeframe = %(timeframe)s
              AND begin >= %(start_date)s
              AND begin <= %(end_date)s
            ORDER BY begin
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "start_date": start_moscow,
            "end_date": end_moscow,
        }

        try:
            result = await client.query(query, parameters=params)
            candles = list(result.named_results())

            logger.debug(
                "storage_manager.candles_loaded",
                ticker=ticker,
                timeframe=timeframe,
                count=len(candles),
            )

            return candles

        except Exception as e:
            logger.exception(
                "storage_manager.candles_load_error",
                error=str(e),
                ticker=ticker,
                timeframe=timeframe,
                error_type=type(e).__name__,
                fallback="returning_empty_list",
            )
            return []

    async def get_last_n_candles_for_context(
        self,
        ticker: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Загружает последние N свечей для RT контекста (fallback при Redis downtime).

        Используется как fallback когда Redis недоступен.
        Возвращает свечи от старых к новым для совместимости с Redis cache.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            limit: Количество последних свечей (по умолчанию 500).

        Returns:
            Список последних N свечей в формате dict, от старых к новым.

        Example:
            >>> candles = await storage.get_last_n_candles_for_context("SBER", "1h", 500)
            >>> len(candles)
            500
        """
        query = """
            SELECT ticker, timeframe, open, high, low, close, volume, begin
            FROM trader.candles_base
            WHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
            ORDER BY begin DESC
            LIMIT %(limit)s
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "limit": limit,
        }

        try:
            result = await self._ch_client.query(query, parameters=params)
            candles = list(result.named_results())

            # Reverse для порядка от старых к новым (как в Redis)
            candles.reverse()

            logger.debug(
                "storage_manager.context_candles_loaded_from_clickhouse",
                ticker=ticker,
                timeframe=timeframe,
                count=len(candles),
            )

            return candles

        except Exception as e:
            logger.exception(
                "storage_manager.context_candles_load_error",
                error=str(e),
                ticker=ticker,
                timeframe=timeframe,
                error_type=type(e).__name__,
                fallback="returning_empty_list",
            )
            return []
