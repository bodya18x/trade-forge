"""Kafka Consumers для Trading Engine."""

from __future__ import annotations

from consumers.backtest_consumer import BacktestConsumer
from consumers.rt_consumer import RTConsumer

__all__ = [
    "BacktestConsumer",
    "RTConsumer",
]
