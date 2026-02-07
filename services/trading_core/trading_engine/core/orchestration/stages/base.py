"""
Base Stage - базовый класс для этапов pipeline.

Определяет интерфейс и общую логику для всех этапов обработки бэктеста.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from tradeforge_logger import get_logger

from core.orchestration.context import PipelineContext

logger = get_logger(__name__)


class StageError(Exception):
    """Исключение для ошибок выполнения этапа pipeline."""

    def __init__(
        self,
        stage_name: str,
        message: str,
        original_error: Exception | None = None,
    ):
        """
        Инициализирует исключение этапа.

        Args:
            stage_name: Имя этапа, где произошла ошибка.
            message: Описание ошибки.
            original_error: Оригинальное исключение (если есть).
        """
        self.stage_name = stage_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Stage '{stage_name}' failed: {message}")


class PipelineStage(ABC):
    """
    Базовый класс для этапа pipeline бэктеста.

    Каждый этап отвечает за конкретную часть обработки и может:
    - Читать данные из контекста
    - Обновлять контекст новыми данными
    - Выбрасывать StageError при ошибках

    Examples:
        >>> class MyStage(PipelineStage):
        ...     @property
        ...     def name(self) -> str:
        ...         return "my_stage"
        ...
        ...     async def execute(self, context: PipelineContext) -> None:
        ...         # Логика этапа
        ...         pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Возвращает имя этапа для логирования.

        Returns:
            Строковое имя этапа (snake_case).
        """
        pass

    @abstractmethod
    async def execute(self, context: PipelineContext) -> None:
        """
        Выполняет логику этапа.

        Args:
            context: Контекст pipeline с данными для обработки.

        Raises:
            StageError: При ошибке выполнения этапа.
        """
        pass

    async def run(self, context: PipelineContext) -> None:
        """
        Обертка для execute с логированием и таймингом.

        Автоматически логирует начало/завершение этапа и время выполнения.
        Оборачивает ошибки в StageError для единообразной обработки.

        Args:
            context: Контекст pipeline.

        Raises:
            StageError: При ошибке выполнения этапа.
        """
        logger.info(
            "pipeline.stage_started",
            stage=self.name,
            job_id=str(context.job_id),
            correlation_id=context.correlation_id,
        )

        start_time = time.time()

        try:
            await self.execute(context)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "pipeline.stage_completed",
                stage=self.name,
                elapsed_ms=elapsed_ms,
                job_id=str(context.job_id),
                correlation_id=context.correlation_id,
            )

        except StageError:
            # Пробрасываем StageError дальше
            raise

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.exception(
                "pipeline.stage_failed",
                stage=self.name,
                elapsed_ms=elapsed_ms,
                error=str(e),
                job_id=str(context.job_id),
                correlation_id=context.correlation_id,
            )
            raise StageError(
                stage_name=self.name,
                message=str(e),
                original_error=e,
            ) from e
