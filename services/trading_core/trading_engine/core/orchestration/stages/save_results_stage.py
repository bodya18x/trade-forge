"""
Save Results Stage - сохранение результатов бэктеста.

Шестой (финальный) этап pipeline, отвечающий за:
- Расчет метрик на основе сделок
- Санитизацию данных (NaN → None)
- Сохранение результатов в PostgreSQL
- Обновление статуса задачи
"""

from __future__ import annotations

from typing import Any

from tradeforge_logger import get_logger

from core.common import JobStatus, sanitize_json
from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError
from core.simulation import calculate_metrics
from models.backtest import BacktestConfig
from repositories.postgres import BacktestRepository

logger = get_logger(__name__)


class SaveResultsStage(PipelineStage):
    """
    Этап сохранения результатов бэктеста в базу данных.

    Рассчитывает метрики, сериализует сделки и сохраняет результаты.

    Attributes:
        backtest_repo: Репозиторий для сохранения результатов.
    """

    def __init__(self, backtest_repo: BacktestRepository):
        """
        Инициализирует stage с backtest репозиторием.

        Args:
            backtest_repo: BacktestRepository для сохранения результатов.
        """
        self.backtest_repo = backtest_repo

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "save_results"

    async def execute(self, context: PipelineContext) -> None:
        """
        Сохраняет результаты бэктеста и обновляет статус задачи.

        Args:
            context: Контекст pipeline с результатами симуляции.

        Raises:
            StageError: Если отсутствуют необходимые данные или ошибка сохранения.
        """
        if not context.trades:
            logger.warning(
                "save_results.no_trades",
                job_id=str(context.job_id),
                message="No trades generated during backtest",
                correlation_id=context.correlation_id,
            )
            # Не выбрасываем ошибку - отсутствие сделок это валидный результат

        # Создаем конфиг для расчета метрик
        config = BacktestConfig.from_simulation_params(
            context.simulation_params
        )

        # Рассчитываем метрики
        metrics: dict[str, Any] = calculate_metrics(context.trades, config)

        # Сериализуем trades в JSON
        trades_json = [
            trade.model_dump(mode="json") for trade in context.trades
        ]

        # Санитизация: заменяем NaN и Infinity на None для корректного JSON
        metrics = sanitize_json(metrics)
        trades_json = sanitize_json(trades_json)

        # Сохраняем в БД
        result_id = await self.backtest_repo.save_backtest_result(
            job_id=context.job_id,
            metrics=metrics,
            trades=trades_json,
        )

        if not result_id:
            raise StageError(
                stage_name=self.name,
                message="Failed to save backtest results to database",
            )

        logger.info(
            "save_results.results_saved",
            job_id=str(context.job_id),
            result_id=str(result_id),
            trades_count=len(context.trades),
            correlation_id=context.correlation_id,
        )

        # Обновляем статус задачи на COMPLETED
        await self.backtest_repo.update_job_status(
            context.job_id, JobStatus.COMPLETED
        )

        logger.info(
            "save_results.job_completed",
            job_id=str(context.job_id),
            correlation_id=context.correlation_id,
        )
