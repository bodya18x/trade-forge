"""
Общие типы для Internal API.

Определяет type aliases для часто используемых типов данных.
"""

from __future__ import annotations

from typing import TypeAlias
from uuid import UUID

# UUID типы для бизнес-сущностей
CorrelationID: TypeAlias = str
UserID: TypeAlias = UUID
StrategyID: TypeAlias = UUID
BacktestJobID: TypeAlias = UUID
BatchID: TypeAlias = UUID
IndicatorID: TypeAlias = UUID

# Типы для идентификации данных
Ticker: TypeAlias = str
Timeframe: TypeAlias = str
IndicatorKey: TypeAlias = str

# Типы для Redis ключей
RedisKey: TypeAlias = str
IdempotencyKey: TypeAlias = str
