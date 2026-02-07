from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger
from tradeforge_schemas.auth import UserResponse, UserUpdate

from app.core.redis import get_rate_limit_redis
from app.crud.crud_users import update_user
from app.dependencies import get_current_user, get_current_user_id
from app.schemas.auth import CurrentUserInfo
from app.schemas.limits import UserLimitsResponse
from app.services.limits_service import LimitsService

log = get_logger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=UserResponse,
    summary="Получить профиль текущего пользователя",
)
async def get_profile(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """
    Возвращает информацию о профиле текущего авторизованного пользователя.
    """
    return UserResponse.model_validate(current_user)


@router.put(
    "/",
    response_model=UserResponse,
    summary="Обновить профиль пользователя",
)
async def update_profile(
    user_update: UserUpdate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Обновляет профиль текущего пользователя.

    - Можно обновить email и/или пароль
    - При обновлении пароля он автоматически хешируется
    """
    updated_user = await update_user(db, user_id=user_id, user_in=user_update)

    if not updated_user:
        log.error("user.profile.update.failed", user_id=str(user_id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    log.info("user.profile.updated", user_id=str(user_id))

    return UserResponse.model_validate(updated_user)


@router.get(
    "/limits",
    response_model=UserLimitsResponse,
    summary="Получить лимиты пользователя",
    description="""
    Возвращает информацию о текущих лимитах пользователя и их использовании.

    **Включает в себя:**
    - Лимиты создания стратегий в сутки
    - Лимиты запуска бэктестов в сутки
    - Лимиты одновременных бэктестов
    - Максимальный период бэктеста
    - Текущее использование каждого лимита
    - Время сброса лимитов (00:00 МСК)

    **Лимиты зависят от тарифного плана:**
    - **free**: 5 стратегий/день, 25 бэктестов/день, 2 одновременных
    - **pro**: 50 стратегий/день, 200 бэктестов/день, 10 одновременных
    - **enterprise**: 500 стратегий/день, 1000 бэктестов/день, 25 одновременных
    """,
)
async def get_user_limits(
    current_user: Annotated["CurrentUserInfo", Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
):
    """
    Получает информацию о лимитах пользователя и их текущем использовании.
    """
    limits_service = LimitsService(redis)

    user_id = current_user.id
    subscription_tier = current_user.subscription_tier

    limits = await limits_service.get_user_limits(user_id, subscription_tier)

    log.info(
        "user.limits.retrieved",
        user_id=str(user_id),
        subscription_tier=subscription_tier,
        strategies_used=limits.strategies_per_day.used,
        backtests_used=limits.backtests_per_day.used,
    )

    return limits
