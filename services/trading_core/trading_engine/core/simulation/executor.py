"""
Backtest Executor - координатор процесса бэктестирования.

Гибридный векторизованный движок:
1. Векторизованный расчет всех сигналов (один проход)
2. Пошаговая симуляция торговли с использованием предрассчитанных сигналов

Основной координатор, который делегирует специфичную логику специализированным модулям:
- SignalCalculator: Расчет торговых сигналов
- PositionManager: Управление позициями
- ExitChecker: Проверка условий выхода
- DataCacheManager: Кэширование numpy массивов
- TradeBuilder: Построение объектов сделок
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from tradeforge_logger import get_logger

from core.common import ConfigurationError, InsufficientDataError
from core.simulation.data_cache import CachedData
from core.simulation.exit_checker import ExitChecker, TradingState
from core.simulation.metrics import calculate_metrics
from core.simulation.position_manager import PositionManager
from core.simulation.progress_tracker import ProgressTracker
from core.simulation.signal_calculator import SignalCalculator, SignalsBatch
from core.simulation.simulation_lifecycle import SimulationLifecycle
from core.simulation.trade_builder import TradeBuilder
from models.backtest import BacktestConfig, BacktestTrade
from models.strategy import StrategyDefinition

logger = get_logger(__name__)


class BacktestExecutor:
    """
    Координатор процесса бэктестирования.

    Управляет полным жизненным циклом бэктеста:
    1. Валидация стратегии и данных
    2. Расчет сигналов (делегирует SignalCalculator)
    3. Симуляция торговли (использует PositionManager + ExitChecker)
    4. Расчет метрик

    Attributes:
        df: DataFrame с историческими данными.
        strategy: Определение торговой стратегии.
        config: Конфигурация параметров бэктеста.
        lot_size: Размер лота инструмента.
        correlation_id: ID корреляции для трейсинга.
        signal_calculator: Калькулятор торговых сигналов.
        position_manager: Менеджер позиций.
        exit_checker: Проверщик условий выхода.
        trade_builder: Builder для создания сделок.
        trades: Список завершенных сделок.
        metrics: Рассчитанные метрики эффективности.
        ticker: Символ инструмента.

    Examples:
        >>> executor = BacktestExecutor(
        ...     df=historical_data,
        ...     strategy=strategy_definition,
        ...     lot_size=10,
        ...     correlation_id="test-123"
        ... )
        >>> trades = executor.run()
        >>> metrics, _ = executor.get_results()
        >>> print(f"Total trades: {metrics['total_trades']}")
    """

    def __init__(
        self,
        df: pd.DataFrame,
        strategy: StrategyDefinition,
        config: BacktestConfig | None = None,
        lot_size: int = 1,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует движок бэктестирования.

        Args:
            df: DataFrame с OHLCV данными и индикаторами.
            strategy: Определение торговой стратегии.
            config: Конфигурация бэктеста (initial_balance, commission, etc).
            lot_size: Размер лота инструмента.
            correlation_id: ID корреляции для логирования.

        Raises:
            InsufficientDataError: Если DataFrame пустой.
            ConfigurationError: Если lot_size <= 0.
        """
        if df.empty:
            raise InsufficientDataError(
                "DataFrame для бэктеста не может быть пустым."
            )

        if lot_size <= 0:
            raise ConfigurationError(
                f"lot_size должен быть положительным, получено: {lot_size}"
            )

        self.df = df.copy()
        self.strategy = strategy
        self.config = config or BacktestConfig()
        self.lot_size = lot_size
        self.correlation_id = correlation_id

        # Извлекаем ticker из DataFrame
        self.ticker = self._extract_ticker()

        # Инициализируем специализированные компоненты
        self.signal_calculator = SignalCalculator(strategy, correlation_id)
        self.trade_builder = TradeBuilder(
            config=self.config,
            lot_size=lot_size,
            df=self.df,
            correlation_id=correlation_id,
        )
        self.position_manager = PositionManager(
            trade_builder=self.trade_builder,
            strategy_definition=strategy,
            correlation_id=correlation_id,
        )
        self.exit_checker = ExitChecker(correlation_id=correlation_id)
        self.lifecycle = SimulationLifecycle(
            config=self.config,
            ticker=self.ticker,
            correlation_id=correlation_id,
        )

        # Результаты
        self.trades: list[BacktestTrade] = []
        self.metrics: dict[str, Any] = {}

    def _extract_ticker(self) -> str:
        """
        Извлекает ticker из DataFrame.

        Returns:
            Символ инструмента или "UNKNOWN".
        """
        if "ticker" in self.df.columns and not self.df.empty:
            return str(self.df["ticker"].iloc[0])
        return "UNKNOWN"

    def run(self) -> list[BacktestTrade]:
        """
        Запускает бэктест и возвращает список сделок.

        Координатор процесса бэктестирования. Метод разбит на этапы:
        1. Валидация стратегии и данных
        2. Векторизованный расчет сигналов
        3. Логирование статистики сигналов
        4. Пошаговая симуляция

        Returns:
            Список завершенных сделок (BacktestTrade).

        Examples:
            >>> executor = BacktestExecutor(...)
            >>> trades = executor.run()
            >>> print(f"Total trades: {len(trades)}")
            Total trades: 42
        """
        logger.info(
            "executor.backtest_started",
            ticker=self.ticker,
            lot_size=self.lot_size,
            initial_balance=self.config.initial_balance,
            commission_rate=self.config.commission_rate,
            position_size_multiplier=self.config.position_size_multiplier,
            correlation_id=self.correlation_id,
        )

        # 1. Валидация
        self._validate_strategy_and_data()

        # 2. Расчет сигналов (делегируем SignalCalculator)
        signals = self.signal_calculator.calculate_all_signals(self.df)

        # 3. Логирование статистики
        self.signal_calculator.log_signals_summary(signals, self.df.index)

        # 4. Симуляция
        self._simulate_trades(signals)

        logger.info(
            "executor.backtest_completed",
            ticker=self.ticker,
            trades_count=len(self.trades),
            correlation_id=self.correlation_id,
        )

        return self.trades

    def _validate_strategy_and_data(self) -> None:
        """
        Валидирует стратегию и DataFrame.

        Логирует INFO информацию о стратегии и данных для мониторинга.
        """
        logger.info(
            "executor.strategy_validation",
            has_entry_buy=self.strategy.entry_buy_conditions is not None,
            has_entry_sell=self.strategy.entry_sell_conditions is not None,
            has_exit=self.strategy.exit_conditions is not None,
            has_exit_long=self.strategy.exit_long_conditions is not None,
            has_exit_short=self.strategy.exit_short_conditions is not None,
            has_stop_loss=self.strategy.stop_loss is not None,
            stop_loss_type=(
                self.strategy.stop_loss.type
                if self.strategy.stop_loss
                else None
            ),
            correlation_id=self.correlation_id,
        )

        # Валидация DataFrame
        required_cols = ["open", "high", "low", "close", "volume"]
        has_ohlcv = all(col in self.df.columns for col in required_cols)

        # Проверка на NaN в критичных OHLCV колонках
        if has_ohlcv:
            for col in required_cols:
                nan_count = self.df[col].isna().sum()
                if nan_count > 0:
                    logger.error(
                        "executor.nan_values_detected",
                        column=col,
                        nan_count=nan_count,
                        total_rows=len(self.df),
                        correlation_id=self.correlation_id,
                    )
                    raise InsufficientDataError(
                        f"Critical OHLCV column '{col}' contains {nan_count} NaN values. "
                        f"Cannot execute backtest with incomplete price data."
                    )

        logger.info(
            "executor.dataframe_validation",
            shape=self.df.shape,
            columns_count=len(self.df.columns),
            has_ohlcv=has_ohlcv,
            missing_ohlcv=[
                col for col in required_cols if col not in self.df.columns
            ],
            first_timestamp=(
                str(self.df.index[0]) if len(self.df) > 0 else None
            ),
            last_timestamp=(
                str(self.df.index[-1]) if len(self.df) > 0 else None
            ),
            correlation_id=self.correlation_id,
        )

    def _simulate_trades(self, signals: SignalsBatch) -> None:
        """
        Координатор пошаговой симуляции торговли.

        Главный цикл симуляции, делегирующий специфичную логику специализированным классам:
        - SimulationLifecycle: Инициализация и финализация
        - ProgressTracker: Timeout protection и progress logging
        - Обработка каждой свечи

        Args:
            signals: Пакет предрассчитанных сигналов.

        Raises:
            BacktestExecutionError: При превышении timeout симуляции.
        """
        # Инициализация через lifecycle
        state, cached = self.lifecycle.initialize(self.df, signals)
        total_candles = len(self.df)

        # Инициализация progress tracker
        tracker = ProgressTracker(
            ticker=self.ticker, correlation_id=self.correlation_id
        )

        # Основной цикл симуляции (пропускаем первую свечу i=0)
        for i in range(1, total_candles):
            # Timeout protection
            tracker.check_timeout(i, total_candles, len(self.trades))

            # Progress logging
            tracker.log_progress_if_needed(
                i, total_candles, state, len(self.trades)
            )

            # Обработка свечи
            self._process_candle(state, cached, i)

        # Финализация через lifecycle
        final_trade = self.lifecycle.finalize(
            state,
            cached,
            self.position_manager,
            self.trades,
            tracker.get_total_elapsed(),
            total_candles,
        )
        if final_trade:
            self.trades.append(final_trade)

    def _process_candle(
        self, state: TradingState, cached: CachedData, i: int
    ) -> None:
        """
        Обрабатывает одну свечу: проверка выхода и входа.

        ВАЖНО: Используем два отдельных if (НЕ if-else!) для поддержки ФЛИПОВ.
        Флип = закрытие позиции и немедленное открытие противоположной НА ТОЙ ЖЕ СВЕЧЕ.

        Логика:
        1. Если есть позиция → проверяем выход (может закрыть, state.has_position() станет False)
        2. Если нет позиции → проверяем вход (может открыть новую, даже после закрытия на шаге 1)

        Args:
            state: Текущее состояние торговли.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.
        """
        # БЛОК 1: Обработка открытой позиции (может закрыть)
        if state.has_position():
            self._process_open_position(state, cached, i)

        # БЛОК 2: Проверка входа в новую позицию (даже если закрыли в блоке 1!)
        if not state.has_position():
            self._process_entry_signal(state, cached, i)

    def _process_open_position(
        self, state: TradingState, cached: CachedData, i: int
    ) -> None:
        """
        Обрабатывает открытую позицию: обновление SL и проверка выхода.

        Args:
            state: Текущее состояние торговли.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.
        """
        # Обновляем trailing stop loss
        self.position_manager.update_trailing_stop_loss(state, cached, i)

        # Проверяем условия выхода
        exit_info = self.exit_checker.check_exit_conditions(state, cached, i)

        if exit_info:
            # Проверяем флип
            exit_info.is_flip = self.exit_checker.check_flip(state, cached, i)

            # Закрываем позицию
            trade = self.position_manager.close_position(
                state, exit_info, cached, i
            )
            self.trades.append(trade)

    def _process_entry_signal(
        self, state: TradingState, cached: CachedData, i: int
    ) -> None:
        """
        Проверяет условия входа и открывает позицию если есть сигнал.

        Args:
            state: Текущее состояние торговли.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.
        """
        entry_info = self.position_manager.check_entry_conditions(cached, i)

        if entry_info:
            self.position_manager.open_position(state, entry_info, cached, i)

    def get_results(self) -> tuple[dict[str, Any], list[BacktestTrade]]:
        """
        Возвращает рассчитанные метрики и список сделок.

        Returns:
            Tuple (metrics, trades):
                - metrics: Словарь с метриками эффективности
                - trades: Список завершенных сделок

        Examples:
            >>> metrics, trades = executor.get_results()
            >>> print(f"ROI: {metrics['net_total_profit_pct']:.2f}%")
            ROI: 15.23%
        """
        if not self.metrics:
            self._calculate_and_log_metrics()
        return self.metrics, self.trades

    def _calculate_and_log_metrics(self) -> None:
        """
        Рассчитывает и логирует метрики эффективности.

        Использует функцию calculate_metrics из модуля metrics.
        """
        self.metrics = calculate_metrics(self.trades, self.config)

        logger.info(
            "executor.metrics_calculated",
            ticker=self.ticker,
            initial_balance=self.metrics.get("initial_balance"),
            gross_final_balance=self.metrics.get("gross_final_balance"),
            gross_total_profit_pct=self.metrics.get("gross_total_profit_pct"),
            net_final_balance=self.metrics.get("net_final_balance"),
            net_total_profit_pct=self.metrics.get("net_total_profit_pct"),
            total_trades=self.metrics.get("total_trades"),
            wins=self.metrics.get("wins"),
            losses=self.metrics.get("losses"),
            win_rate=self.metrics.get("win_rate"),
            profit_factor=self.metrics.get("profit_factor"),
            max_drawdown_pct=self.metrics.get("max_drawdown_pct"),
            sharpe_ratio=self.metrics.get("sharpe_ratio"),
            stability_score=self.metrics.get("stability_score"),
            correlation_id=self.correlation_id,
        )
