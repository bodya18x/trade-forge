"""
PostgreSQL Repositories для Trading Engine.

Модульная структура репозиториев с разделением ответственности:
- BaseRepository: Общая логика (retry, подключение к БД)
- BacktestRepository: Задачи на бэктест и результаты
- TickerRepository: Информация о тикерах с TTL кэшем
- StrategyRepository: Стратегии для RT торговли
- IndicatorRepository: Реестр индикаторов
- BatchRepository: Пакеты бэктестов
"""

from __future__ import annotations

from .backtest_repository import BacktestRepository
from .base import BaseRepository
from .batch_repository import BatchRepository
from .indicator_repository import IndicatorRepository
from .strategy_repository import StrategyRepository
from .ticker_repository import TickerRepository

__all__ = [
    # Base
    "BaseRepository",
    # Specific repositories
    "BacktestRepository",
    "TickerRepository",
    "StrategyRepository",
    "IndicatorRepository",
    "BatchRepository",
]
