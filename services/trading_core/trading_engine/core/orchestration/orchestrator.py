"""
Backtest Orchestrator - координатор процесса бэктестинга.

Отвечает за создание и запуск pipeline для обработки бэктеста.
Делегирует специфичную логику каждого этапа отдельным stages.
"""

from __future__ import annotations

import uuid

from clickhouse_connect.driver.asyncclient import AsyncClient
from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_logger import get_logger

from core.common import JobStatus
from core.data import IndicatorResolver
from core.orchestration.context import PipelineContext
from core.orchestration.pipeline import BacktestPipeline
from core.orchestration.stages import StageError
from core.orchestration.stages.analyze_strategy_stage import (
    AnalyzeStrategyStage,
)
from core.orchestration.stages.ensure_data_stage import EnsureDataStage
from core.orchestration.stages.execute_simulation_stage import (
    ExecuteSimulationStage,
)
from core.orchestration.stages.load_data_stage import LoadDataStage
from core.orchestration.stages.load_job_stage import LoadJobStage
from core.orchestration.stages.save_results_stage import SaveResultsStage
from core.strategy import StrategyAnalyzer
from repositories.clickhouse import ClickHouseRepository
from repositories.postgres import (
    BacktestRepository,
    IndicatorRepository,
    TickerRepository,
)

logger = get_logger(__name__)


