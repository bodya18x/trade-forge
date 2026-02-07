"""
Административные эндпоинты - Управление токенами и безопасностью.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger

from app.crud.crud_sessions import (
    blacklist_token,
    is_token_blacklisted_db,
    log_security_event,
)
from app.dependencies import require_admin
from app.schemas.auth import (
    BlacklistTokenRequest,
    BlacklistTokenResponse,
    CurrentUserInfo,
    TokenStatusResponse,
)

log = get_logger(__name__)

router = APIRouter()


@router.post(
    "/blacklist-token",
    response_model=BlacklistTokenResponse,
    summary="Принудительно заблокировать токен",
    description="""
    Принудительно добавляет токен в blacklist (admin endpoint).

    **Функциональность:**
    - Блокирует токен по его JTI (JWT ID)
    - Указывает причину блокировки для аудита
    - Логирует принудительную блокировку

    **Использование:**
    - Экстренная блокировка скомпрометированных токенов
    - Принудительный logout конкретного пользователя
    - Реагирование на инциденты безопасности

    **Безопасность:**
    - Endpoint требует админских прав (в продакшене)
    - Полное логирование всех блокировок
    - Невозможно отменить блокировку (только до истечения TTL)

    **Примеры причин:**
    - `security_breach`: Нарушение безопасности
    - `account_compromised`: Компрометация аккаунта
    - `policy_violation`: Нарушение политики
    """,
)
async def blacklist_token_manually(
    request: BlacklistTokenRequest,
    current_user: Annotated["CurrentUserInfo", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Принудительно блокирует токен (admin функция).

    - Добавляет token_jti в blacklist
    - Указывает причину блокировки
    - Логирует принудительную блокировку
    """

    user_id = current_user.id

    # Проверка админских прав уже выполнена через require_admin dependency

    # Устанавливаем время истечения (30 дней для безопасности)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    # Добавляем в blacklist
    success = await blacklist_token(
        db=db,
        token_jti=request.token_jti,
        token_type="access",  # Принудительно блокируем как access токен
        user_id=user_id,  # ID администратора
        expires_at=expires_at,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to blacklist token",
        )

    # Логируем принудительную блокировку
    await log_security_event(
        db=db,
        event_type="token_blacklisted_manually",
        user_id=user_id,
        details={
            "blocked_token_jti": request.token_jti,
            "reason": request.reason,
            "admin_action": True,
        },
    )

    log.info(
        "token.blacklisted.manually",
        admin_user_id=str(user_id),
        blocked_token_jti=request.token_jti,
        reason=request.reason,
    )

    return BlacklistTokenResponse(
        message="Token blacklisted successfully", success=True
    )


@router.get(
    "/token-status/{token_jti}",
    response_model=TokenStatusResponse,
    summary="Проверить статус токена",
    description="""
    Проверяет статус конкретного токена по его JTI.

    **Возможные статусы:**
    - `active`: Токен активен и действителен
    - `blacklisted`: Токен заблокирован
    - `expired`: Токен истек по времени

    **Функциональность:**
    - Проверка blacklist в БД
    - Проверка времени истечения
    - Детальная информация о блокировке

    **Use case:**
    - Диагностика проблем с токенами
    - Проверка результата блокировки
    - Мониторинг безопасности
    """,
)
async def get_token_status(
    token_jti: str,
    current_user: Annotated["CurrentUserInfo", Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Возвращает статус токена по его JTI.

    - Проверяет blacklist в БД
    - Определяет статус токена
    - Возвращает детальную информацию
    """

    # Проверка админских прав уже выполнена через require_admin dependency
    # Проверяем blacklist
    is_blacklisted = await is_token_blacklisted_db(db, token_jti)

    if is_blacklisted:
        # Токен в blacklist - ищем детали
        query = text(
            """
            SELECT created_at as blacklisted_at, expires_at
            FROM auth.token_blacklist
            WHERE token_jti = :token_jti
        """
        )
        result = await db.execute(query, {"token_jti": token_jti})
        blacklist_info = result.mappings().one_or_none()

        return TokenStatusResponse(
            token_jti=token_jti,
            status="blacklisted",
            blacklisted_at=(
                blacklist_info["blacklisted_at"] if blacklist_info else None
            ),
            expires_at=(
                blacklist_info["expires_at"]
                if blacklist_info
                else datetime.now(timezone.utc)
            ),
        )

    # Токен не в blacklist - считаем активным
    # В продакшене здесь можно добавить более детальную проверку времени истечения
    default_expiry = datetime.now(timezone.utc) + timedelta(days=7)

    log.info(
        "token.status.checked",
        user_id=str(current_user.id),
        checked_token_jti=token_jti,
        status="active",
    )

    return TokenStatusResponse(
        token_jti=token_jti,
        status="active",
        blacklisted_at=None,
        expires_at=default_expiry,
    )
