"""
Task Registry для роутинга задач на обработчики.

Реализует паттерн Registry для универсального consumer.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from tradeforge_logger import get_logger

logger = get_logger(__name__)

# Тип обработчика задачи
TaskHandler = Callable[[str, dict[str, Any]], Awaitable[int]]


class TaskRegistry:
    """
    Регистр задач и их обработчиков.

    Позволяет регистрировать обработчики для разных типов задач
    и роутить входящие задачи на нужный обработчик.
    """

    def __init__(self):
        """Инициализация пустого регистра."""
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        """
        Регистрирует обработчик для типа задачи.

        Args:
            task_type: Тип задачи (например, "collect_candles")
            handler: Async функция-обработчик
        """
        if task_type in self._handlers:
            logger.warning(
                "registry.handler_overwrite",
                task_type=task_type,
            )

        self._handlers[task_type] = handler

        logger.debug(
            "registry.handler_registered",
            task_type=task_type,
        )

    async def execute(
        self,
        task_type: str,
        ticker: str,
        params: dict[str, Any],
    ) -> int:
        """
        Выполняет задачу через зарегистрированный обработчик.

        Args:
            task_type: Тип задачи
            ticker: Тикер для обработки
            params: Параметры задачи

        Returns:
            Результат выполнения обработчика

        Raises:
            ValueError: Если обработчик для типа задачи не найден
            Exception: Если обработчик выбросил исключение
        """
        handler = self._handlers.get(task_type)

        if handler is None:
            logger.error(
                "registry.handler_not_found",
                task_type=task_type,
                available_types=list(self._handlers.keys()),
            )
            raise ValueError(
                f"Unknown task_type: {task_type}. "
                f"Available: {list(self._handlers.keys())}"
            )

        logger.debug(
            "registry.executing_task",
            task_type=task_type,
            ticker=ticker,
            params=params,
        )

        try:
            result = await handler(ticker, params)

            logger.debug(
                "registry.task_executed",
                task_type=task_type,
                ticker=ticker,
                result=result,
            )

            return result

        except Exception as e:
            logger.error(
                "registry.task_execution_failed",
                task_type=task_type,
                ticker=ticker,
                params=params,
                error=str(e),
                exc_info=True,
            )
            raise

    def get_registered_types(self) -> list[str]:
        """
        Получает список всех зарегистрированных типов задач.

        Returns:
            Список типов задач
        """
        return list(self._handlers.keys())
