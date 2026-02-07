"""
Зависимости FastAPI для Internal API.

Включает извлечение и валидацию заголовков от Gateway.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Header, HTTPException, status
from tradeforge_logger import set_user_id

from app.types import UserID


async def get_current_user_id(
    x_user_id: Annotated[str | None, Header()] = None
) -> UserID:
    """
    Извлекает и валидирует X-User-ID из заголовков.

    Наш Internal API полностью доверяет Gateway, поэтому просто проверяем
    наличие и формат заголовка.

    Args:
        x_user_id: User ID из заголовка X-User-ID

    Returns:
        UUID пользователя

    Raises:
        HTTPException: Если заголовок отсутствует или неверный формат

    Note:
        Также устанавливает user_id в контекст логирования для observability.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID header is missing",
        )
    try:
        user_uuid = uuid.UUID(x_user_id)
        # Устанавливаем user_id в контекст логирования для observability
        set_user_id(str(user_uuid))
        return user_uuid
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid User ID format",
        )
