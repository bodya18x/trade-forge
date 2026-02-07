"""
Общие компоненты для Trading Engine.

Содержит константы, исключения и утилиты общего назначения.
"""

from __future__ import annotations

from .constants import (
    BACKTEST_TIMEOUT_SECONDS,
    CLICKHOUSE_DUMMY_INDICATOR_KEY,
    CLICKHOUSE_DUMMY_INDICATOR_PAIR,
    CLICKHOUSE_DUMMY_VALUE_KEY,
    CLICKHOUSE_QUERY_TIMEOUT_SECONDS,
    CLICKHOUSE_TECHNICAL_COLUMNS,
    CONSECUTIVE_LOSSES_PENALTY_FACTOR,
    EPSILON,
    MAX_CANDLES_PER_BACKTEST,
    MAX_DRAWDOWN_DEFAULT,
    MAX_PROFIT_FACTOR_CAP,
    MAX_PROFIT_STD_DEV_DEFAULT,
    MAX_STABILITY_SCORE,
    MIN_TRADES_FOR_STABILITY_SCORE,
    OHLCV_COLUMNS,
    SIMULATION_PROGRESS_LOG_INTERVAL,
    SIMULATION_TIMEOUT_CHECK_INTERVAL,
    SIMULATION_TIMEOUT_SECONDS,
    SLOW_DATA_LOAD_THRESHOLD_MS,
    SLOW_QUERY_THRESHOLD_MS,
    STABILITY_WEIGHT_AVG_PROFIT_CONSISTENCY,
    STABILITY_WEIGHT_MAX_CONSECUTIVE_LOSSES,
    STABILITY_WEIGHT_MAX_DRAWDOWN,
    STABILITY_WEIGHT_PROFIT_FACTOR,
    STABILITY_WEIGHT_WIN_RATE,
    STABILITY_WEIGHTS,
    TRADE_COUNT_CONFIDENCE_FACTOR,
    ExitReason,
    JobStatus,
    PositionType,
    StabilityWeights,
)
from .exceptions import (
    BacktestExecutionError,
    ConfigurationError,
    DataNotFoundError,
    IndicatorCalculationError,
    InsufficientDataError,
    InvalidStrategyError,
    TradingEngineError,
)
from .utils import convert_to_moscow_tz, sanitize_json

__all__ = [
    # Constants
    "BACKTEST_TIMEOUT_SECONDS",
    "CLICKHOUSE_DUMMY_INDICATOR_KEY",
    "CLICKHOUSE_DUMMY_INDICATOR_PAIR",
    "CLICKHOUSE_DUMMY_VALUE_KEY",
    "CLICKHOUSE_QUERY_TIMEOUT_SECONDS",
    "CLICKHOUSE_TECHNICAL_COLUMNS",
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
    "SIMULATION_PROGRESS_LOG_INTERVAL",
    "SIMULATION_TIMEOUT_CHECK_INTERVAL",
    "SIMULATION_TIMEOUT_SECONDS",
    "SLOW_DATA_LOAD_THRESHOLD_MS",
    "SLOW_QUERY_THRESHOLD_MS",
    "STABILITY_WEIGHT_AVG_PROFIT_CONSISTENCY",
    "STABILITY_WEIGHT_MAX_CONSECUTIVE_LOSSES",
    "STABILITY_WEIGHT_MAX_DRAWDOWN",
    "STABILITY_WEIGHT_PROFIT_FACTOR",
    "STABILITY_WEIGHT_WIN_RATE",
    "STABILITY_WEIGHTS",
    "StabilityWeights",
    "TRADE_COUNT_CONFIDENCE_FACTOR",
    # Exceptions
    "BacktestExecutionError",
    "ConfigurationError",
    "DataNotFoundError",
    "IndicatorCalculationError",
    "InsufficientDataError",
    "InvalidStrategyError",
    "TradingEngineError",
    # Utils
    "convert_to_moscow_tz",
    "sanitize_json",
]
