"""
Load Data Stage - загрузка данных для бэктеста.

Четвертый этап pipeline, отвечающий за:
- Загрузку базовых свечей из ClickHouse
- Загрузку значений индикаторов из ClickHouse
- Подготовку DataFrame для бэктеста
"""

from __future__ import annotations

import time

from tradeforge_logger import get_logger

from core.common import SLOW_DATA_LOAD_THRESHOLD_MS, DataNotFoundError
from core.data import prepare_dataframe
from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError
from repositories.clickhouse import ClickHouseRepository

logger = get_logger(__name__)


class LoadDataStage(PipelineStage):
    """
    Этап загрузки данных для бэктеста из ClickHouse.

    Загружает базовые свечи и индикаторы, подготавливает DataFrame.

    Attributes:
        clickhouse_repo: Репозиторий для работы с ClickHouse.
    """

    def __init__(self, clickhouse_repo: ClickHouseRepository):
        """
        Инициализирует stage с ClickHouse репозиторием.

        Args:
            clickhouse_repo: ClickHouseRepository для загрузки данных.
        """
        self.clickhouse_repo = clickhouse_repo

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "load_data"

    async def execute(self, context: PipelineContext) -> None:
        """
        Загружает данные для бэктеста и подготавливает DataFrame.

        Args:
            context: Контекст pipeline с параметрами загрузки.

        Raises:
            StageError: Если данные не найдены или ошибка загрузки.
        """
        if not context.job_details:
            raise StageError(
                stage_name=self.name,
                message="job_details not found in context",
            )

        logger.info(
            "load_data.loading_started",
            job_id=str(context.job_id),
            ticker=context.ticker,
            timeframe=context.timeframe,
            correlation_id=context.correlation_id,
        )

        load_start = time.time()

        # Загружаем данные из ClickHouse
        base_candles, indicators_data = (
            await self.clickhouse_repo.fetch_data_for_backtest(
                client=context.client,
                ticker=context.ticker,
                timeframe=context.timeframe,
                start_date=context.start_date,
                end_date=context.end_date,
                indicator_key_pairs=context.required_indicators,
            )
        )

        elapsed_load_ms = round((time.time() - load_start) * 1000, 2)

        if not base_candles:
            raise StageError(
                stage_name=self.name,
                message=f"No candles found for {context.ticker} {context.timeframe}",
            )

        # Подготавливаем DataFrame
        df = prepare_dataframe(
            base_candles, indicators_data, context.correlation_id
        )

        # Сохраняем в контекст
        context.dataframe = df

        logger.info(
            "load_data.loading_completed",
            job_id=str(context.job_id),
            candles_count=len(df),
            elapsed_ms=elapsed_load_ms,
            correlation_id=context.correlation_id,
        )

        # Warning для медленной загрузки данных
        if elapsed_load_ms > SLOW_DATA_LOAD_THRESHOLD_MS:
            logger.warning(
                "load_data.slow_loading_detected",
                elapsed_ms=elapsed_load_ms,
                threshold_ms=SLOW_DATA_LOAD_THRESHOLD_MS,
                candles_count=len(df),
                ticker=context.ticker,
                timeframe=context.timeframe,
                job_id=str(context.job_id),
                correlation_id=context.correlation_id,
            )
