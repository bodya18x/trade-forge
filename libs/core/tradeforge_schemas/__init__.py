"""
TradeForge Schemas - Единые Pydantic схемы для всех сервисов Trade Forge.

Этот пакет содержит унифицированные схемы данных для обеспечения консистентности
контрактов между всеми микросервисами платформы.

Основные модули:
- base: Базовые схемы (пагинация, ошибки, успешные ответы)
- strategies: Схемы для работы со стратегиями и их валидацией
- backtests: Схемы для бэктестирования
- batch_backtests: Схемы для групповых бэктестов
- metadata: Схемы для метаданных (индикаторы, тикеры, рынки)
- auth: Схемы аутентификации и пользователей
"""

from .backtests import (
    BacktestCreateRequest,
    BacktestFullResponse,
    BacktestJobInfo,
    BacktestResults,
    BacktestSortBy,
    BacktestSummary,
    JobStatusEnum,
    SimulationParameters,
)
from .base import (
    ErrorResponse,
    PaginatedResponse,
    SortDirection,
    SuccessResponse,
    ValidationErrorDetail,
)
from .batch_backtests import (
    BatchBacktestCreateRequest,
    BatchBacktestFilters,
    BatchBacktestJobInfo,
    BatchBacktestResponse,
    BatchBacktestSummary,
    BatchSortBy,
    BatchStatusEnum,
)
from .metadata import (
    IndicatorResponse,
    MarketResponse,
    SystemStatusResponse,
    TickerResponse,
    TimeframeInfo,
)
from .strategies import (
    LastBacktestInfo,
    StrategyCreateRequest,
    StrategyDefinition,
    StrategyResponse,
    StrategySortBy,
    StrategySummary,
    StrategyUpdateRequest,
    StrategyValidationRequest,
    StrategyValidationResponse,
)

__all__ = [
    # Backtest schemas
    "BacktestCreateRequest",
    "BacktestFullResponse",
    "BacktestJobInfo",
    "BacktestResults",
    "BacktestSortBy",
    "BacktestSummary",
    "JobStatusEnum",
    "SimulationParameters",
    # Batch backtest schemas
    "BatchBacktestCreateRequest",
    "BatchBacktestFilters",
    "BatchBacktestJobInfo",
    "BatchBacktestResponse",
    "BatchBacktestSummary",
    "BatchSortBy",
    "BatchStatusEnum",
    # Base schemas
    "ErrorResponse",
    "PaginatedResponse",
    "SortDirection",
    "SuccessResponse",
    "ValidationErrorDetail",
    # Metadata schemas
    "IndicatorResponse",
    "MarketResponse",
    "SystemStatusResponse",
    "TickerResponse",
    "TimeframeInfo",
    # Strategy schemas
    "LastBacktestInfo",
    "StrategyCreateRequest",
    "StrategyDefinition",
    "StrategyResponse",
    "StrategySortBy",
    "StrategySummary",
    "StrategyUpdateRequest",
    "StrategyValidationRequest",
    "StrategyValidationResponse",
]
