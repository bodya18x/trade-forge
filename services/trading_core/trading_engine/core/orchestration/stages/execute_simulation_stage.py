"""
Execute Simulation Stage - выполнение симуляции бэктеста.

Пятый этап pipeline, отвечающий за:
- Создание конфигурации бэктеста
- Запуск симуляции через BacktestExecutor
- Получение списка завершенных сделок
"""

from __future__ import annotations

from tradeforge_logger import get_logger

from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError
from core.simulation import BacktestExecutor
from models.backtest import BacktestConfig

logger = get_logger(__name__)


class ExecuteSimulationStage(PipelineStage):
    """
    Этап выполнения симуляции бэктеста.

    Создает экземпляр BacktestExecutor и запускает симуляцию,
    сохраняя результаты в контексте.
    """

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "execute_simulation"

    async def execute(self, context: PipelineContext) -> None:
        """
        Выполняет симуляцию бэктеста.

        Args:
            context: Контекст pipeline с DataFrame и параметрами.

        Raises:
            StageError: Если отсутствуют необходимые данные.
        """
        if context.dataframe is None:
            raise StageError(
                stage_name=self.name,
                message="dataframe not found in context. "
                "LoadDataStage must run first.",
            )

        if not context.strategy_definition:
            raise StageError(
                stage_name=self.name,
                message="strategy_definition not found in context",
            )

        # Создаем конфигурацию бэктеста
        config = BacktestConfig.from_simulation_params(
            context.simulation_params
        )

        logger.debug(
            "execute_simulation.config_created",
            job_id=str(context.job_id),
            initial_balance=config.initial_balance,
            commission_rate=config.commission_rate,
            position_size_multiplier=config.position_size_multiplier,
            correlation_id=context.correlation_id,
        )

        logger.info(
            "execute_simulation.starting",
            job_id=str(context.job_id),
            candles_count=len(context.dataframe),
            lot_size=context.lot_size,
            correlation_id=context.correlation_id,
        )

        # Создаем executor и запускаем симуляцию
        executor = BacktestExecutor(
            df=context.dataframe,
            strategy=context.strategy_definition,
            config=config,
            lot_size=context.lot_size,
            correlation_id=context.correlation_id,
        )

        trades = executor.run()

        # Сохраняем результаты в контексте
        context.trades = trades

        logger.info(
            "execute_simulation.completed",
            job_id=str(context.job_id),
            trades_count=len(trades),
            correlation_id=context.correlation_id,
        )
