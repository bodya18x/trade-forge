"""
CRUD операции для управления пользовательскими сессиями.

Использует SQLAlchemy 2.0+ синтаксис с ORM моделями из tradeforge_db.

Реализует функции для:
- Создания и управления сессиями
- Работы с blacklist токенов
- Логирования событий безопасности
- Геолокации и device fingerprinting
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import SecurityEvents, TokenBlacklist, UserSessions
from tradeforge_logger import get_logger

from app.core.device_fingerprinting import device_fingerprint_enricher
from app.core.redis import get_main_redis

log = get_logger(__name__)


async def create_user_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    refresh_token_jti: str,
    device_info: Optional[Dict[str, Any]] = None,
    remember_me: bool = False,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создает новую пользовательскую сессию.

    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        refresh_token_jti: JTI refresh токена
        device_info: Информация об устройстве
        remember_me: Запомнить пользователя (увеличить TTL)
        ip_address: IP адрес клиента

    Returns:
        Словарь с данными созданной сессии
    """
    session_id = uuid.uuid4()
    csrf_token = secrets.token_hex(32)

    # Время жизни сессии зависит от remember_me
    expires_delta = timedelta(days=30 if remember_me else 7)
    expires_at = datetime.now(timezone.utc) + expires_delta

    # Обогащаем device fingerprint с GeoIP и парсингом User-Agent
    enriched_device_info = device_info or {}

    # Извлекаем user_agent из device_info или используем пустую строку
    user_agent_string = ""
    if device_info:
        user_agent_string = device_info.get("user_agent", "")

    if device_info and ip_address and user_agent_string:
        try:
            enriched_device_info = (
                await device_fingerprint_enricher.enrich_fingerprint(
                    client_ip=ip_address,
                    user_agent=user_agent_string,
                    base_fingerprint=device_info,
                )
            )

            # Создаем хеш безопасности для fingerprint
            security_fingerprint_hash = (
                device_fingerprint_enricher.create_security_fingerprint_hash(
                    enriched_device_info
                )
            )
            enriched_device_info["security_fingerprint_hash"] = (
                security_fingerprint_hash
            )

            log.info(
                "session.device.fingerprint.enriched",
                user_id=str(user_id),
                has_geo=bool(enriched_device_info.get("geo")),
                has_parsed_ua=bool(
                    enriched_device_info.get("parsed_user_agent")
                ),
                fingerprint_hash=security_fingerprint_hash[:16]
                + "...",  # Первые 16 символов для логов
            )
        except Exception as e:
            log.error(
                "session.device.fingerprint.failed",
                user_id=str(user_id),
                error=str(e),
            )

    device_name = (
        enriched_device_info.get("device_name")
        if enriched_device_info
        else None
    )
    device_type = (
        enriched_device_info.get("device_type")
        if enriched_device_info
        else None
    )
    user_agent = (
        enriched_device_info.get("user_agent")
        if enriched_device_info
        else None
    )

    # Создаем запись сессии через ORM
    new_session = UserSessions(
        session_id=session_id,
        user_id=user_id,
        refresh_token_jti=refresh_token_jti,
        device_name=device_name,
        device_type=device_type,
        user_agent=user_agent,
        ip_address=ip_address,
        csrf_token=csrf_token,
        enriched_device_info=(
            enriched_device_info if enriched_device_info else None
        ),
        expires_at=expires_at,
        is_active=True,
    )

    db.add(new_session)
    await db.flush()

    # Сохраняем CSRF токен в Redis для middleware валидации
    try:
        redis = get_main_redis()
        csrf_key = f"csrf_token:{session_id}"
        # TTL равен времени жизни сессии в секундах
        ttl_seconds = int(expires_delta.total_seconds())
        await redis.setex(csrf_key, ttl_seconds, csrf_token)

        log.info(
            "session.csrf.token.saved",
            session_id=str(session_id),
            ttl_seconds=ttl_seconds,
        )
    except Exception as e:
        log.error(
            "session.csrf.token.save.failed",
            session_id=str(session_id),
            error=str(e),
        )

    log.info(
        "session.created",
        user_id=str(user_id),
        session_id=str(session_id),
        device_type=device_type,
        remember_me=remember_me,
    )

    return {
        "session_id": session_id,
        "csrf_token": csrf_token,
        "expires_at": expires_at,
        "user_id": user_id,
    }


