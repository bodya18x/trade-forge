"""
Backtest Pipeline - координатор выполнения бэктеста через этапы.

Управляет последовательным выполнением всех этапов обработки бэктеста
с централизованной обработкой ошибок.
"""

from __future__ import annotations

import time

from tradeforge_logger import get_logger

from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError

logger = get_logger(__name__)


class BacktestPipeline:
    """
    Pipeline для выполнения бэктеста с четкими этапами.

    Управляет полным жизненным циклом бэктеста через последовательность stages:
    1. LoadJobStage - загрузка и валидация задачи
    2. AnalyzeStrategyStage - анализ стратегии и извлечение индикаторов
    3. EnsureDataStage - проверка наличия индикаторов
    4. LoadDataStage - загрузка данных для бэктеста
    5. ExecuteSimulationStage - выполнение симуляции
    6. SaveResultsStage - сохранение результатов

    Attributes:
        stages: Список этапов для выполнения.

    Examples:
        >>> pipeline = BacktestPipeline(stages=[
        ...     LoadJobStage(...),
        ...     AnalyzeStrategyStage(...),
        ...     # ... другие stages
        ... ])
        >>> context = PipelineContext(job_id=uuid, client=client)
        >>> await pipeline.run(context)
    """

    def __init__(self, stages: list[PipelineStage]):
        """
        Инициализирует pipeline с этапами.

        Args:
            stages: Список этапов для последовательного выполнения.
        """
        self.stages = stages

    async def run(self, context: PipelineContext) -> None:
        """
        Запускает pipeline с последовательным выполнением всех этапов.

        Координирует выполнение, логирует прогресс и обрабатывает ошибки.

        Args:
            context: Контекст с данными для обработки.

        Raises:
            StageError: При ошибке выполнения любого этапа.
        """
        pipeline_start = time.time()

        logger.info(
            "pipeline.started",
            job_id=str(context.job_id),
            stages_count=len(self.stages),
            correlation_id=context.correlation_id,
        )

        try:
            for idx, stage in enumerate(self.stages, start=1):
                logger.debug(
                    "pipeline.stage_starting",
                    stage=stage.name,
                    stage_number=idx,
                    total_stages=len(self.stages),
                    job_id=str(context.job_id),
                    correlation_id=context.correlation_id,
                )

                # Выполняем этап
                await stage.run(context)

                logger.debug(
                    "pipeline.stage_finished",
                    stage=stage.name,
                    stage_number=idx,
                    total_stages=len(self.stages),
                    job_id=str(context.job_id),
                    correlation_id=context.correlation_id,
                )

            # Все этапы выполнены успешно
            total_elapsed = time.time() - pipeline_start
            logger.info(
                "pipeline.completed_successfully",
                job_id=str(context.job_id),
                total_elapsed_seconds=round(total_elapsed, 2),
                trades_count=len(context.trades),
                correlation_id=context.correlation_id,
            )

        except StageError as e:
            total_elapsed = time.time() - pipeline_start
            logger.error(
                "pipeline.stage_error",
                stage=e.stage_name,
                error=e.message,
                job_id=str(context.job_id),
                total_elapsed_seconds=round(total_elapsed, 2),
                correlation_id=context.correlation_id,
            )
            raise

        except Exception as e:
            total_elapsed = time.time() - pipeline_start
            logger.exception(
                "pipeline.unexpected_error",
                error=str(e),
                job_id=str(context.job_id),
                total_elapsed_seconds=round(total_elapsed, 2),
                correlation_id=context.correlation_id,
            )
            raise
