"""
Ensure Data Stage - проверка наличия индикаторов и запрос их расчета.

Третий этап pipeline, отвечающий за:
- Проверку наличия требуемых индикаторов в ClickHouse
- Запрос расчета недостающих индикаторов через Kafka
- Реализацию "круга почета" (round trip pattern)
"""

from __future__ import annotations

from tradeforge_logger import get_logger

from core.data import IndicatorResolver
from core.orchestration.context import PipelineContext
from core.orchestration.stages.base import PipelineStage, StageError

logger = get_logger(__name__)


class EnsureDataStage(PipelineStage):
    """
    Этап проверки наличия индикаторов и запроса их расчета.

    "КРУГ ПОЧЕТА" (Round Trip Pattern):
    Если индикаторы отсутствуют:
    1. Trading Engine отправляет запрос в Kafka
    2. Data Processor рассчитывает индикаторы
    3. Data Processor отправляет сообщение обратно
    4. Trading Engine получает и запускает бэктест заново

    Attributes:
        indicator_resolver: Резолвер для проверки и запроса индикаторов.
    """

    def __init__(self, indicator_resolver: IndicatorResolver):
        """
        Инициализирует stage с indicator resolver.

        Args:
            indicator_resolver: IndicatorResolver для работы с индикаторами.
        """
        self.indicator_resolver = indicator_resolver

    @property
    def name(self) -> str:
        """Возвращает имя этапа."""
        return "ensure_data"

    async def execute(self, context: PipelineContext) -> None:
        """
        Проверяет наличие индикаторов и запрашивает расчет если нужно.

        Args:
            context: Контекст pipeline с требуемыми данными.

        Raises:
            StageError: Если необходимые данные отсутствуют в контексте.
        """
        if not context.job_details:
            raise StageError(
                stage_name=self.name,
                message="job_details not found in context. "
                "LoadJobStage must run first.",
            )

        # Если флаг skip_indicator_check установлен - пропускаем проверку
        # Это происходит после получения CALCULATION_SUCCESS от Data Processor
        if context.skip_indicator_check:
            logger.info(
                "ensure_data.check_skipped",
                job_id=str(context.job_id),
                message="Indicator check skipped after CALCULATION_SUCCESS",
                correlation_id=context.correlation_id,
            )
            return

        if not context.required_indicators:
            logger.info(
                "ensure_data.no_indicators_required",
                job_id=str(context.job_id),
                correlation_id=context.correlation_id,
            )
            return

        # Проверяем наличие индикаторов
        indicators_ready = (
            await self.indicator_resolver.ensure_indicators_available(
                client=context.client,
                ticker=context.ticker,
                timeframe=context.timeframe,
                start_date=context.start_date,
                end_date=context.end_date,
                required_indicators=context.required_indicators,
                job_id=context.job_id,
                correlation_id=context.correlation_id,
            )
        )

        if not indicators_ready:
            # Индикаторы отсутствуют, запрос на расчет отправлен
            # Pipeline должен остановиться и ждать "круга почета"
            logger.info(
                "ensure_data.waiting_for_round_trip",
                job_id=str(context.job_id),
                message="Indicators calculation requested, waiting for round trip",
                correlation_id=context.correlation_id,
            )

            raise StageError(
                stage_name=self.name,
                message="Indicators not ready, calculation requested. "
                "Waiting for round trip from Data Processor.",
            )

        logger.info(
            "ensure_data.indicators_ready",
            job_id=str(context.job_id),
            indicators_count=len(context.required_indicators),
            correlation_id=context.correlation_id,
        )
