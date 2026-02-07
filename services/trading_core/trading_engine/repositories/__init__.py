"""Repositories для Trading Engine."""

from __future__ import annotations

from repositories.clickhouse import ClickHouseRepository
from repositories.postgres import (
    BacktestRepository,
    BaseRepository,
    BatchRepository,
    IndicatorRepository,
    StrategyRepository,
    TickerRepository,
)

__all__ = [
    # ClickHouse
    "ClickHouseRepository",
    # PostgreSQL - Modular Repositories
    "BaseRepository",
    "BacktestRepository",
    "TickerRepository",
    "StrategyRepository",
    "IndicatorRepository",
    "BatchRepository",
]
