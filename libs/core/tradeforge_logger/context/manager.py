# -*- coding: utf-8 -*-
"""Управление контекстом логирования.

Этот модуль предоставляет async-safe механизмы для хранения контекстной
информации (correlation_id, request_id, user_id) с использованием ContextVars.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

# ContextVars для async-safe хранения контекста
_correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)
_request_id_var: ContextVar[str | None] = ContextVar(
    "request_id", default=None
)
_user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
_custom_context_var: ContextVar[dict[str, Any]] = ContextVar(
    "custom_context", default={}
)


# ============================================================================
# Correlation ID
# ============================================================================


def set_correlation_id(correlation_id: str) -> Token[str | None]:
    """Установить correlation ID в контекст.

    Args:
        correlation_id: Уникальный идентификатор для отслеживания
            операции через все микросервисы.

    Returns:
        Token для возможности сброса значения.

    Examples:
        >>> token = set_correlation_id("550e8400-e29b-41d4-a716-446655440000")
        >>> get_correlation_id()
        '550e8400-e29b-41d4-a716-446655440000'
    """
    return _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    """Получить correlation ID из контекста.

    Returns:
        Correlation ID или None если не установлен.

    Examples:
        >>> set_correlation_id("abc-123")
        >>> get_correlation_id()
        'abc-123'
    """
    return _correlation_id_var.get()


def clear_correlation_id() -> None:
    """Очистить correlation ID из контекста."""
    _correlation_id_var.set(None)


# ============================================================================
# Request ID
# ============================================================================


def generate_request_id() -> str:
    """Сгенерировать новый request ID.

    Returns:
        Уникальный request ID в формате UUID4.

    Examples:
        >>> request_id = generate_request_id()
        >>> len(request_id)
        36
    """
    return f"req_{uuid.uuid4().hex[:12]}"


def set_request_id(request_id: str) -> Token[str | None]:
    """Установить request ID в контекст.

    Args:
        request_id: Уникальный идентификатор HTTP запроса.

    Returns:
        Token для возможности сброса значения.

    Examples:
        >>> token = set_request_id("req_abc123")
        >>> get_request_id()
        'req_abc123'
    """
    return _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Получить request ID из контекста.

    Returns:
        Request ID или None если не установлен.
    """
    return _request_id_var.get()


def clear_request_id() -> None:
    """Очистить request ID из контекста."""
    _request_id_var.set(None)


# ============================================================================
# User ID
# ============================================================================


def set_user_id(user_id: str) -> Token[str | None]:
    """Установить user ID в контекст.

    Args:
        user_id: Идентификатор пользователя.

    Returns:
        Token для возможности сброса значения.

    Examples:
        >>> token = set_user_id("user_789")
        >>> get_user_id()
        'user_789'
    """
    return _user_id_var.set(user_id)


def get_user_id() -> str | None:
    """Получить user ID из контекста.

    Returns:
        User ID или None если не установлен.
    """
    return _user_id_var.get()


def clear_user_id() -> None:
    """Очистить user ID из контекста."""
    _user_id_var.set(None)


# ============================================================================
# Custom Context
# ============================================================================


def set_custom_context(key: str, value: Any) -> None:
    """Установить кастомное значение в контекст.

    Args:
        key: Ключ.
        value: Значение.

    Examples:
        >>> set_custom_context("tenant_id", "tenant_123")
        >>> get_custom_context("tenant_id")
        'tenant_123'
    """
    current = _custom_context_var.get()
    updated = {**current, key: value}
    _custom_context_var.set(updated)


def get_custom_context(key: str) -> Any:
    """Получить кастомное значение из контекста.

    Args:
        key: Ключ.

    Returns:
        Значение или None если ключ не найден.
    """
    return _custom_context_var.get().get(key)


def get_all_custom_context() -> dict[str, Any]:
    """Получить весь кастомный контекст.

    Returns:
        Словарь с кастомным контекстом.
    """
    return _custom_context_var.get().copy()


def clear_custom_context() -> None:
    """Очистить весь кастомный контекст."""
    _custom_context_var.set({})


# ============================================================================
# Context Managers
# ============================================================================


@contextmanager
def bind_context(**kwargs: Any) -> Iterator[None]:
    """Временно добавить контекст.

    Args:
        **kwargs: Контекстные поля (correlation_id, request_id, user_id,
            или любые кастомные поля).

    Yields:
        None

    Examples:
        >>> with bind_context(correlation_id="abc", user_id="user_1"):
        ...     logger.info("test")  # будет содержать correlation_id и user_id
    """
    tokens: list[Token] = []

    # Стандартные поля
    if "correlation_id" in kwargs:
        tokens.append(set_correlation_id(kwargs["correlation_id"]))
    if "request_id" in kwargs:
        tokens.append(set_request_id(kwargs["request_id"]))
    if "user_id" in kwargs:
        tokens.append(set_user_id(kwargs["user_id"]))

    # Кастомные поля
    custom_keys = set(kwargs.keys()) - {
        "correlation_id",
        "request_id",
        "user_id",
    }
    old_custom_context = _custom_context_var.get()
    if custom_keys:
        new_custom_context = {
            **old_custom_context,
            **{k: kwargs[k] for k in custom_keys},
        }
        tokens.append(_custom_context_var.set(new_custom_context))

    try:
        yield
    finally:
        # Восстанавливаем предыдущие значения
        for token in reversed(tokens):
            token.var.reset(token)


def clear_all_context() -> None:
    """Очистить весь контекст.

    Полезно для тестов или явного сброса.
    """
    clear_correlation_id()
    clear_request_id()
    clear_user_id()
    clear_custom_context()


def get_current_context() -> dict[str, Any]:
    """Получить весь текущий контекст.

    Returns:
        Словарь со всеми контекстными полями.

    Examples:
        >>> with bind_context(correlation_id="abc", user_id="user_1"):
        ...     context = get_current_context()
        >>> context
        {'correlation_id': 'abc', 'user_id': 'user_1'}
    """
    context: dict[str, Any] = {}

    if correlation_id := get_correlation_id():
        context["correlation_id"] = correlation_id
    if request_id := get_request_id():
        context["request_id"] = request_id
    if user_id := get_user_id():
        context["user_id"] = user_id

    # Добавляем кастомный контекст
    context.update(get_all_custom_context())

    return context
