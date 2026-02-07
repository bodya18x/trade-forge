"""
Модуль для симуляции бэктестов.

Содержит компоненты для выполнения симуляции торговли:
- BacktestExecutor: Основной движок бэктестирования
- TradeBuilder: Построение объектов BacktestTrade с расчетами
- calculate_metrics: Расчет метрик производительности стратегии
"""

from __future__ import annotations

from .executor import BacktestExecutor
from .metrics import calculate_metrics
from .trade_builder import TradeBuilder

__all__ = [
    "BacktestExecutor",
    "TradeBuilder",
    "calculate_metrics",
]