async def get_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_session_id: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Получает список активных сессий пользователя.

    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        current_session_id: ID текущей сессии (для пометки)

    Returns:
        Список сессий пользователя
    """
    now = datetime.now(timezone.utc)

    stmt = (
        select(UserSessions)
        .where(
            UserSessions.user_id == user_id,
            UserSessions.is_active == True,
            UserSessions.expires_at > now,
        )
        .order_by(UserSessions.last_activity.desc())
    )

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    session_list = []
    for session in sessions:
        location = None
        if session.location_city and session.location_country:
            location = f"{session.location_city}, {session.location_country}"
        elif session.location_country:
            location = session.location_country

        session_info = {
            "session_id": session.session_id,
            "device_info": {
                "device_name": session.device_name,
                "device_type": session.device_type,
                "user_agent": session.user_agent,
                "ip_address": (
                    str(session.ip_address) if session.ip_address else None
                ),
                "location": location,
            },
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "is_current": session.session_id == current_session_id,
            "expires_at": session.expires_at,
        }
        session_list.append(session_info)

    return session_list


async def update_session_activity(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
) -> bool:
    """
    Обновляет время последней активности сессии.

    Args:
        db: Сессия базы данных
        session_id: ID сессии
        user_id: ID пользователя (для безопасности, опционально)

    Returns:
        True если сессия обновлена, False если не найдена
    """
    now = datetime.now(timezone.utc)

    # Формируем условия запроса
    conditions = [
        UserSessions.session_id == session_id,
        UserSessions.expires_at > now,
    ]
    if user_id:
        conditions.append(UserSessions.user_id == user_id)

    stmt = update(UserSessions).where(*conditions).values(last_activity=now)

    result = await db.execute(stmt)
    await db.flush()

    if result.rowcount > 0:
        return True
    else:
        if user_id:
            log.warning(
                "session.activity.update.not_found",
                session_id=str(session_id),
                user_id=str(user_id),
            )
        return False


async def terminate_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """
    Завершает конкретную сессию пользователя.

    Args:
        db: Сессия базы данных
        session_id: ID сессии для завершения
        user_id: ID пользователя (для проверки принадлежности)

    Returns:
        True если сессия завершена, False если не найдена
    """
    # Сначала получаем refresh_token_jti для добавления в blacklist
    stmt = select(UserSessions.refresh_token_jti).where(
        UserSessions.session_id == session_id,
        UserSessions.user_id == user_id,
        UserSessions.is_active == True,
    )

    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        return False

    refresh_token_jti = row

    # Обновляем сессию как неактивную
    update_stmt = (
        update(UserSessions)
        .where(
            UserSessions.session_id == session_id,
            UserSessions.user_id == user_id,
        )
        .values(is_active=False)
    )

    update_result = await db.execute(update_stmt)
    await db.flush()

    if update_result.rowcount > 0:
        # Добавляем refresh токен в blacklist
        await _blacklist_token_by_jti(refresh_token_jti, "refresh")

        log.info(
            "session.terminated",
            session_id=str(session_id),
            user_id=str(user_id),
            refresh_token_jti=refresh_token_jti,
        )
        return True

    return False


async def _blacklist_token_by_jti(jti: str, token_type: str) -> None:
    """
    Добавляет токен в blacklist по его JTI.

    Args:
        jti: JTI токена
        token_type: Тип токена ("access" или "refresh")
    """
    try:
        redis_client = get_main_redis()
        blacklist_key = f"token_blacklist:{jti}"

        # Устанавливаем TTL в 30 дней (больше чем max время жизни токена)
        ttl_seconds = 30 * 24 * 60 * 60  # 30 дней

        await redis_client.setex(
            blacklist_key, ttl_seconds, "session_terminated"
        )

        log.info(
            "token.blacklisted",
            jti=jti,
            token_type=token_type,
        )

    except Exception as e:
        log.error(
            "token.blacklist.failed",
            jti=jti,
            token_type=token_type,
            error=str(e),
        )


async def terminate_all_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    keep_session_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Завершает все сессии пользователя, кроме указанной.

    КРИТИЧЕСКИ ВАЖНО: Добавляет все refresh токены в blacklist для безопасности.

    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        keep_session_id: ID сессии, которую НЕ нужно завершать

    Returns:
        Количество завершенных сессий
    """
    # Формируем условия для select
    select_conditions = [
        UserSessions.user_id == user_id,
        UserSessions.is_active == True,
        UserSessions.refresh_token_jti.isnot(None),
    ]
    if keep_session_id:
        select_conditions.append(UserSessions.session_id != keep_session_id)

    # Получаем все JTI для blacklist
    select_stmt = select(UserSessions.refresh_token_jti).where(
        *select_conditions
    )

    select_result = await db.execute(select_stmt)
    refresh_jtis = [row for row in select_result.scalars().all()]

    log.info(
        "sessions.mass_termination.tokens_found",
        user_id=str(user_id),
        tokens_count=len(refresh_jtis),
    )

    # Добавляем все refresh токены в blacklist
    for jti in refresh_jtis:
        await _blacklist_token_by_jti(jti, "refresh")

    # Формируем условия для update
    update_conditions = [UserSessions.user_id == user_id]
    if keep_session_id:
        update_conditions.append(UserSessions.session_id != keep_session_id)

    # Деактивируем сессии
    update_stmt = (
        update(UserSessions).where(*update_conditions).values(is_active=False)
    )

    update_result = await db.execute(update_stmt)
    await db.flush()

    terminated_count = update_result.rowcount
    log.info(
        "sessions.all.terminated",
        user_id=str(user_id),
        kept_session_id=str(keep_session_id) if keep_session_id else None,
        terminated_count=terminated_count,
        blacklisted_tokens=len(refresh_jtis),
    )

    return terminated_count


