"""
Pydantic схемы для Kafka сообщений Trading Engine.

Определяет структуру входящих и исходящих сообщений для всех типов consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BacktestRequestMessage(BaseModel):
    """
    Сообщение, инициирующее задачу на бэктест.

    Приходит из Internal API, также используется для "круга почета" от Data Processor.

    Attributes:
        job_id: UUID задачи на бэктест
        status: Статус задачи (опционально, для круга почета)
    """

    job_id: uuid.UUID = Field(..., description="UUID задачи на бэктест")
    status: str | None = Field(None, description="Статус обработки")


class IndicatorCalculationRequestMessage(BaseModel):
    """
    Запрос на расчет индикаторов для бэктеста.

    Отправляется в Data Processor для batch-расчета недостающих индикаторов.

    Attributes:
        job_id: UUID задачи на бэктест (для correlation)
        ticker: Тикер инструмента
        timeframe: Таймфрейм
        start_date: Начальная дата периода (ISO format)
        end_date: Конечная дата периода (ISO format)
        indicators: Список определений индикаторов для расчета
    """

    job_id: str = Field(..., description="UUID задачи на бэктест")
    ticker: str = Field(..., description="Тикер инструмента")
    timeframe: str = Field(..., description="Таймфрейм")
    start_date: str = Field(..., description="Начальная дата (ISO format)")
    end_date: str = Field(..., description="Конечная дата (ISO format)")
    indicators: list[dict[str, Any]] = Field(
        ..., description="Список определений индикаторов"
    )


class FatCandleMessage(BaseModel):
    """
    "Жирная" свеча, приходящая от сервиса калькуляции для RT-обработки.
    Используем `extra='allow'` для гибкости, но основные поля валидируем.
    """

    model_config = ConfigDict(
        extra="allow"
    )  # Pydantic V2: Разрешаем дополнительные поля

    ticker: str
    timeframe: str
    begin: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TradeOrderMessage(BaseModel):
    """Торговый приказ, отправляемый из RT-процессора."""

    strategy_id: uuid.UUID
    ticker: str
    action: Literal["OPEN", "CLOSE", "UPDATE_SL"]
    side: Literal["BUY", "SELL"]
    price: float
    stop_loss: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
