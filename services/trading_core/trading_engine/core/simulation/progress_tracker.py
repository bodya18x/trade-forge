"""
Progress Tracker - отслеживание прогресса и timeout симуляции бэктеста.

Управляет:
1. Логированием прогресса (каждые 10% обработанных свечей)
2. Защитой от бесконечного выполнения (timeout 5 минут)
"""

from __future__ import annotations

import time

from tradeforge_logger import get_logger

from core.common import (
    SIMULATION_PROGRESS_LOG_INTERVAL,
    SIMULATION_TIMEOUT_CHECK_INTERVAL,
    SIMULATION_TIMEOUT_SECONDS,
    BacktestExecutionError,
)
from core.simulation.exit_checker import TradingState

logger = get_logger(__name__)


class ProgressTracker:
    """
    Отслеживает прогресс симуляции и защищает от timeout.

    Attributes:
        start_time: Время начала симуляции (Unix timestamp).
        next_log_threshold: Следующий порог для логирования прогресса (0.1 = 10%).
        ticker: Символ инструмента для логирования.
        correlation_id: ID корреляции для трейсинга.

    Examples:
        >>> tracker = ProgressTracker(ticker="SBER", correlation_id="abc-123")
        >>> # В цикле симуляции:
        >>> for i in range(1, total_candles):
        ...     tracker.check_timeout(i, total_candles, trades_count)
        ...     tracker.log_progress_if_needed(i, total_candles, state, trades_count)
    """

    def __init__(self, ticker: str, correlation_id: str | None = None):
        """
        Инициализирует трекер прогресса.

        Args:
            ticker: Символ инструмента.
            correlation_id: ID корреляции для логирования.
        """
        self.start_time = time.time()
        self.next_log_threshold = SIMULATION_PROGRESS_LOG_INTERVAL
        self.ticker = ticker
        self.correlation_id = correlation_id

    def check_timeout(
        self, current_candle: int, total_candles: int, trades_count: int
    ) -> None:
        """
        Проверяет превышение timeout симуляции.

        Выполняется каждые SIMULATION_TIMEOUT_CHECK_INTERVAL свечей для оптимизации.

        Args:
            current_candle: Индекс текущей свечи.
            total_candles: Общее количество свечей.
            trades_count: Количество завершенных сделок.

        Raises:
            BacktestExecutionError: При превышении SIMULATION_TIMEOUT_SECONDS.
        """
        if current_candle % SIMULATION_TIMEOUT_CHECK_INTERVAL == 0:
            elapsed = time.time() - self.start_time
            if elapsed > SIMULATION_TIMEOUT_SECONDS:
                logger.error(
                    "progress_tracker.simulation_timeout",
                    elapsed_seconds=round(elapsed, 2),
                    processed_candles=current_candle,
                    total_candles=total_candles,
                    progress_pct=round(
                        current_candle / total_candles * 100, 1
                    ),
                    trades_completed=trades_count,
                    ticker=self.ticker,
                    correlation_id=self.correlation_id,
                )
                raise BacktestExecutionError(
                    f"Simulation timeout after {elapsed:.1f}s. "
                    f"Processed {current_candle}/{total_candles} candles "
                    f"({current_candle/total_candles*100:.1f}%). "
                    f"Consider reducing dataset size or optimizing strategy complexity."
                )

    def log_progress_if_needed(
        self,
        current_candle: int,
        total_candles: int,
        state: TradingState,
        trades_count: int,
    ) -> None:
        """
        Логирует прогресс симуляции если достигнут порог.

        Порог увеличивается каждый раз на SIMULATION_PROGRESS_LOG_INTERVAL (10%).

        Args:
            current_candle: Индекс текущей свечи.
            total_candles: Общее количество свечей.
            state: Текущее состояние торговли.
            trades_count: Количество завершенных сделок.
        """
        progress = current_candle / total_candles
        if progress >= self.next_log_threshold:
            elapsed = time.time() - self.start_time
            logger.info(
                "progress_tracker.simulation_progress",
                progress_pct=round(progress * 100, 1),
                processed_candles=current_candle,
                total_candles=total_candles,
                trades_so_far=trades_count,
                current_capital=round(state.current_capital, 2),
                elapsed_seconds=round(elapsed, 2),
                ticker=self.ticker,
                correlation_id=self.correlation_id,
            )
            self.next_log_threshold += SIMULATION_PROGRESS_LOG_INTERVAL

    def get_total_elapsed(self) -> float:
        """
        Возвращает общее время выполнения симуляции.

        Returns:
            Время в секундах с момента инициализации трекера.
        """
        return time.time() - self.start_time
