from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from tradeforge_db import UserSessions, get_db_manager
from tradeforge_logger import get_logger

from app.core.redis import get_main_redis
from app.settings import settings

log = get_logger(__name__)


class JWTPayload(BaseModel):
    """
    Структура payload JWT токена.
    """

    user_id: str
    email: str
    exp: int
    iat: int
    token_type: str = "access"  # access or refresh
    session_id: Optional[str] = None  # ID сессии для связи с БД


def create_access_token(
    user_id: uuid.UUID, email: str, session_id: Optional[uuid.UUID] = None
) -> str:
    """
    Создает JWT access token для пользователя.

    Args:
        user_id: UUID пользователя
        email: Email пользователя
        session_id: UUID сессии (для связи с БД)

    Returns:
        JWT токен в виде строки
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    payload = {
        "user_id": str(user_id),
        "email": email,
        "token_type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_hex(16),
    }

    if session_id:
        payload["session_id"] = str(session_id)

    token = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token


def create_refresh_token(
    user_id: uuid.UUID,
    email: str,
    session_id: Optional[uuid.UUID] = None,
    remember_me: bool = False,
) -> tuple[str, str]:
    """
    Создает JWT refresh token для пользователя.

    Args:
        user_id: UUID пользователя
        email: Email пользователя
        session_id: UUID сессии
        remember_me: Увеличить время жизни токена

    Returns:
        Кортеж (refresh_token, jti)
    """
    now = datetime.now(timezone.utc)
    expire_days = 30 if remember_me else settings.JWT_REFRESH_EXPIRE_DAYS
    expire = now + timedelta(days=expire_days)

    jti = secrets.token_hex(16)
    payload = {
        "user_id": str(user_id),
        "email": email,
        "token_type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
    }

    if session_id:
        payload["session_id"] = str(session_id)

    token = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token, jti


def create_token_pair(
    user_id: uuid.UUID,
    email: str,
    session_id: Optional[uuid.UUID] = None,
    remember_me: bool = False,
) -> tuple[str, str, str]:
    """
    Создает пару токенов (access и refresh) для пользователя.

    Args:
        user_id: UUID пользователя
        email: Email пользователя
        session_id: UUID сессии
        remember_me: Увеличить время жизни refresh токена

    Returns:
        Кортеж (access_token, refresh_token, refresh_jti)
    """
    access_token = create_access_token(user_id, email, session_id)
    refresh_token, refresh_jti = create_refresh_token(
        user_id, email, session_id, remember_me
    )
    return access_token, refresh_token, refresh_jti


async def verify_token(
    token: str, expected_type: str = "access"
) -> JWTPayload | None:
    """
    Валидирует JWT токен и извлекает payload.

    Args:
        token: JWT токен для проверки
        expected_type: Ожидаемый тип токена ("access" или "refresh")

    Returns:
        JWTPayload если токен валиден, None если невалиден
    """
    try:
        # Проверяем что токен не пустой
        if not token or not token.strip():
            log.warning("token.empty_or_whitespace", token_type=expected_type)
            return None

        # Убираем лишние пробелы
        token = token.strip()
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        # Проверяем наличие обязательных полей
        if not payload.get("user_id") or not payload.get("email"):
            return None

        # Проверяем тип токена
        token_type = payload.get("token_type", "access")
        if token_type != expected_type:
            log.warning(
                "token.type.mismatch",
                expected=expected_type,
                actual=token_type,
            )
            return None

        # Проверяем срок действия
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(
            exp, tz=timezone.utc
        ) < datetime.now(timezone.utc):
            return None

        # Проверяем blacklist
        if await is_token_blacklisted(token):
            log.info("token.blacklisted", token_type=expected_type)
            return None

        # Для access токенов проверяем активность сессии
        if expected_type == "access":
            session_id = payload.get("session_id")
            if session_id and not await is_session_active(session_id):
                log.info(
                    "session.inactive",
                    session_id=session_id,
                )
                return None

        return JWTPayload.model_validate(payload)

    except JWTError as e:
        log.warning(
            "token.jwt.invalid", error=str(e), token_type=expected_type
        )
        return None
    except ValueError as e:
        log.warning(
            "token.validation.error", error=str(e), token_type=expected_type
        )
        return None
    except Exception as e:
        log.error(
            "token.error.unexpected", error=str(e), token_type=expected_type
        )
        return None


async def verify_access_token(token: str) -> JWTPayload | None:
    """
    Валидирует JWT access token.

    Args:
        token: JWT access token для проверки

    Returns:
        JWTPayload если токен валиден, None если невалиден
    """
    return await verify_token(token, "access")


async def verify_refresh_token(token: str) -> JWTPayload | None:
    """
    Валидирует JWT refresh token.

    Args:
        token: JWT refresh token для проверки

    Returns:
        JWTPayload если токен валиден, None если невалиден
    """
    return await verify_token(token, "refresh")


async def extract_user_id_from_token(token: str) -> uuid.UUID | None:
    """
    Извлекает user_id из JWT токена.

    Args:
        token: JWT токен

    Returns:
        UUID пользователя или None если токен невалиден
    """
    payload = await verify_access_token(token)
    if not payload:
        return None

    try:
        return uuid.UUID(payload.user_id)
    except ValueError:
        log.warning("token.user_id.invalid", user_id=payload.user_id)
        return None


async def extract_session_id_from_token(token: str) -> uuid.UUID | None:
    """
    Извлекает session_id из JWT токена.

    Args:
        token: JWT токен

    Returns:
        UUID сессии или None если токен невалиден или нет session_id
    """
    payload = await verify_access_token(token)
    if not payload:
        return None

    # Проверяем наличие session_id в токене
    if not hasattr(payload, "session_id") or not payload.session_id:
        log.warning("token.session_id.missing")
        return None

    try:
        return uuid.UUID(payload.session_id)
    except ValueError:
        log.warning("token.session_id.invalid", session_id=payload.session_id)
        return None


async def extract_token_data(token: str) -> dict | None:
    """
    Извлекает все данные из JWT токена (user_id, session_id).

    Args:
        token: JWT токен

    Returns:
        Словарь с данными токена или None если токен невалиден
    """
    payload = await verify_access_token(token)
    if not payload:
        return None

    result = {}

    # Извлекаем user_id
    try:
        result["user_id"] = uuid.UUID(payload.user_id)
    except ValueError:
        log.warning(
            "token.user_id.invalid.in.payload", user_id=payload.user_id
        )
        return None

    # Извлекаем session_id если есть
    if hasattr(payload, "session_id") and payload.session_id:
        try:
            result["session_id"] = uuid.UUID(payload.session_id)
        except ValueError:
            log.warning(
                "token.session_id.invalid.in.payload",
                session_id=payload.session_id,
            )
            return None

    return result


async def invalidate_token(token: str) -> bool:
    """
    Инвалидирует JWT токен, добавляя его в blacklist в Redis.

    Args:
        token: JWT токен для инвалидации

    Returns:
        True если токен успешно инвалидирован, False в случае ошибки
    """
    try:
        # Проверяем токен и извлекаем JTI (unique token ID)
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        jti = payload.get("jti")
        exp = payload.get("exp")

        if not jti or not exp:
            log.warning("token.claims.missing")
            return False

        # Вычисляем время до истечения токена
        now = datetime.now(timezone.utc)
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
        ttl_seconds = int((exp_datetime - now).total_seconds())

        # Если токен уже истек, не нужно его blacklist'ить
        if ttl_seconds <= 0:
            log.info("token.expired.skip.blacklist")
            return True

        # Добавляем JTI в Redis blacklist с TTL равным времени до истечения токена
        redis_client = get_main_redis()
        blacklist_key = f"token_blacklist:{jti}"

        await redis_client.setex(blacklist_key, ttl_seconds, "invalidated")

        log.info("token.invalidated", jti=jti)
        return True

    except JWTError as e:
        log.warning("token.invalidation.jwt.invalid", error=str(e))
        return False
    except Exception as e:
        log.error("token.invalidation.error", error=str(e))
        return False


async def is_token_blacklisted(token: str) -> bool:
    """
    Проверяет, находится ли токен в blacklist.

    Args:
        token: JWT токен для проверки

    Returns:
        True если токен в blacklist, False если нет или в случае ошибки
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        jti = payload.get("jti")
        if not jti:
            return False

        redis_client = get_main_redis()
        blacklist_key = f"token_blacklist:{jti}"

        is_blacklisted = await redis_client.exists(blacklist_key)

        return bool(is_blacklisted)

    except Exception as e:
        log.error("token.blacklist.check.error", error=str(e))
        return False


async def is_session_active(session_id: str) -> bool:
    """
    Проверяет, активна ли сессия в базе данных.

    Args:
        session_id: UUID сессии для проверки

    Returns:
        True если сессия активна, False если неактивна или не найдена
    """
    try:
        db_manager = get_db_manager()
        async with db_manager.session() as db:
            stmt = select(UserSessions).where(
                UserSessions.session_id == uuid.UUID(session_id),
                UserSessions.is_active == True,
            )

            result = await db.execute(stmt)
            session = result.scalar_one_or_none()

            is_active = session is not None

            log.info(
                "session.status.checked",
                session_id=session_id,
                is_active=is_active,
            )

            return is_active

    except Exception as e:
        log.error(
            "session.status.check.error",
            session_id=session_id,
            error=str(e),
        )
        # В случае ошибки БД запрещаем доступ (fail closed) для безопасности
        return False