async def get_session_by_refresh_jti(
    db: AsyncSession,
    refresh_token_jti: str,
) -> Optional[Dict[str, Any]]:
    """
    Находит сессию по JTI refresh токена.

    Args:
        db: Сессия базы данных
        refresh_token_jti: JTI refresh токена

    Returns:
        Данные сессии или None если не найдена
    """
    stmt = select(
        UserSessions.session_id,
        UserSessions.user_id,
        UserSessions.csrf_token,
        UserSessions.is_active,
        UserSessions.expires_at,
    ).where(UserSessions.refresh_token_jti == refresh_token_jti)

    result = await db.execute(stmt)
    row = result.one_or_none()

    if not row:
        return None

    return {
        "session_id": row.session_id,
        "user_id": row.user_id,
        "csrf_token": row.csrf_token,
        "is_active": row.is_active,
        "expires_at": row.expires_at,
    }


async def update_session_refresh_token(
    db: AsyncSession,
    session_id: uuid.UUID,
    new_refresh_token_jti: str,
    new_csrf_token: Optional[str] = None,
) -> bool:
    """
    Обновляет JTI refresh токена в сессии (для Token Rotation).

    Args:
        db: Сессия базы данных
        session_id: ID сессии
        new_refresh_token_jti: Новый JTI refresh токена
        new_csrf_token: Новый CSRF токен (опционально)

    Returns:
        True если обновлено, False если сессия не найдена
    """
    now = datetime.now(timezone.utc)

    # Формируем данные для обновления
    update_values = {
        "refresh_token_jti": new_refresh_token_jti,
        "last_activity": now,
    }
    if new_csrf_token:
        update_values["csrf_token"] = new_csrf_token

    stmt = (
        update(UserSessions)
        .where(UserSessions.session_id == session_id)
        .values(**update_values)
    )

    result = await db.execute(stmt)
    rows_affected = result.rowcount

    log.debug(
        "session.refresh_token.update.before_flush",
        session_id=str(session_id),
        new_refresh_token_jti=new_refresh_token_jti,
        new_csrf_token=new_csrf_token,
        rows_affected=rows_affected,
    )

    await db.flush()

    log.debug(
        "session.refresh_token.updated",
        session_id=str(session_id),
        rows_affected=rows_affected,
    )

    return rows_affected > 0


