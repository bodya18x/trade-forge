from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger

from app.core.auth import extract_token_data, extract_user_id_from_token
from app.core.proxy_client import InternalAPIClient, internal_api_client
from app.core.rate_limiting import check_user_rate_limits
from app.core.redis import get_rate_limit_redis
from app.crud.crud_users import get_user_by_id
from app.schemas.auth import CurrentUserInfo
from app.settings import settings

log = get_logger(__name__)

# Bearer token security scheme
security = HTTPBearer()


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> uuid.UUID:
    """
    Извлекает и валидирует user_id из JWT токена.

    Args:
        credentials: Bearer токен из заголовка Authorization

    Returns:
        UUID пользователя

    Raises:
        HTTPException: Если токен невалиден или пользователь не найден
    """
    token = credentials.credentials
    user_id = await extract_user_id_from_token(token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_current_user(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserInfo:
    """
    Получает текущего пользователя из базы данных.

    Args:
        user_id: UUID пользователя из JWT токена
        db: Сессия базы данных

    Returns:
        Данные пользователя в виде CurrentUserInfo

    Raises:
        HTTPException: Если пользователь не найден или неактивен
    """
    user = await get_user_by_id(db, user_id=user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Преобразуем ORM объект в Pydantic модель
    return CurrentUserInfo(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        subscription_tier=user.subscription_tier,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def get_current_user_with_session(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserInfo:
    """
    Получает текущего пользователя с session_id из JWT токена.

    Args:
        credentials: Bearer токен из заголовка Authorization
        db: Сессия базы данных

    Returns:
        Данные пользователя в виде CurrentUserInfo с session_id

    Raises:
        HTTPException: Если токен невалиден или пользователь не найден
    """
    token = credentials.credentials
    token_data = await extract_token_data(token)

    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = token_data["user_id"]
    session_id = token_data["session_id"]

    # Получаем пользователя из БД
    user = await get_user_by_id(db, user_id=user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Преобразуем ORM объект в Pydantic модель и добавляем session_id
    return CurrentUserInfo(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        subscription_tier=user.subscription_tier,
        created_at=user.created_at,
        updated_at=user.updated_at,
        session_id=session_id,
    )


async def require_admin(
    current_user: Annotated[CurrentUserInfo, Depends(get_current_user)]
) -> CurrentUserInfo:
    """
    Dependency для проверки, что пользователь является администратором.

    Args:
        current_user: Данные текущего пользователя

    Returns:
        Данные пользователя, если он администратор

    Raises:
        HTTPException: Если пользователь не является администратором
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )

    return current_user


async def get_user_subscription_limits(
    current_user: Annotated[CurrentUserInfo, Depends(get_current_user)]
) -> dict[str, int]:
    """
    Получает лимиты пользователя на основе его тарифа.

    Args:
        current_user: Данные текущего пользователя

    Returns:
        Словарь с лимитами пользователя
    """
    limits = settings.SUBSCRIPTION_LIMITS.get(
        current_user.subscription_tier, settings.SUBSCRIPTION_LIMITS["free"]
    )

    return limits


def get_internal_api_client() -> InternalAPIClient:
    """
    Dependency для получения HTTP клиента Internal API.

    Returns:
        Экземпляр InternalAPIClient
    """
    return internal_api_client


async def check_user_limits_with_tier(
    current_user: Annotated[CurrentUserInfo, Depends(get_current_user)],
    method: str,
    resource_type: str = None,
) -> None:
    """
    Dependency для проверки лимитов пользователя с автоматическим извлечением subscription_tier.

    Args:
        current_user: Данные текущего пользователя
        method: HTTP метод
        resource_type: Тип ресурса

    Raises:
        HTTPException: При превышении лимитов
    """
    redis = get_rate_limit_redis()

    await check_user_rate_limits(
        redis=redis,
        user_id=current_user.id,
        method=method,
        subscription_tier=current_user.subscription_tier,
        resource_type=resource_type,
    )


class RateLimitChecker:
    """
    Класс-обертка для создания dependency с конкретными параметрами.
    """

    def __init__(self, method: str, resource_type: str = None):
        self.method = method
        self.resource_type = resource_type

    async def __call__(
        self,
        current_user: Annotated[CurrentUserInfo, Depends(get_current_user)],
    ) -> None:
        await check_user_limits_with_tier(
            current_user=current_user,
            method=self.method,
            resource_type=self.resource_type,
        )


# Предопределенные dependency для часто используемых случаев
check_strategy_creation_limits = RateLimitChecker("POST", "strategy")
check_backtest_creation_limits = RateLimitChecker("POST", "backtest")
check_general_write_limits = RateLimitChecker("POST")
check_general_read_limits = RateLimitChecker("GET")
