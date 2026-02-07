"""
Analyze Strategy Stage - анализ стратегии и извлечение индикаторов.

Второй этап pipeline, отвечающий за:
- Анализ определения стратегии
- Извлечение списка требуемых индикаторов
- Логирование информации о стратегии
"""

from __future__ import annotations

from tradeforge_logger import get_logger

from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError
from core.strategy import StrategyAnalyzer

logger = get_logger(__name__)


class AnalyzeStrategyStage(PipelineStage):
    """
    Этап анализа стратегии и извлечения требуемых индикаторов.

    Использует StrategyAnalyzer для извлечения всех индикаторов,
    необходимых для выполнения стратегии.

    Attributes:
        strategy_analyzer: Анализатор стратегий для извлечения индикаторов.
    """

    def __init__(self, strategy_analyzer: StrategyAnalyzer):
        """
        Инициализирует stage с анализатором стратегий.

        Args:
            strategy_analyzer: StrategyAnalyzer для извлечения индикаторов.
        """
        self.strategy_analyzer = strategy_analyzer

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "analyze_strategy"

    async def execute(self, context: PipelineContext) -> None:
        """
        Анализирует стратегию и извлекает требуемые индикаторы.

        Args:
            context: Контекст pipeline с strategy_definition.

        Raises:
            StageError: Если strategy_definition отсутствует в контексте.
        """
        if not context.strategy_definition:
            raise StageError(
                stage_name=self.name,
                message="strategy_definition not found in context. "
                "LoadJobStage must run first.",
            )

        # Логируем информацию о стратегии
        logger.debug(
            "analyze_strategy.strategy_info",
            job_id=str(context.job_id),
            has_entry_buy=context.strategy_definition.entry_buy_conditions
            is not None,
            has_entry_sell=context.strategy_definition.entry_sell_conditions
            is not None,
            has_exit=context.strategy_definition.exit_conditions is not None,
            has_exit_long=context.strategy_definition.exit_long_conditions
            is not None,
            has_exit_short=context.strategy_definition.exit_short_conditions
            is not None,
            has_stop_loss=context.strategy_definition.stop_loss is not None,
            correlation_id=context.correlation_id,
        )

        # Извлекаем требуемые индикаторы
        required_indicators = (
            await self.strategy_analyzer.extract_required_indicators(
                context.strategy_definition
            )
        )

        # Сохраняем в контексте
        context.required_indicators = required_indicators

        logger.info(
            "analyze_strategy.indicators_extracted",
            job_id=str(context.job_id),
            indicators_count=len(required_indicators),
            correlation_id=context.correlation_id,
        )
