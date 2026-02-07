"""
Load Job Stage - загрузка и валидация задачи на бэктест.

Первый этап pipeline, отвечающий за:
- Загрузку job details из PostgreSQL
- Загрузку ticker info для получения lot_size
- Парсинг и валидацию strategy definition
- Заполнение контекста всеми необходимыми данными
"""

from __future__ import annotations

from tradeforge_logger import get_logger

from core.common import DataNotFoundError
from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError
from models.strategy import StrategyDefinition
from repositories.postgres import BacktestRepository, TickerRepository

logger = get_logger(__name__)


class LoadJobStage(PipelineStage):
    """
    Этап загрузки и валидации задачи на бэктест.

    Координирует процесс загрузки:
    1. Загружает job details из PostgreSQL
    2. Загружает ticker info для получения lot_size
    3. Парсит и валидирует strategy definition
    4. Заполняет контекст всеми данными

    Attributes:
        backtest_repo: Репозиторий для BacktestJobs.
        ticker_repo: Репозиторий для Tickers.
    """

    def __init__(
        self,
        backtest_repo: BacktestRepository,
        ticker_repo: TickerRepository,
    ):
        """
        Инициализирует stage с репозиториями.

        Args:
            backtest_repo: Репозиторий для BacktestJobs.
            ticker_repo: Репозиторий для Tickers.
        """
        self.backtest_repo = backtest_repo
        self.ticker_repo = ticker_repo

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "load_job"

    async def execute(self, context: PipelineContext) -> None:
        """
        Загружает и валидирует задачу на бэктест.

        Args:
            context: Контекст pipeline для заполнения данными.

        Raises:
            StageError: Если job или ticker не найдены.
        """
        # 1. Загружаем job details
        job_details = await self.backtest_repo.get_job_details(context.job_id)
        if not job_details:
            raise StageError(
                stage_name=self.name,
                message=f"Job {context.job_id} not found in database",
            )

        logger.info(
            "load_job.job_details_loaded",
            job_id=str(context.job_id),
            ticker=job_details.ticker,
            timeframe=job_details.timeframe,
            correlation_id=context.correlation_id,
        )

        # 2. Загружаем ticker info
        ticker_info = await self.ticker_repo.get_ticker_info(
            job_details.ticker
        )
        if not ticker_info:
            raise StageError(
                stage_name=self.name,
                message=f"Ticker {job_details.ticker} not found",
            )

        logger.debug(
            "load_job.ticker_info_loaded",
            ticker=job_details.ticker,
            lot_size=ticker_info.lot_size,
            correlation_id=context.correlation_id,
        )

        # 3. Парсим strategy definition
        try:
            strategy_def = StrategyDefinition(
                **job_details.strategy_definition
            )
        except Exception as e:
            raise StageError(
                stage_name=self.name,
                message=f"Failed to parse strategy definition: {str(e)}",
                original_error=e,
            )

        logger.debug(
            "load_job.strategy_parsed",
            job_id=str(context.job_id),
            has_entry_buy=strategy_def.entry_buy_conditions is not None,
            has_entry_sell=strategy_def.entry_sell_conditions is not None,
            correlation_id=context.correlation_id,
        )

        # 4. Заполняем контекст
        context.job_details = job_details
        context.ticker_info = ticker_info
        context.strategy_definition = strategy_def
        context.simulation_params = job_details.simulation_params
        context.lot_size = ticker_info.lot_size

        logger.info(
            "load_job.context_populated",
            job_id=str(context.job_id),
            ticker=job_details.ticker,
            timeframe=job_details.timeframe,
            lot_size=ticker_info.lot_size,
            correlation_id=context.correlation_id,
        )
