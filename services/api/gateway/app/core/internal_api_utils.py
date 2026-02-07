"""
Утилиты для работы с Internal API - обработка ошибок и ответов.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def extract_internal_api_error_detail(response_text: str) -> str:
    """
    Безопасно извлекает detail из ответа внутреннего API.
    Скрывает внутренние URL и структуры от пользователя.

    Args:
        response_text: Сырой текст ответа от Internal API

    Returns:
        Безопасное сообщение об ошибке для пользователя
    """
    try:
        # Пробуем распарсить JSON ответ внутреннего API
        error_data = json.loads(response_text)

        # Извлекаем только detail, игнорируя внутренние URL и структуру
        if isinstance(error_data, dict) and "detail" in error_data:
            return error_data["detail"]

    except (json.JSONDecodeError, KeyError, TypeError):
        # Если не удалось распарсить - возвращаем безопасное сообщение
        pass

    # Если ничего не получилось - возвращаем общее сообщение
    return "Ошибка обработки запроса. Пожалуйста, проверьте данные и попробуйте еще раз."


def extract_error_detail_safe(response_text: str, default_message: str) -> str:
    """
    Извлекает detail из ответа или возвращает default сообщение.

    Args:
        response_text: Сырой текст ответа от Internal API
        default_message: Сообщение по умолчанию, если извлечение не удалось

    Returns:
        Сообщение об ошибке
    """
    try:
        error_data = json.loads(response_text)
        detail = error_data.get("detail", default_message)
        return detail if detail and detail.strip() else default_message
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return default_message


def sanitize_internal_api_response(
    response_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Очищает ответ Internal API от внутренних деталей перед отдачей клиенту.

    Args:
        response_data: Данные ответа от Internal API

    Returns:
        Санитизированные данные
    """
    # В будущем здесь можно добавить логику фильтрации внутренних полей
    # Например, удаление internal_id, debug_info и т.д.
    return response_data
