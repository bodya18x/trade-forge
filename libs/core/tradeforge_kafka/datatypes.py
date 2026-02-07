"""
Типы и Pydantic схемы для Kafka сообщений.

Этот модуль определяет базовые типы и схемы для работы с Kafka,
включая обертки над сообщениями и метаданные.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class KafkaMessageMetadata(BaseModel):
    """
    Метаданные обработки Kafka сообщения.

    Используется для observability и трейсинга.

    Attributes:
        processing_time_ms: Время обработки сообщения в миллисекундах
        retries: Количество повторных попыток обработки
        error: Описание ошибки (если была)
        correlation_id: ID для distributed tracing
    """

    processing_time_ms: float = Field(
        ..., description="Время обработки в миллисекундах"
    )
    retries: int = Field(default=0, ge=0, description="Количество retry")
    error: str | None = Field(default=None, description="Сообщение об ошибке")
    correlation_id: str | None = Field(
        default=None, description="Correlation ID для трейсинга"
    )


class KafkaMessage(BaseModel, Generic[T]):
    """
    Обёртка над Kafka сообщением с валидацией через Pydantic.

    Generic класс, где T - это Pydantic модель для полезной нагрузки.

    Attributes:
        key: Ключ сообщения (используется для партицирования)
        value: Полезная нагрузка (валидированная Pydantic модель)
        topic: Название топика
        partition: Номер партиции
        offset: Offset сообщения в партиции
        timestamp: Временная метка сообщения
        headers: Заголовки сообщения (например, correlation_id)

    Example:
        ```python
        class MyPayload(BaseModel):
            ticker: str
            price: float

        message = KafkaMessage[MyPayload](
            key="SBER",
            value=MyPayload(ticker="SBER", price=250.0),
            topic="prices",
            partition=0,
            offset=12345,
            timestamp=datetime.now()
        )
        ```
    """

    key: str | None = Field(default=None, description="Ключ сообщения")
    value: T = Field(..., description="Полезная нагрузка")
    topic: str = Field(..., description="Топик")
    partition: int = Field(..., ge=0, description="Партиция")
    offset: int = Field(..., ge=0, description="Offset")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Временная метка",
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Заголовки сообщения"
    )

    class Config:
        arbitrary_types_allowed = True

    @property
    def correlation_id(self) -> str | None:
        """Извлекает correlation_id из заголовков."""
        return self.headers.get("X-Correlation-ID")

    def set_correlation_id(self, correlation_id: str) -> None:
        """Устанавливает correlation_id в заголовки."""
        self.headers["X-Correlation-ID"] = correlation_id


class RecordMetadata(BaseModel):
    """
    Метаданные отправленного сообщения (результат send).

    Attributes:
        topic: Топик
        partition: Партиция
        offset: Offset
        timestamp: Временная метка записи
    """

    topic: str
    partition: int
    offset: int
    timestamp: datetime | None = None


class DLQMessage(BaseModel):
    """
    Структура сообщения в Dead Letter Queue.

    Содержит оригинальное сообщение + метаданные об ошибке.

    Attributes:
        original_message: Оригинальное сообщение (как dict)
        original_topic: Исходный топик
        error: Описание ошибки
        stacktrace: Стек-трейс ошибки
        attempts: Количество попыток обработки
        first_attempt_at: Время первой попытки
        last_attempt_at: Время последней попытки
        correlation_id: Correlation ID для трейсинга
    """

    original_message: dict[str, Any] = Field(
        ..., description="Оригинальное сообщение"
    )
    original_topic: str = Field(..., description="Исходный топик")
    error: str = Field(..., description="Описание ошибки")
    stacktrace: str = Field(..., description="Стек-трейс")
    attempts: int = Field(..., gt=0, description="Количество попыток")
    first_attempt_at: datetime = Field(..., description="Время первой попытки")
    last_attempt_at: datetime = Field(
        ..., description="Время последней попытки"
    )
    correlation_id: str | None = Field(
        default=None, description="Correlation ID"
    )
