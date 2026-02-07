"""
Ядро Trading Engine.

Содержит всю бизнес-логику для:
- Анализа и оценки торговых стратегий
- Симуляции бэктестов
- Работы с данными и индикаторами
- Оркестрации процесса обработки

Структура:
- common/: Общие компоненты (константы, исключения, утилиты)
- strategy/: Работа со стратегиями (evaluator, analyzer)
- simulation/: Симуляция бэктеста (executor, trade_builder, metrics)
- data/: Работа с данными (preparer, indicator_resolver)
- orchestration/: Оркестрация процесса (orchestrator)
"""

from __future__ import annotations

# Common
from .common import (
    BACKTEST_TIMEOUT_SECONDS,
    CLICKHOUSE_QUERY_TIMEOUT_SECONDS,
    CONSECUTIVE_LOSSES_PENALTY_FACTOR,
    EPSILON,
    MAX_CANDLES_PER_BACKTEST,
    MAX_DRAWDOWN_DEFAULT,
    MAX_PROFIT_FACTOR_CAP,
    MAX_PROFIT_STD_DEV_DEFAULT,
    MAX_STABILITY_SCORE,
    MIN_TRADES_FOR_STABILITY_SCORE,
    OHLCV_COLUMNS,
    STABILITY_WEIGHT_AVG_PROFIT_CONSISTENCY,
    STABILITY_WEIGHT_MAX_CONSECUTIVE_LOSSES,
    STABILITY_WEIGHT_MAX_DRAWDOWN,
    STABILITY_WEIGHT_PROFIT_FACTOR,
    STABILITY_WEIGHT_WIN_RATE,
    STABILITY_WEIGHTS,
    TRADE_COUNT_CONFIDENCE_FACTOR,
    BacktestExecutionError,
    ConfigurationError,
    DataNotFoundError,
    ExitReason,
    IndicatorCalculationError,
    InsufficientDataError,
    InvalidStrategyError,
    JobStatus,
    PositionType,
    StabilityWeights,
    TradingEngineError,
    sanitize_json,
)

# Data
from .data import IndicatorResolver, prepare_dataframe

# Orchestration
from .orchestration import BacktestOrchestrator

# Simulation
from .simulation import BacktestExecutor, TradeBuilder, calculate_metrics

# Strategy
from .strategy import StrategyAnalyzer, StrategyEvaluator

__all__ = [
    # Common - Constants
    "BACKTEST_TIMEOUT_SECONDS",
    "CLICKHOUSE_QUERY_TIMEOUT_SECONDS",
    "CONSECUTIVE_LOSSES_PENALTY_FACTOR",
    "EPSILON",
    "ExitReason",
    "JobStatus",
    "MAX_CANDLES_PER_BACKTEST",
    "MAX_DRAWDOWN_DEFAULT",
    "MAX_PROFIT_FACTOR_CAP",
    "MAX_PROFIT_STD_DEV_DEFAULT",
    "MAX_STABILITY_SCORE",
    "MIN_TRADES_FOR_STABILITY_SCORE",
    "OHLCV_COLUMNS",
    "PositionType",
    "STABILITY_WEIGHT_AVG_PROFIT_CONSISTENCY",
    "STABILITY_WEIGHT_MAX_CONSECUTIVE_LOSSES",
    "STABILITY_WEIGHT_MAX_DRAWDOWN",
    "STABILITY_WEIGHT_PROFIT_FACTOR",
    "STABILITY_WEIGHT_WIN_RATE",
    "STABILITY_WEIGHTS",
    "StabilityWeights",
    "TRADE_COUNT_CONFIDENCE_FACTOR",
    # Common - Exceptions
    "BacktestExecutionError",
    "ConfigurationError",
    "DataNotFoundError",
    "IndicatorCalculationError",
    "InsufficientDataError",
    "InvalidStrategyError",
    "TradingEngineError",
    # Common - Utils
    "sanitize_json",
    # Data
    "IndicatorResolver",
    "prepare_dataframe",
    # Orchestration
    "BacktestOrchestrator",
    # Simulation
    "BacktestExecutor",
    "TradeBuilder",
    "calculate_metrics",
    # Strategy
    "StrategyAnalyzer",
    "StrategyEvaluator",
]
