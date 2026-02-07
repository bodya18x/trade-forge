"""
Handler для задач сбора свечей.

Создает handler функции для обработки запросов на сбор свечей.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from modules import CandlesCollectorService


def create_candles_handler(
    service: CandlesCollectorService,
) -> Callable[[str, dict], Awaitable[int]]:
    """
    Создает handler для задач сбора свечей.

    Args:
        service: Экземпляр сервиса сбора свечей

    Returns:
        Асинхронная handler функция для обработки задач сбора свечей
    """

    async def handler(ticker: str, params: dict) -> int:
        """
        Обрабатывает задачу сбора свечей.

        Args:
            ticker: Символ тикера
            params: Параметры задачи (должны содержать 'timeframe')

        Returns:
            Количество собранных свечей

        Raises:
            ValueError: Если 'timeframe' отсутствует в params
        """
        timeframe = params.get("timeframe")
        if not timeframe:
            raise ValueError("Missing 'timeframe' in params")

        return await service.collect_candles(ticker, timeframe)

    return handler
