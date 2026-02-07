"""
Pydantic схемы для Kafka сообщений в MOEX Collector.

Универсальные схемы для различных типов задач по сбору данных.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CollectionTaskMessage(BaseModel):
    """
    Универсальное сообщение с задачей на сбор данных.

    Используется для всех типов сборов (свечи, ордербуки, сделки и т.д.).
    Consumer роутит задачу по task_type в нужный обработчик.
    """

    task_type: str = Field(
        ..., description="Тип задачи для роутинга в обработчик"
    )
    ticker: str = Field(..., description="Алиас тикера")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Параметры специфичные для типа задачи",
    )
