"""
Унифицированные Pydantic схемы для метаданных системы.

Содержит схемы для индикаторов, тикеров, рынков и системной информации.
Объединяет лучшие практики из Gateway и Internal API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from pydantic import BaseModel, Field

# === ИНДИКАТОРЫ ===


class IndicatorResponse(BaseModel):
    """
    Унифицированная информация о техническом индикаторе.

    Объединяет подходы из Gateway и Internal API.
    """

    name: str = Field(
        ..., description="Код индикатора (например, 'macd', 'rsi')"
    )
    display_name: str = Field(
        ..., description="Человекочитаемое название индикатора"
    )
    description: str = Field(..., description="Описание индикатора")
    category: str = Field(
        ...,
        description="Категория индикатора (momentum, trend, volume, volatility)",
    )
    complexity: str = Field(
        ..., description="Сложность индикатора (basic, intermediate, advanced)"
    )
    parameters_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema для параметров индикатора"
    )
    output_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema для выходных значений"
    )
    key_template: str = Field(
        ..., description="Шаблон для генерации ключей индикатора"
    )
    is_enabled: bool = Field(
        ..., description="Включен ли индикатор для использования"
    )

    model_config = {"from_attributes": True}


# === РЫНКИ ===


class MarketResponse(BaseModel):
    """Краткая информация о торговой площадке."""

    market_code: str = Field(..., description="Код рынка")
    description: str = Field(..., description="Описание рынка")

    model_config = {"from_attributes": True}


class MarketFullResponse(BaseModel):
    """Полная информация о торговой площадке."""

    id: uuid.UUID = Field(..., description="Уникальный идентификатор рынка")
    market_code: str = Field(..., description="Код рынка")
    name: str = Field(..., description="Название рынка")
    description: str = Field(..., description="Описание рынка")
    timezone: str = Field(..., description="Часовой пояс рынка")
    trading_hours: str = Field(..., description="Часы торгов")
    is_active: bool = Field(..., description="Активен ли рынок")
    created_at: datetime = Field(..., description="Время создания")

    model_config = {"from_attributes": True}


# === ТИКЕРЫ ===


class TickerResponse(BaseModel):
    """Краткая информация о торговом инструменте."""

    symbol: str = Field(..., description="Символ тикера")
    market_id: int = Field(..., description="ID рынка")
    description: str = Field(..., description="Описание инструмента")
    type: str = Field(
        ..., description="Тип инструмента (stock, currency, future)"
    )
    is_active: bool = Field(..., description="Доступен ли для торговли")
    lot_size: int = Field(..., description="Размер лота", ge=1)
    min_step: Decimal = Field(..., description="Минимальный шаг цены", ge=0)
    decimals: int = Field(
        ..., description="Количество знаков после запятой", ge=0
    )
    isin: str | None = Field(
        None, description="Международный идентификационный код"
    )
    currency: str = Field(..., description="Валюта торгов")

    model_config = {"from_attributes": True}


class TickerFullResponse(BaseModel):
    """Полная информация о торговом инструменте."""

    id: uuid.UUID = Field(..., description="Уникальный идентификатор тикера")
    symbol: str = Field(..., description="Символ тикера")
    name: str = Field(..., description="Полное название инструмента")
    description: str = Field(..., description="Описание инструмента")
    market_id: uuid.UUID = Field(..., description="ID рынка")
    market_code: str = Field(..., description="Код рынка")
    instrument_type: str = Field(
        ..., description="Тип инструмента (stock, currency, future)"
    )
    lot_size: int = Field(..., description="Размер лота", ge=1)
    min_step: Decimal = Field(..., description="Минимальный шаг цены", ge=0)
    decimals: int = Field(
        ..., description="Количество знаков после запятой", ge=0
    )
    currency: str = Field(..., description="Валюта торгов")
    isin: str | None = Field(
        None, description="Международный идентификационный код"
    )
    is_active: bool = Field(..., description="Доступен ли для торговли")
    created_at: datetime = Field(..., description="Время создания")

    model_config = {"from_attributes": True}


# === ТАЙМФРЕЙМЫ ===


class TimeframeInfo(BaseModel):
    """Информация о доступном таймфрейме."""

    code: str = Field(..., description="Код таймфрейма (1m, 5m, 1h, 1d)")
    name: str = Field(..., description="Человекочитаемое название")
    duration_minutes: int = Field(..., description="Длительность в минутах")
    is_supported: bool = Field(..., description="Поддерживается ли системой")


# === СИСТЕМНАЯ ИНФОРМАЦИЯ ===


class SystemStatusResponse(BaseModel):
    """Статус системы и доступные возможности."""

    version: str = Field(..., description="Версия API")
    status: str = Field(
        ..., description="Статус системы (healthy, degraded, maintenance)"
    )
    features: Dict[str, bool] = Field(..., description="Доступные функции")
    supported_timeframes: list[TimeframeInfo] = Field(
        ..., description="Поддерживаемые таймфреймы"
    )
    rate_limits: Dict[str, int] = Field(..., description="Лимиты запросов")
    maintenance_window: str | None = Field(
        None, description="Окно технических работ"
    )
