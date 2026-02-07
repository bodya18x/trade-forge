"""
Базовые Pydantic схемы, используемые во всех сервисах Trade Forge.

Содержит общие схемы для пагинации, обработки ошибок и стандартных ответов.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

# Типовая переменная для пагинированных ответов
ItemType = TypeVar("ItemType")


class PaginatedResponse(BaseModel, Generic[ItemType]):
    """
    Стандартный пагинированный ответ для всех API эндпоинтов.

    Используется для возврата списков данных с информацией о пагинации.
    """

    items: list[ItemType] = Field(..., description="Элементы текущей страницы")
    total: int = Field(..., description="Общее количество элементов", ge=0)
    limit: int = Field(
        ..., description="Максимальное количество элементов на странице", gt=0
    )
    offset: int = Field(..., description="Смещение от начала списка", ge=0)

    @computed_field
    @property
    def has_more(self) -> bool:
        """Есть ли еще элементы после текущей страницы"""
        return (self.offset + len(self.items)) < self.total


class ErrorResponse(BaseModel):
    """
    Стандартная схема для ошибок в формате RFC 7807 (Problem Details).

    Обеспечивает единообразную структуру ошибок во всех сервисах.
    """

    type: str | None = Field(
        None, description="URI типа проблемы (для категоризации ошибки)"
    )
    title: str | None = Field(
        None, description="Краткое, человекочитаемое резюме проблемы"
    )
    status: int | None = Field(
        None, description="HTTP статус код", ge=400, le=599
    )
    detail: str | None = Field(None, description="Подробное описание проблемы")
    instance: str | None = Field(
        None, description="URI экземпляра проблемы (конкретный запрос)"
    )


class SuccessResponse(BaseModel):
    """
    Стандартная схема для успешных операций без возврата данных.

    Используется для операций типа DELETE или других, которые не возвращают объект.
    """

    success: bool = Field(True, description="Индикатор успешного выполнения")
    message: str | None = Field(
        None, description="Опциональное сообщение о результате"
    )


class ValidationErrorDetail(BaseModel):
    """
    Детальная информация об ошибке валидации поля.

    Используется в составе ErrorResponse для описания проблем валидации.
    """

    loc: list[str | int] = Field(..., description="Путь к полю с ошибкой")
    msg: str = Field(..., description="Сообщение об ошибке")
    type: str = Field(..., description="Тип ошибки валидации")
    input: Any | None = Field(
        None, description="Переданное значение (при наличии)"
    )


class ValidationErrorResponse(ErrorResponse):
    """
    Расширенная схема ошибок для детальных ошибок валидации.

    Наследует от ErrorResponse и добавляет массив детализированных ошибок.
    """

    errors: list[ValidationErrorDetail] | None = Field(
        None, description="Список детальных ошибок валидации"
    )


class SortDirection(str, Enum):
    """Направления сортировки."""

    ASC = "asc"
    DESC = "desc"