async def blacklist_token(
    db: AsyncSession,
    token_jti: str,
    token_type: str,
    user_id: uuid.UUID,
    expires_at: datetime,
    reason: Optional[str] = None,
) -> bool:
    """
    Добавляет токен в blacklist.

    Args:
        db: Сессия базы данных
        token_jti: JTI токена
        token_type: Тип токена (access/refresh)
        user_id: ID пользователя
        expires_at: Время истечения токена
        reason: Причина блокировки

    Returns:
        True если добавлен в blacklist
    """
    try:
        # Создаем запись через ORM
        blacklist_entry = TokenBlacklist(
            token_jti=token_jti,
            token_type=token_type,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason or "manual_blacklist",
        )

        db.add(blacklist_entry)
        await db.flush()

        log.info(
            "token.blacklisted.db",
            token_jti=token_jti,
            token_type=token_type,
            user_id=str(user_id),
            reason=reason,
        )

        return True

    except Exception as e:
        log.warning(
            "token.blacklist.db.failed",
            token_jti=token_jti,
            error=str(e),
        )
        await db.rollback()
        return False


async def is_token_blacklisted_db(
    db: AsyncSession,
    token_jti: str,
) -> bool:
    """
    Проверяет, находится ли токен в blacklist БД.

    Args:
        db: Сессия базы данных
        token_jti: JTI токена

    Returns:
        True если токен в blacklist
    """
    stmt = (
        select(TokenBlacklist.token_jti)
        .where(TokenBlacklist.token_jti == token_jti)
        .limit(1)
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def log_security_event(
    db: AsyncSession,
    event_type: str,
    user_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Логирует событие безопасности.

    Args:
        db: Сессия базы данных
        event_type: Тип события
        user_id: ID пользователя (опционально)
        session_id: ID сессии (опционально)
        details: Дополнительные детали в JSON
        ip_address: IP адрес
        user_agent: User-Agent

    Returns:
        True если событие залогировано
    """
    try:
        event_id = uuid.uuid4()

        # Создаем запись события через ORM
        security_event = SecurityEvents(
            id=event_id,
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.add(security_event)
        await db.flush()

        log.info(
            "security.event.logged",
            event_type=event_type,
            user_id=str(user_id) if user_id else None,
            session_id=str(session_id) if session_id else None,
        )

        return True

    except Exception as e:
        log.warning(
            "security.event.log.failed",
            event_type=event_type,
            error=str(e),
        )
        await db.rollback()
        return False


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """
    Очищает истекшие сессии.

    Args:
        db: Сессия базы данных

    Returns:
        Количество удаленных сессий
    """
    now = datetime.now(timezone.utc)

    stmt = delete(UserSessions).where(UserSessions.expires_at < now)

    result = await db.execute(stmt)
    await db.flush()

    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(
            "sessions.expired.cleaned",
            deleted_count=deleted_count,
        )

    return deleted_count


async def cleanup_expired_blacklist(db: AsyncSession) -> int:
    """
    Очищает истекшие записи blacklist.

    Args:
        db: Сессия базы данных

    Returns:
        Количество удаленных записей
    """
    now = datetime.now(timezone.utc)

    stmt = delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)

    result = await db.execute(stmt)
    await db.flush()

    deleted_count = result.rowcount
    if deleted_count > 0:
        log.info(
            "blacklist.expired.cleaned",
            deleted_count=deleted_count,
        )

    return deleted_count
