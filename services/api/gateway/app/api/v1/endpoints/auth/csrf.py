"""
Эндпоинты CSRF защиты - Генерация и обновление CSRF токенов.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session

from app.core.redis import get_main_redis
from app.dependencies import get_current_user_with_session
from app.schemas.auth import CSRFTokenResponse, CurrentUserInfo
from app.services.auth_service import AuthService

router = APIRouter()


def get_auth_service(
    redis: Annotated[Redis, Depends(get_main_redis)],
) -> AuthService:
    """Получает экземпляр сервиса аутентификации."""
    return AuthService(redis=redis)


@router.get(
    "/csrf-token",
    response_model=CSRFTokenResponse,
    summary="Получить CSRF токен",
    description="""
    Возвращает CSRF токен для текущей сессии пользователя.

    **Функциональность:**
    - Генерирует или обновляет CSRF токен для текущей сессии
    - Сохраняет токен в Redis с TTL
    - Привязывает токен к session_id из JWT

    **Использование:**
    - Получите CSRF токен перед критичными операциями
    - Включите токен в заголовок `X-CSRF-Token` или в body запроса
    - Токен действителен в течение 1 часа

    **Безопасность:**
    - Каждая сессия имеет уникальный CSRF токен
    - Токен автоматически обновляется после использования
    - Защищает от Cross-Site Request Forgery атак
    """,
)
async def get_csrf_token(
    current_user: Annotated[
        "CurrentUserInfo", Depends(get_current_user_with_session)
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Генерирует или возвращает CSRF токен для текущей сессии.

    - Извлекает session_id из JWT токена
    - Генерирует новый CSRF токен
    - Сохраняет в Redis с TTL 1 час
    """
    session_id = current_user.session_id
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session ID not found in token. Please login with extended authentication.",
        )

    csrf_data = await auth_service.generate_csrf_token(
        user_id=current_user.id, session_id=session_id
    )

    return CSRFTokenResponse(**csrf_data)


@router.post(
    "/csrf-token",
    response_model=CSRFTokenResponse,
    summary="Обновить CSRF токен (POST)",
    description="""
    Обновляет CSRF токен для текущей сессии пользователя.

    **Безопасность:**
    - Требует валидный access токен
    - Инвалидирует ВСЕ старые CSRF токены для сессии
    - Генерирует новый уникальный CSRF токен
    - Привязывает токен к session_id из JWT
    - Логирует все обновления для аудита
    """,
)
async def refresh_csrf_token(
    current_user: Annotated[
        "CurrentUserInfo", Depends(get_current_user_with_session)
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Обновляет CSRF токен для текущей сессии (POST метод).
    """
    session_id = current_user.session_id
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session ID not found in token. Please login with extended authentication.",
        )

    csrf_data = await auth_service.refresh_csrf_token(
        db=db, user_id=current_user.id, session_id=session_id
    )

    return CSRFTokenResponse(**csrf_data)
