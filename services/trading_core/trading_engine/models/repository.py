"""
Pydantic модели для данных репозиториев.

Типизированные модели для данных, возвращаемых из PostgreSQL и ClickHouse.
Заменяют слабо типизированные dict[str, Any] на строго типизированные модели.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.backtest import BacktestConfig
from models.strategy import StrategyDefinition


class BacktestJobDetails(BaseModel):
    """
    Детали задачи на бэктест из PostgreSQL.

    Объединяет информацию из таблиц BacktestJobs и Strategies
    для полного описания задачи на бэктест.

    Attributes:
        job_id: UUID задачи на бэктест.
        user_id: UUID пользователя.
        ticker: Символ инструмента (например, "SBER").
        timeframe: Таймфрейм свечей (например, "1h", "1d").
        start_date: Дата начала периода бэктеста.
        end_date: Дата окончания периода бэктеста.
        status: Текущий статус задачи.
        simulation_params: Параметры симуляции (initial_balance, etc.).
        strategy_id: UUID стратегии.
        strategy_name: Название стратегии.
        strategy_definition: Определение стратегии (entry/exit условия).
    """

    model_config = ConfigDict(
        from_attributes=True, arbitrary_types_allowed=True
    )

    job_id: uuid.UUID = Field(..., description="UUID задачи на бэктест")
    user_id: uuid.UUID = Field(..., description="UUID пользователя")
    ticker: str = Field(..., description="Символ инструмента")
    timeframe: str = Field(..., description="Таймфрейм свечей")
    start_date: datetime = Field(..., description="Дата начала периода")
    end_date: datetime = Field(..., description="Дата окончания периода")
    status: str = Field(..., description="Статус задачи")
    simulation_params: dict[str, Any] = Field(
        default_factory=dict, description="Параметры симуляции"
    )
    strategy_id: uuid.UUID = Field(..., description="UUID стратегии")
    strategy_name: str = Field(..., description="Название стратегии")
    strategy_definition: dict[str, Any] = Field(
        ..., description="Определение стратегии"
    )


class TickerInfo(BaseModel):
    """
    Информация о тикере из PostgreSQL.

    Attributes:
        lot_size: Размер лота инструмента.
        min_step: Минимальный шаг цены.
        decimals: Количество знаков после запятой.
        currency: Валюта инструмента.
    """

    model_config = ConfigDict(from_attributes=True)

    lot_size: int = Field(..., description="Размер лота", gt=0)
    min_step: float = Field(..., description="Минимальный шаг цены", gt=0)
    decimals: int = Field(
        ..., description="Количество знаков после запятой", ge=0
    )
    currency: str = Field(..., description="Валюта инструмента")
