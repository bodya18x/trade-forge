# -*- coding: utf-8 -*-
"""Вспомогательные функции."""

from __future__ import annotations

import sys
import traceback
from typing import Any


def format_exception_info(exc_info: tuple | None = None) -> dict[str, Any]:
    """Форматирует информацию об исключении в структурированный вид.

    Args:
        exc_info: Tuple (type, value, traceback) или None для использования
            sys.exc_info().

    Returns:
        Словарь с информацией об исключении.

    Examples:
        >>> try:
        ...     raise ValueError("test error")
        ... except ValueError:
        ...     info = format_exception_info()
        >>> info["type"]
        'ValueError'
        >>> info["message"]
        'test error'
    """
    if exc_info is None:
        exc_info = sys.exc_info()

    if exc_info == (None, None, None):
        return {}

    exc_type, exc_value, exc_traceback = exc_info

    if exc_type is None or exc_value is None:
        return {}

    # Форматируем traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)

    return {
        "type": exc_type.__name__,
        "message": str(exc_value),
        "traceback": [line.rstrip() for line in tb_lines],
        "module": exc_type.__module__ if exc_type.__module__ else None,
    }


def truncate_string(value: str, max_length: int = 1000) -> str:
    """Обрезает строку до максимальной длины.

    Args:
        value: Строка для обрезки.
        max_length: Максимальная длина.

    Returns:
        Обрезанная строка с индикатором если была обрезана.

    Examples:
        >>> truncate_string("hello world", 5)
        'hello...[truncated]'
        >>> truncate_string("hello", 10)
        'hello'
    """
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}...[truncated]"
