"""
Pydantic схемы для работы с групповыми бэктестами (batch backtests).

Содержит все схемы для создания, управления и получения статусов групповых бэктестов.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .backtests import BacktestCreateRequest, JobStatusEnum

# === ПЕРЕЧИСЛЕНИЯ ===


class BatchStatusEnum(str, enum.Enum):
    """Статусы группового бэктеста."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"


class BatchSortBy(str, enum.Enum):
    """Доступные поля для сортировки групповых бэктестов."""

    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    STATUS = "status"
    TOTAL_COUNT = "total_count"
    COMPLETED_COUNT = "completed_count"
    FAILED_COUNT = "failed_count"
    PROGRESS_PERCENTAGE = "progress_percentage"


# === ЗАПРОСЫ НА СОЗДАНИЕ ===


class BatchBacktestCreateRequest(BaseModel):
    """
    Запрос на создание группового бэктеста.

    Содержит описание группы и список индивидуальных бэктестов для выполнения.
    """

    description: str = Field(
        ...,
        min_length=0,
        max_length=500,
        description="Описание группы бэктестов",
    )
    backtests: list[BacktestCreateRequest] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="Список бэктестов для выполнения (максимум 50)",
    )


# === ИНФОРМАЦИЯ ОБ ИНДИВИДУАЛЬНЫХ ЗАДАЧАХ ===


class BatchBacktestJobInfo(BaseModel):
    """Информация об индивидуальной задаче в составе группового бэктеста."""

    job_id: uuid.UUID = Field(..., description="ID задачи")
    status: JobStatusEnum = Field(..., description="Статус задачи")
    ticker: str = Field(..., description="Торговый инструмент")
    timeframe: str = Field(..., description="Таймфрейм")
    completion_time: datetime | None = Field(
        None, description="Время завершения задачи"
    )
    error_message: str | None = Field(
        None, description="Сообщение об ошибке, если статус FAILED"
    )

    model_config = ConfigDict(from_attributes=True)


# === ПОЛНЫЕ ОТВЕТЫ ===


class BatchBacktestResponse(BaseModel):
    """
    Полный ответ по групповому бэктесту.

    Содержит информацию о группе и статусы всех индивидуальных задач.
    """

    batch_id: uuid.UUID = Field(..., description="ID группового бэктеста")
    status: BatchStatusEnum = Field(..., description="Общий статус группы")
    description: str = Field(..., description="Описание группы")
    total_count: int = Field(..., description="Общее количество задач", ge=0)
    completed_count: int = Field(
        ..., description="Количество завершенных задач", ge=0
    )
    failed_count: int = Field(
        ..., description="Количество неудачных задач", ge=0
    )
    progress_percentage: float = Field(
        ..., description="Процент выполнения группы", ge=0, le=100
    )
    individual_jobs: list[BatchBacktestJobInfo] = Field(
        ..., description="Список индивидуальных задач"
    )
    estimated_completion_time: datetime | None = Field(
        None, description="Оценка времени завершения всей группы"
    )
    created_at: datetime = Field(..., description="Время создания группы")
    updated_at: datetime = Field(
        ..., description="Время последнего обновления"
    )

    model_config = ConfigDict(from_attributes=True)


# === КРАТКИЕ ОТВЕТЫ ДЛЯ СПИСКОВ ===


class BatchBacktestSummary(BaseModel):
    """Краткая информация о групповом бэктесте для списков."""

    batch_id: uuid.UUID = Field(..., description="ID группового бэктеста")
    description: str = Field(..., description="Описание группы")
    status: BatchStatusEnum = Field(..., description="Статус группы")
    total_count: int = Field(..., description="Общее количество задач", ge=0)
    completed_count: int = Field(
        ..., description="Количество завершенных задач", ge=0
    )
    failed_count: int = Field(
        ..., description="Количество неудачных задач", ge=0
    )
    progress_percentage: float = Field(
        ..., description="Процент выполнения", ge=0, le=100
    )
    estimated_completion_time: datetime | None = Field(
        None, description="Оценка времени завершения"
    )
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(..., description="Время обновления")

    model_config = ConfigDict(from_attributes=True)


# === ФИЛЬТРЫ ДЛЯ ПОИСКА ===


class BatchBacktestFilters(BaseModel):
    """Фильтры для поиска групповых бэктестов."""

    user_id: uuid.UUID | None = Field(
        None, description="Фильтр по пользователю (только для админов)"
    )
    status: BatchStatusEnum | None = Field(
        None, description="Фильтр по статусу"
    )
    created_after: datetime | None = Field(
        None, description="Показать созданные после указанной даты"
    )
    created_before: datetime | None = Field(
        None, description="Показать созданные до указанной даты"
    )
