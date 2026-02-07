"""
Strategy Evaluators Module.

Модульная система оценки торговых стратегий (AST).

Разбита на специализированные evaluator'ы по типам узлов:
- logical: AND, OR
- comparison: GREATER_THAN, LESS_THAN, EQUALS
- crossover: CROSSOVER_UP, CROSSOVER_DOWN
- special: SUPER_TREND_FLIP, MACD_CROSSOVER_FLIP

Главный класс:
- StrategyEvaluator: Координатор, делегирующий оценку специализированным функциям
"""

from __future__ import annotations

from .base import StrategyEvaluator

__all__ = [
    "StrategyEvaluator",
]
