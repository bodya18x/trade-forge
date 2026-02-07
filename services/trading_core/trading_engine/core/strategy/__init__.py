"""
Модуль для работы со стратегиями.

Содержит компоненты для анализа и оценки торговых стратегий:
- StrategyEvaluator: Векторизованная оценка условий стратегии на DataFrame
- StrategyAnalyzer: Извлечение требуемых индикаторов из AST стратегии
"""

from __future__ import annotations

from .analyzer import StrategyAnalyzer
from .evaluators import StrategyEvaluator

__all__ = [
    "StrategyAnalyzer",
    "StrategyEvaluator",
]
