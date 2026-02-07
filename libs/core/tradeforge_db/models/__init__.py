"""
SQLAlchemy модели для Trade Forge PostgreSQL.

Этот модуль экспортирует все модели базы данных для использования в сервисах.
"""

from __future__ import annotations

from .auth import Users
from .backtest_results import BacktestResults
from .base import Base, TimestampTemplate
from .indicators import SystemIndicators, UsersIndicators
from .jobs import BacktestBatches, BacktestJobs, BatchStatus, JobStatus
from .markets import Markets
from .session_management import SecurityEvents, TokenBlacklist, UserSessions
from .strategies import Strategies
from .tickers import Tickers, TickerType

__all__ = [
    # Base classes
    "Base",
    "TimestampTemplate",
    # Auth domain
    "Users",
    "UserSessions",
    "TokenBlacklist",
    "SecurityEvents",
    # Trading domain
    "Strategies",
    "BacktestJobs",
    "BacktestBatches",
    "JobStatus",
    "BatchStatus",
    "BacktestResults",
    "SystemIndicators",
    "UsersIndicators",
    "Markets",
    "Tickers",
    "TickerType",
]
