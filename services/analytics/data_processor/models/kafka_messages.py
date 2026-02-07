"""
Pydantic схемы для Kafka сообщений Data Processor сервиса.

Определяет структуру входящих и исходящих сообщений.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawCandleMessage(BaseModel):
    """
    Сообщение с сырой свечой из топика trade-forge.marketdata.candles.raw.v1.

    Attributes:
        ticker: Тикер инструмента
        timeframe: Таймфрейм (1m, 5m, 1h и т.д.)
        open: Цена открытия
        high: Максимальная цена
        low: Минимальная цена
        close: Цена закрытия
        volume: Объем торгов
        value: Стоимость торгов (опционально)
        begin: Время начала свечи
        end: Время окончания свечи
    """

    ticker: str = Field(..., description="Тикер инструмента")
    timeframe: str = Field(..., description="Таймфрейм свечи")
    open: float = Field(..., description="Цена открытия", gt=0)
    high: float = Field(..., description="Максимальная цена", gt=0)
    low: float = Field(..., description="Минимальная цена", gt=0)
    close: float = Field(..., description="Цена закрытия", gt=0)
    volume: float = Field(..., description="Объем торгов", ge=0)
    value: float | None = Field(None, description="Стоимость торгов", ge=0)
    begin: datetime = Field(..., description="Время начала свечи")
    # end: datetime = Field(..., description="Время окончания свечи")


class ProcessedCandleMessage(BaseModel):
    """
    Сообщение с обработанной свечой (OHLCV + индикаторы).

    Отправляется в топик trade-forge.indicators.candles.processed.rt.v1.

    Attributes:
        ticker: Тикер инструмента
        timeframe: Таймфрейм
        open: Цена открытия
        high: Максимальная цена
        low: Минимальная цена
        close: Цена закрытия
        volume: Объем торгов
        value: Стоимость торгов (опционально)
        begin: Время начала свечи
        end: Время окончания свечи
        indicators: Динамические значения индикаторов (ключ -> значение)
    """

    ticker: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    value: float | None = None
    begin: str  # ISO format datetime string
    end: str  # ISO format datetime string
    # Все остальные поля - это индикаторы (динамические)

    class Config:
        extra = "allow"  # Разрешаем дополнительные поля (индикаторы)


class IndicatorDefinition(BaseModel):
    """
    Определение индикатора для расчета.

    Attributes:
        indicator_key: Уникальный ключ индикатора
        indicator_name: Название индикатора
        library: Библиотека расчета (talib, pandas_ta, custom)
        params: Параметры индикатора
    """

    indicator_key: str = Field(..., description="Уникальный ключ индикатора")
    indicator_name: str = Field(..., description="Название индикатора")
    library: str = Field(
        ..., description="Библиотека расчета (talib, pandas_ta, custom)"
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="Параметры индикатора"
    )


class BatchCalculationRequestMessage(BaseModel):
    """
    Запрос на batch-расчет индикаторов.

    Получается из топика trade-forge.backtesting.indicators.calculation-requested.v1.

    Attributes:
        job_id: Уникальный ID задачи
        ticker: Тикер инструмента
        timeframe: Таймфрейм
        start_date: Начальная дата периода
        end_date: Конечная дата периода
        indicators: Список определений индикаторов для расчета
    """

    job_id: str = Field(..., description="Уникальный ID задачи")
    ticker: str = Field(..., description="Тикер инструмента")
    timeframe: str = Field(..., description="Таймфрейм")
    start_date: str = Field(..., description="Начальная дата (ISO format)")
    end_date: str = Field(..., description="Конечная дата (ISO format)")
    indicators: list[dict[str, Any]] = Field(
        ..., description="Список определений индикаторов"
    )


class BatchCalculationResponseMessage(BaseModel):
    """
    Ответ после batch-расчета индикаторов.

    Отправляется в топик trade-forge.backtests.requests.v1.

    Attributes:
        job_id: ID обработанной задачи
        status: Статус выполнения (CALCULATION_SUCCESS | CALCULATION_FAILURE)
        error: Описание ошибки (если status = FAILURE)
    """

    job_id: str = Field(..., description="ID обработанной задачи")
    status: str = Field(
        ..., description="Статус (CALCULATION_SUCCESS | CALCULATION_FAILURE)"
    )
    error: str | None = Field(None, description="Описание ошибки")
