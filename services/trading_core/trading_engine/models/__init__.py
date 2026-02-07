"""Модели данных для Trading Engine."""

from __future__ import annotations

# AST node models
from models.ast_nodes import (
    AnyConditionNode,
    ComparisonNode,
    ConditionNode,
    CrossoverNode,
    IndicatorValueNode,
    LogicalNode,
    PrevIndicatorValueNode,
    ResolvableValue,
    SpecialConditionNode,
    ValueNode,
)

# Backtest models
from models.backtest import BacktestConfig, BacktestTrade

# Kafka message schemas
from models.kafka_messages import (
    BacktestRequestMessage,
    FatCandleMessage,
    IndicatorCalculationRequestMessage,
    TradeOrderMessage,
)

# Repository models
from models.repository import BacktestJobDetails, TickerInfo

# Strategy models
from models.strategy import (
    StopLossConfig,
    StrategyDefinition,
    StrategyModel,
    TakeProfitConfig,
)

__all__ = [
    # Backtest models
    "BacktestConfig",
    "BacktestTrade",
    # Repository models
    "BacktestJobDetails",
    "TickerInfo",
    # Strategy models
    "StopLossConfig",
    "TakeProfitConfig",
    "StrategyDefinition",
    "StrategyModel",
    # Kafka message schemas
    "BacktestRequestMessage",
    "IndicatorCalculationRequestMessage",
    "FatCandleMessage",
    "TradeOrderMessage",
    # AST node models
    "ValueNode",
    "IndicatorValueNode",
    "PrevIndicatorValueNode",
    "ResolvableValue",
    "ComparisonNode",
    "CrossoverNode",
    "SpecialConditionNode",
    "ConditionNode",
    "LogicalNode",
    "AnyConditionNode",
]