class BacktestOrchestrator:
    """
    Orchestrator для координации процесса бэктестинга.

    Управляет полным жизненным циклом задачи на бэктест через Pipeline:
    1. Создает pipeline с необходимыми stages
    2. Инициализирует контекст с данными задачи
    3. Запускает pipeline
    4. Обрабатывает ошибки и обновляет статусы

    Архитектурный паттерн: Pipeline + Dependency Injection

    Attributes:
        backtest_repo: Репозиторий для работы с BacktestJobs и BacktestResults.
        ticker_repo: Репозиторий для работы с Tickers (с TTL кэшем).
        indicator_repo: Репозиторий для работы с реестром индикаторов.
        clickhouse_repo: Репозиторий для работы с ClickHouse.
        producer: Kafka producer для отправки запросов на расчет индикаторов.
        strategy_analyzer: Анализатор стратегий для извлечения индикаторов.
        indicator_resolver: Резолвер индикаторов для проверки и запроса расчета.
    """

    def __init__(
        self,
        backtest_repo: BacktestRepository,
        ticker_repo: TickerRepository,
        indicator_repo: IndicatorRepository,
        clickhouse_repo: ClickHouseRepository,
        producer: AsyncKafkaProducer,
    ):
        """
        Инициализирует orchestrator с модульными репозиториями.

        Args:
            backtest_repo: Репозиторий для BacktestJobs и BacktestResults.
            ticker_repo: Репозиторий для Tickers.
            indicator_repo: Репозиторий для индикаторов.
            clickhouse_repo: Репозиторий ClickHouse.
            producer: Kafka producer.
        """
        self.backtest_repo = backtest_repo
        self.ticker_repo = ticker_repo
        self.indicator_repo = indicator_repo
        self.clickhouse_repo = clickhouse_repo
        self.producer = producer

        # Инициализируем анализаторы для использования в stages
        self.strategy_analyzer = StrategyAnalyzer(indicator_repo)
        self.indicator_resolver = IndicatorResolver(
            clickhouse_repo, producer, indicator_repo
        )

    def _create_pipeline(self) -> BacktestPipeline:
        """
        Создает pipeline с необходимыми этапами.

        Определяет последовательность обработки бэктеста:
        1. LoadJobStage - загрузка и валидация задачи
        2. AnalyzeStrategyStage - анализ стратегии
        3. EnsureDataStage - проверка наличия индикаторов
        4. LoadDataStage - загрузка данных
        5. ExecuteSimulationStage - выполнение симуляции
        6. SaveResultsStage - сохранение результатов

        Returns:
            Настроенный BacktestPipeline с этапами.
        """
        stages = [
            LoadJobStage(
                backtest_repo=self.backtest_repo,
                ticker_repo=self.ticker_repo,
            ),
            AnalyzeStrategyStage(strategy_analyzer=self.strategy_analyzer),
            EnsureDataStage(indicator_resolver=self.indicator_resolver),
            LoadDataStage(clickhouse_repo=self.clickhouse_repo),
            ExecuteSimulationStage(),
            SaveResultsStage(backtest_repo=self.backtest_repo),
        ]

        return BacktestPipeline(stages=stages)

    async def process_backtest(
        self,
        job_id: uuid.UUID,
        client: AsyncClient,
        correlation_id: str | None = None,
        skip_indicator_check: bool = False,
    ) -> None:
        """
        Обрабатывает полный цикл бэктеста через pipeline.

        Координирует процесс, делегируя специфичную логику stages:
        - Создает pipeline с необходимыми этапами
        - Инициализирует контекст
        - Запускает pipeline
        - Обрабатывает ошибки

        Args:
            job_id: UUID задачи на бэктест.
            client: Async ClickHouse client из pool.
            correlation_id: Correlation ID для трейсинга.
            skip_indicator_check: Пропустить проверку полноты индикаторов
                (используется после получения CALCULATION_SUCCESS).

        Raises:
            StageError: При ошибке выполнения любого этапа pipeline.
        """
        logger.info(
            "orchestrator.backtest_started",
            job_id=str(job_id),
            correlation_id=correlation_id,
        )

        try:
            # Создаем pipeline
            pipeline = self._create_pipeline()

            # Инициализируем контекст
            context = PipelineContext(
                job_id=job_id,
                client=client,
                correlation_id=correlation_id,
                skip_indicator_check=skip_indicator_check,
            )

            # Запускаем pipeline
            await pipeline.run(context)

            logger.info(
                "orchestrator.backtest_completed_successfully",
                job_id=str(job_id),
                trades_count=len(context.trades),
                correlation_id=correlation_id,
            )

        except StageError as e:
            await self._handle_stage_error(job_id, e, correlation_id)

        except Exception as e:
            await self._handle_unexpected_error(job_id, e, correlation_id)

    async def _handle_stage_error(
        self,
        job_id: uuid.UUID,
        error: StageError,
        correlation_id: str | None,
    ) -> None:
        """
        Обрабатывает ошибки выполнения этапов pipeline.

        Особая обработка для EnsureDataStage:
        - Если индикаторы не готовы - это ожидаемая ситуация "круга почета"
        - Не обновляем статус job на FAILED
        - Просто логируем и выходим

        Args:
            job_id: UUID задачи.
            error: Исключение StageError.
            correlation_id: ID корреляции.
        """
        # Особая обработка для "круга почета"
        if (
            error.stage_name == "ensure_data"
            and "Waiting for round trip" in error.message
        ):
            logger.info(
                "orchestrator.waiting_for_indicators",
                job_id=str(job_id),
                message=error.message,
                correlation_id=correlation_id,
            )
            # НЕ обновляем статус - задача остается в RUNNING
            # Ждем возврата сообщения от Data Processor
            return

        # Для остальных ошибок - обновляем статус на FAILED
        logger.error(
            "orchestrator.stage_error",
            job_id=str(job_id),
            stage=error.stage_name,
            error=error.message,
            correlation_id=correlation_id,
        )

        await self.backtest_repo.update_job_status(
            job_id, JobStatus.FAILED, error_message=error.message
        )

    async def _handle_unexpected_error(
        self,
        job_id: uuid.UUID,
        error: Exception,
        correlation_id: str | None,
    ) -> None:
        """
        Обрабатывает неожиданные ошибки выполнения.

        Args:
            job_id: UUID задачи.
            error: Исключение.
            correlation_id: ID корреляции.
        """
        logger.exception(
            "orchestrator.unexpected_error",
            job_id=str(job_id),
            error=str(error),
            correlation_id=correlation_id,
        )

        await self.backtest_repo.update_job_status(
            job_id, JobStatus.FAILED, error_message=str(error)
        )
