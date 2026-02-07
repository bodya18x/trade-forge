"""
Simulation Lifecycle - управление жизненным циклом симуляции бэктеста.

Отвечает за:
1. Инициализацию состояния и кэша перед началом симуляции
2. Финализацию: закрытие последней позиции и логирование итогов
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tradeforge_logger import get_logger

from core.simulation.data_cache import CachedData, DataCacheManager
from core.simulation.exit_checker import TradingState
from core.simulation.signal_calculator import SignalsBatch
from models.backtest import BacktestConfig, BacktestTrade

if TYPE_CHECKING:
    import pandas as pd

    from core.simulation.position_manager import PositionManager

logger = get_logger(__name__)


class SimulationLifecycle:
    """
    Управляет жизненным циклом симуляции бэктеста.

    Attributes:
        config: Конфигурация бэктеста (initial_balance, etc).
        ticker: Символ инструмента для логирования.
        correlation_id: ID корреляции для трейсинга.

    Examples:
        >>> lifecycle = SimulationLifecycle(
        ...     config=BacktestConfig(initial_balance=100000),
        ...     ticker="SBER",
        ...     correlation_id="abc-123"
        ... )
        >>> state, cached = lifecycle.initialize(df, signals)
        >>> # ... симуляция ...
        >>> final_trade = lifecycle.finalize(state, cached, position_manager, trades, start_time, total_candles)
    """

    def __init__(
        self,
        config: BacktestConfig,
        ticker: str,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует управление жизненным циклом.

        Args:
            config: Конфигурация бэктеста.
            ticker: Символ инструмента.
            correlation_id: ID корреляции для логирования.
        """
        self.config = config
        self.ticker = ticker
        self.correlation_id = correlation_id

    def initialize(
        self, df: pd.DataFrame, signals: SignalsBatch
    ) -> tuple[TradingState, CachedData]:
        """
        Инициализирует состояние и данные для симуляции.

        Args:
            df: DataFrame с историческими данными.
            signals: Пакет предрассчитанных сигналов.

        Returns:
            Tuple (state, cached):
                - state: Инициализированное состояние торговли
                - cached: Кэшированные numpy массивы
        """
        state = TradingState(current_capital=self.config.initial_balance)
        cached = DataCacheManager.cache_data_arrays(df, signals)
        return state, cached

    def finalize(
        self,
        state: TradingState,
        cached: CachedData,
        position_manager: PositionManager,
        trades: list[BacktestTrade],
        total_elapsed: float,
        total_candles: int,
    ) -> BacktestTrade | None:
        """
        Финализирует симуляцию: закрывает последнюю позицию и логирует итоги.

        Args:
            state: Финальное состояние торговли.
            cached: Кэшированные данные.
            position_manager: Менеджер позиций для закрытия последней позиции.
            trades: Список всех завершенных сделок.
            total_elapsed: Общее время выполнения симуляции (секунды).
            total_candles: Общее количество обработанных свечей.

        Returns:
            Финальная сделка если позиция была открыта, иначе None.
        """
        # Закрываем последнюю позицию если открыта
        final_trade = position_manager.close_final_position(state, cached)

        # Финальное логирование
        logger.info(
            "simulation_lifecycle.simulation_completed",
            total_candles=total_candles,
            total_trades=len(trades),
            final_capital=round(state.current_capital, 2),
            elapsed_seconds=round(total_elapsed, 2),
            candles_per_second=(
                round(total_candles / total_elapsed, 0)
                if total_elapsed > 0
                else 0
            ),
            ticker=self.ticker,
            correlation_id=self.correlation_id,
        )

        return final_trade
