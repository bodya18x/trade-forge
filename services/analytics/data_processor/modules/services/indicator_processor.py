"""
Indicator Processor для расчета и сохранения индикаторов.

Обрабатывает индикаторы с использованием distributed locks для предотвращения
race conditions при параллельной обработке.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from clickhouse_connect.driver import Client
from tradeforge_logger import get_logger

from calc.base import IndicatorPipeline
from core.protocols import ILockManager, IStorageManager

from .data_transformer import DataTransformer

logger = get_logger(__name__)


class IndicatorProcessor:
    """
    Обрабатывает индикаторы.

    Каждый индикатор обрабатывается независимо с блокировкой по ключу
    ticker:timeframe:indicator_key. Это предотвращает дублирование расчетов
    при параллельном выполнении нескольких batch-задач.

    Attributes:
        storage: Менеджер хранилища данных.
        locks: Менеджер распределенных блокировок.
        transformer: Трансформер данных в long format.
    """

    def __init__(
        self,
        storage_manager: IStorageManager,
        lock_manager: ILockManager,
    ):
        """
        Инициализирует процессор индикаторов.

        Args:
            storage_manager: Менеджер хранилища.
            lock_manager: Менеджер блокировок.
        """
        self.storage = storage_manager
        self.locks = lock_manager
        self.transformer = DataTransformer()

    async def process_indicators(
        self,
        client: Client,
        pipeline: IndicatorPipeline,
        df: pd.DataFrame,
        ticker: str,
        timeframe: str,
        original_start_date: datetime,
        job_id: str,
        correlation_id: str | None = None,
    ) -> int:
        """
        Обрабатывает все индикаторы последовательно с блокировками.

        Для каждого индикатора:
        1. Получает блокировку (с ожиданием)
        2. Рассчитывает индикатор
        3. Трансформирует в long format
        4. Сохраняет в ClickHouse
        5. Освобождает блокировку

        Args:
            client: Клиент Clickhouse.
            pipeline: Пайплайн индикаторов для расчета.
            df: DataFrame с базовыми свечами.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            original_start_date: Дата начала без lookback периода.
            job_id: ID задачи для логирования.
            correlation_id: Correlation ID для трейсинга.

        Returns:
            Количество успешно обработанных индикаторов.

        Raises:
            RetryableError: При timeout получения блокировки.
        """
        processed_count = 0

        for indicator in pipeline.indicators:
            indicator_key = indicator.get_base_key()

            lock_key = self.locks.generate_indicator_lock_key(
                ticker, timeframe, indicator_key
            )

            logger.debug(
                "indicator_processor.processing",
                job_id=job_id,
                indicator_key=indicator_key,
                lock_key=lock_key,
                correlation_id=correlation_id,
            )

            # TODO: данная блокировка закомментирована по причине,
            # что на текущем этапе она совершенно не предоставляет никаких преимуществ.
            # Оставлена для будущего расширения с фильтрацией записей.

            # acquired = await self.locks.acquire_lock_with_blocking_wait(
            #     lock_key=lock_key,
            #     timeout_seconds=DEFAULT_LOCK_TIMEOUT_SECONDS,
            #     poll_interval=DEFAULT_LOCK_POLL_INTERVAL_SECONDS,
            #     lock_ttl=DEFAULT_LOCK_TTL_SECONDS,
            # )

            # if not acquired:
            #     logger.error(
            #         "indicator_processor.lock_timeout",
            #         job_id=job_id,
            #         indicator_key=indicator_key,
            #         correlation_id=correlation_id,
            #     )
            #     raise RetryableError(
            #         f"Lock timeout for {lock_key}. Task will be retried by Kafka."
            #     )

            try:
                single_pipeline = IndicatorPipeline([indicator])
                processed_df = single_pipeline.compute_all(df.copy())

                long_df = self.transformer.transform_single_indicator(
                    df=processed_df,
                    indicator=indicator,
                    ticker=ticker,
                    timeframe=timeframe,
                    original_start_date=original_start_date,
                )

                if long_df.empty:
                    logger.warning(
                        "indicator_processor.no_data",
                        job_id=job_id,
                        indicator_key=indicator_key,
                        correlation_id=correlation_id,
                    )
                    continue

                await self.storage.save_batch_indicators(client, long_df)

                logger.info(
                    "indicator_processor.saved",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    records_count=len(long_df),
                    correlation_id=correlation_id,
                )

                processed_count += 1

            except ValueError as e:
                logger.exception(
                    "indicator_processor.validation_error",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    error=str(e),
                    error_type="validation",
                    correlation_id=correlation_id,
                )
                raise
            except KeyError as e:
                logger.exception(
                    "indicator_processor.missing_column_error",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    error=str(e),
                    error_type="missing_column",
                    correlation_id=correlation_id,
                )
                raise
            except ConnectionError as e:
                logger.exception(
                    "indicator_processor.connection_error",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    error=str(e),
                    error_type="connection",
                    correlation_id=correlation_id,
                )
                raise
            except TimeoutError as e:
                logger.exception(
                    "indicator_processor.timeout_error",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    error=str(e),
                    error_type="timeout",
                    correlation_id=correlation_id,
                )
                raise
            except Exception as e:
                logger.exception(
                    "indicator_processor.error",
                    job_id=job_id,
                    indicator_key=indicator_key,
                    error=str(e),
                    error_type=type(e).__name__,
                    correlation_id=correlation_id,
                )
                raise

            finally:
                pass
                # TODO: вернуть, когда вернется блокировка
                # await self.locks.release_lock(lock_key)

        return processed_count
