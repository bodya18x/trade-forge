"""
Signal Calculator - расчет торговых сигналов для бэктеста.

Отвечает за векторизованный расчет всех сигналов (entry, exit, stop loss)
для всего DataFrame за один проход.
"""

from __future__ import annotations

import pandas as pd
from tradeforge_logger import get_logger

from core.strategy import StrategyEvaluator
from models.strategy import StrategyDefinition

logger = get_logger(__name__)


class SignalsBatch:
    """
    Пакет всех предрассчитанных сигналов для бэктеста.

    Векторизованный подход: все сигналы рассчитываются один раз,
    затем используются в пошаговой симуляции.

    Attributes:
        entry_buy: Серия сигналов на вход в Long позицию.
        entry_sell: Серия сигналов на вход в Short позицию.
        exit_long: Серия сигналов на выход из Long позиции.
        exit_short: Серия сигналов на выход из Short позиции.
        sl_long: Серия уровней Stop Loss для Long позиций.
        sl_short: Серия уровней Stop Loss для Short позиций.
    """

    __slots__ = (
        "entry_buy",
        "entry_sell",
        "exit_long",
        "exit_short",
        "sl_long",
        "sl_short",
    )

    def __init__(
        self,
        entry_buy: pd.Series,
        entry_sell: pd.Series,
        exit_long: pd.Series,
        exit_short: pd.Series,
        sl_long: pd.Series,
        sl_short: pd.Series,
    ):
        """
        Инициализирует пакет сигналов.

        Args:
            entry_buy: Серия bool сигналов на покупку.
            entry_sell: Серия bool сигналов на продажу.
            exit_long: Серия bool сигналов на выход из лонга.
            exit_short: Серия bool сигналов на выход из шорта.
            sl_long: Серия float уровней SL для лонга.
            sl_short: Серия float уровней SL для шорта.
        """
        self.entry_buy = entry_buy
        self.entry_sell = entry_sell
        self.exit_long = exit_long
        self.exit_short = exit_short
        self.sl_long = sl_long
        self.sl_short = sl_short


class SignalCalculator:
    """
    Калькулятор торговых сигналов для бэктестинга.

    Использует StrategyEvaluator для векторизованного расчета всех сигналов
    на основе определения стратегии.

    Attributes:
        evaluator: Оценщик стратегии для расчета условий.
        correlation_id: ID корреляции для трейсинга.

    Examples:
        >>> calculator = SignalCalculator(strategy, correlation_id="test-123")
        >>> signals = calculator.calculate_all_signals(df)
        >>> print(f"Buy signals: {signals.entry_buy.sum()}")
        Buy signals: 42
    """

    def __init__(
        self,
        strategy: StrategyDefinition,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует калькулятор сигналов.

        Args:
            strategy: Определение торговой стратегии.
            correlation_id: ID корреляции для логирования.
        """
        self.evaluator = StrategyEvaluator(strategy, correlation_id)
        self.correlation_id = correlation_id

    def calculate_all_signals(self, df: pd.DataFrame) -> SignalsBatch:
        """
        Векторизованный расчет всех сигналов для бэктеста.

        Один проход по DataFrame для расчета всех сигналов:
        - Entry signals (buy/sell)
        - Exit signals (long/short)
        - Stop loss levels (long/short)

        Args:
            df: DataFrame с OHLCV данными и индикаторами.

        Returns:
            SignalsBatch с предрассчитанными сигналами для всех свечей.

        Raises:
            ValueError: Если DataFrame пустой или не содержит нужных колонок.

        Examples:
            >>> df = pd.DataFrame(...)  # OHLCV + indicators
            >>> signals = calculator.calculate_all_signals(df)
            >>> # Все сигналы рассчитаны векторизованно
            >>> assert len(signals.entry_buy) == len(df)
        """
        logger.debug(
            "signal_calculator.calculating_signals",
            rows=len(df),
            correlation_id=self.correlation_id,
        )

        # Расчет entry сигналов
        entry_buy, entry_sell = self.evaluator.evaluate_entry(df)

        # Расчет exit сигналов
        exit_long, exit_short = self.evaluator.evaluate_exit(df)

        # Расчет stop loss уровней
        sl_long, sl_short = self.evaluator.calculate_stop_loss_series(df)

        logger.debug(
            "signal_calculator.signals_calculated",
            entry_buy_count=int(entry_buy.sum()),
            entry_sell_count=int(entry_sell.sum()),
            exit_long_count=int(exit_long.sum()),
            exit_short_count=int(exit_short.sum()),
            correlation_id=self.correlation_id,
        )

        return SignalsBatch(
            entry_buy=entry_buy,
            entry_sell=entry_sell,
            exit_long=exit_long,
            exit_short=exit_short,
            sl_long=sl_long,
            sl_short=sl_short,
        )

    def log_signals_summary(
        self, signals: SignalsBatch, df_index: pd.Index
    ) -> None:
        """
        Логирует статистику по сигналам.

        Args:
            signals: Пакет сигналов для анализа.
            df_index: Индекс DataFrame для поиска первых сигналов.
        """
        buy_count = int(signals.entry_buy.sum())
        sell_count = int(signals.entry_sell.sum())
        exit_long_count = int(signals.exit_long.sum())
        exit_short_count = int(signals.exit_short.sum())

        if buy_count == 0 and sell_count == 0:
            logger.warning(
                "signal_calculator.no_entry_signals_generated",
                buy_signals=buy_count,
                sell_signals=sell_count,
                exit_long_signals=exit_long_count,
                exit_short_signals=exit_short_count,
                correlation_id=self.correlation_id,
            )
        else:
            logger.info(
                "signal_calculator.signals_generated_successfully",
                buy_count=buy_count,
                sell_count=sell_count,
                exit_long_count=exit_long_count,
                exit_short_count=exit_short_count,
                first_buy_signal=(
                    str(df_index[signals.entry_buy][0])
                    if signals.entry_buy.any()
                    else None
                ),
                first_sell_signal=(
                    str(df_index[signals.entry_sell][0])
                    if signals.entry_sell.any()
                    else None
                ),
                correlation_id=self.correlation_id,
            )
