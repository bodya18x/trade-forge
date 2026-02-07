"""
Схемы для работы с лимитами пользователей.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LimitInfo(BaseModel):
    """Информация о конкретном лимите."""

    limit: int = Field(..., description="Максимальное значение лимита")
    used: int = Field(..., description="Использовано на данный момент")
    remaining: int = Field(..., description="Осталось до достижения лимита")
    reset_time: datetime = Field(
        ..., description="Время сброса лимита (00:00 МСК следующего дня)"
    )


class UserLimitsResponse(BaseModel):
    """Ответ с текущими лимитами пользователя."""

    subscription_tier: str = Field(..., description="Текущий тарифный план")

    strategies_per_day: LimitInfo = Field(
        ..., description="Лимит создания стратегий в сутки"
    )
    backtests_per_day: LimitInfo = Field(
        ..., description="Лимит запуска бэктестов в сутки"
    )
    concurrent_backtests: LimitInfo = Field(
        ..., description="Лимит одновременных бэктестов"
    )
    backtest_max_years: LimitInfo = Field(
        ..., description="Максимальный период бэктеста в годах"
    )


class UserProfileResponse(BaseModel):
    """Расширенный ответ профиля пользователя с лимитами."""

    id: uuid.UUID = Field(..., description="ID пользователя")
    email: str = Field(..., description="Email пользователя")
    is_active: bool = Field(..., description="Активен ли пользователь")
    is_admin: bool = Field(..., description="Является ли администратором")
    subscription_tier: str = Field(..., description="Тарифный план")
    created_at: datetime = Field(..., description="Дата регистрации")
    updated_at: datetime = Field(..., description="Дата последнего обновления")

    limits: UserLimitsResponse = Field(
        ..., description="Текущие лимиты пользователя"
    )
