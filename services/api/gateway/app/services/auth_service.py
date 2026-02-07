"""
Сервис аутентификации - Бизнес-логика для операций регистрации, входа и управления сессиями.
Инкапсулирует всю логику работы с токенами, сессиями и CSRF защитой.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from jose import jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_logger import get_logger
from tradeforge_schemas.auth import UserCreate, UserResponse

from app.core.auth import create_token_pair, verify_refresh_token
from app.crud.crud_sessions import (
    blacklist_token,
    create_user_session,
    get_session_by_refresh_jti,
    log_security_event,
    terminate_all_user_sessions,
    terminate_session,
    update_session_refresh_token,
)
from app.crud.crud_users import authenticate_user, create_user
from app.settings import settings

log = get_logger(__name__)


class AuthService:
    """
    Сервис бизнес-логики для аутентификации и управления сессиями.

    Этот сервис инкапсулирует всю логику работы с:
    - Регистрацией и аутентификацией пользователей
    - JWT токенами и их ротацией
    - Сессиями в базе данных
    - CSRF защитой
    - Security events logging
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    def _enrich_device_info(
        self,
        device_info: Optional[Dict[str, Any]],
        http_headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Обогащает device_info данными из HTTP заголовков.

        Args:
            device_info: Информация об устройстве от клиента
            http_headers: HTTP заголовки запроса

        Returns:
            Обогащенная информация об устройстве
        """
        device_info_dict = device_info.copy() if device_info else {}

        # Добавляем User-Agent если не передан
        if not device_info_dict.get("user_agent"):
            user_agent = http_headers.get("user-agent", "")
            if user_agent:
                device_info_dict["user_agent"] = user_agent

        # Добавляем IP адрес из заголовков
        if not device_info_dict.get("ip_address"):
            # Проверяем X-Forwarded-For для прокси
            forwarded_for = http_headers.get("x-forwarded-for")
            if forwarded_for:
                # Берем первый IP из списка (клиентский IP)
                client_ip = forwarded_for.split(",")[0].strip()
                device_info_dict["ip_address"] = client_ip
            else:
                # Fallback на direct connection IP
                client_ip = http_headers.get("x-real-ip")
                if client_ip:
                    device_info_dict["ip_address"] = client_ip

        return device_info_dict

    async def register_user(
        self, db: AsyncSession, email: str, password: str
    ) -> Dict[str, Any]:
        """
        Регистрирует нового пользователя в системе.

        Args:
            db: Database session
            email: Email пользователя
            password: Пароль

        Returns:
            Данные созданного пользователя

        Raises:
            HTTPException: При ошибках валидации или дублировании email
        """
        try:
            user_create = UserCreate(email=email, password=password)
            user = await create_user(db, user_in=user_create)

            log.info(
                "user.registered",
                user_id=str(user.id),
                email=user.email,
            )

            return UserResponse.model_validate(user).model_dump()

        except ValueError as e:
            log.warning("user.registration.failed", email=email, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    async def login_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        device_info: Optional[Dict[str, Any]],
        remember_me: bool,
        http_headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Авторизует пользователя с полной поддержкой session management.

        Args:
            db: Database session
            email: Email пользователя
            password: Пароль
            device_info: Информация об устройстве
            remember_me: Флаг "запомнить меня"
            http_headers: HTTP заголовки для обогащения device_info

        Returns:
            Словарь с токенами, session_id, csrf_token и user info

        Raises:
            HTTPException: При неверных credentials
        """
        # Аутентификация пользователя
        user = await authenticate_user(db, email=email, password=password)

        if not user:
            # Логируем неудачную попытку входа
            enriched_device_info = self._enrich_device_info(
                device_info, http_headers
            )

            await log_security_event(
                db=db,
                event_type="login_failed",
                details={
                    "email": email,
                    "reason": "invalid_credentials",
                    "device_info": enriched_device_info,
                },
                ip_address=enriched_device_info.get("ip_address"),
                user_agent=enriched_device_info.get("user_agent"),
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Обогащаем device_info с HTTP заголовками
        enriched_device_info = self._enrich_device_info(
            device_info, http_headers
        )

        # Создаем первую пару токенов (без session_id)
        _, _, initial_refresh_jti = create_token_pair(
            user_id=user.id,
            email=user.email,
            remember_me=remember_me,
        )

        # Создаем сессию в БД
        session_data = await create_user_session(
            db=db,
            user_id=user.id,
            refresh_token_jti=initial_refresh_jti,
            device_info=enriched_device_info if enriched_device_info else None,
            remember_me=remember_me,
            ip_address=enriched_device_info.get("ip_address"),
        )

        # Пересоздаем токены с session_id
        access_token, refresh_token, new_refresh_jti = create_token_pair(
            user_id=user.id,
            email=user.email,
            session_id=session_data["session_id"],
            remember_me=remember_me,
        )

        # Обновляем сессию с новым refresh JTI
        await update_session_refresh_token(
            db=db,
            session_id=session_data["session_id"],
            new_refresh_token_jti=new_refresh_jti,
        )

        # Логируем успешный вход
        await log_security_event(
            db=db,
            event_type="login_success",
            user_id=user.id,
            session_id=session_data["session_id"],
            details={
                "device_info": enriched_device_info,
                "remember_me": remember_me,
            },
            ip_address=enriched_device_info.get("ip_address"),
            user_agent=enriched_device_info.get("user_agent"),
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
            "session_id": session_data["session_id"],
            "csrf_token": session_data["csrf_token"],
            "user": {
                "id": str(user.id),
                "email": user.email,
                "last_login": datetime.now(timezone.utc).isoformat(),
            },
        }

    async def refresh_tokens(
        self, db: AsyncSession, refresh_token: str
    ) -> Dict[str, Any]:
        """
        Обновляет токены с Refresh Token Rotation.

        Args:
            db: Database session
            refresh_token: Текущий refresh token

        Returns:
            Словарь с новыми токенами, session_id, csrf_token

        Raises:
            HTTPException: При невалидном токене или обнаружении атаки
        """
        # Проверяем refresh token
        payload = await verify_refresh_token(refresh_token)
        if not payload:
            log.warning("token.refresh.invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Извлекаем JTI из токена
        try:
            token_data = jwt.decode(
                refresh_token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            old_jti = token_data.get("jti")
            token_exp = datetime.fromtimestamp(
                token_data.get("exp"), tz=timezone.utc
            )
        except Exception as e:
            log.warning("token.refresh.decode.failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Находим сессию по JTI refresh токена
        session_data = await get_session_by_refresh_jti(db, old_jti)
        if not session_data:
            # КРИТИЧНО: Токен не найден в сессиях - возможная атака
            # Завершаем ВСЕ сессии пользователя при подозрении на атаку
            terminated_count = await terminate_all_user_sessions(
                db, uuid.UUID(payload.user_id)
            )

            await log_security_event(
                db=db,
                event_type="token_reuse_detected",
                user_id=uuid.UUID(payload.user_id),
                details={
                    "reason": "refresh_token_not_in_session",
                    "old_jti": old_jti,
                    "action": "terminate_all_sessions",
                    "terminated_sessions": terminated_count,
                },
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security violation detected. Please login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Добавляем старый refresh токен в blacklist
        await blacklist_token(
            db=db,
            token_jti=old_jti,
            token_type="refresh",
            user_id=session_data["user_id"],
            expires_at=token_exp,
            reason="token_rotation",
        )

        # Создаем новые токены
        access_token, new_refresh_token, new_refresh_jti = create_token_pair(
            user_id=session_data["user_id"],
            email=payload.email,
            session_id=session_data["session_id"],
        )

        # Генерируем новый CSRF токен
        new_csrf_token = secrets.token_hex(32)

        # Обновляем сессию с новым refresh токеном и CSRF токеном
        session_updated = await update_session_refresh_token(
            db=db,
            session_id=session_data["session_id"],
            new_refresh_token_jti=new_refresh_jti,
            new_csrf_token=new_csrf_token,
        )

        if not session_updated:
            log.error(
                "session.update.failed.during_refresh",
                session_id=str(session_data["session_id"]),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update session",
            )

        # Обновляем CSRF токен в Redis
        csrf_key = f"csrf_token:{session_data['session_id']}"
        expires_in = 3600  # 1 час
        await self.redis.setex(csrf_key, expires_in, new_csrf_token)

        # Логируем успешное обновление токена
        await log_security_event(
            db=db,
            event_type="token_refresh_success",
            user_id=session_data["user_id"],
            session_id=session_data["session_id"],
            details={
                "old_jti": old_jti,
                "new_jti": new_refresh_jti,
            },
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
            "session_id": session_data["session_id"],
            "csrf_token": new_csrf_token,
            "user": {
                "id": str(session_data["user_id"]),
                "email": payload.email,
                "last_login": datetime.now(timezone.utc).isoformat(),
            },
        }

    async def logout_user(
        self, db: AsyncSession, refresh_token: str, logout_all_devices: bool
    ) -> Dict[str, Any]:
        """
        Выполняет расширенный выход пользователя из системы.

        Args:
            db: Database session
            refresh_token: Refresh token для завершения сессии
            logout_all_devices: Завершить все сессии или только текущую

        Returns:
            Словарь с результатом logout операции
        """
        sessions_terminated = 0

        try:
            # Проверяем refresh токен
            payload = await verify_refresh_token(refresh_token)
            if not payload:
                # Даже если токен невалидный, считаем logout успешным
                log.info("user.logout.with_invalid_token")
                return {
                    "message": "Successfully logged out",
                    "success": True,
                    "sessions_terminated": 0,
                }

            # Извлекаем JTI из токена
            try:
                token_data = jwt.decode(
                    refresh_token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                refresh_jti = token_data.get("jti")
                token_exp = datetime.fromtimestamp(
                    token_data.get("exp"), tz=timezone.utc
                )
            except Exception as e:
                log.warning(
                    "token.refresh.decode.failed.during_logout", error=str(e)
                )
                return {
                    "message": "Successfully logged out",
                    "success": True,
                    "sessions_terminated": 0,
                }

            user_id = uuid.UUID(payload.user_id)

            # Находим сессию по JTI
            session_data = await get_session_by_refresh_jti(db, refresh_jti)

            if logout_all_devices:
                # Завершаем ВСЕ сессии пользователя
                sessions_terminated = await terminate_all_user_sessions(
                    db, user_id
                )

                # Логируем массовое завершение сессий
                await log_security_event(
                    db=db,
                    event_type="logout_all_devices",
                    user_id=user_id,
                    session_id=(
                        session_data["session_id"] if session_data else None
                    ),
                    details={
                        "sessions_terminated": sessions_terminated,
                        "reason": "user_requested_logout_all",
                    },
                )

            else:
                # Завершаем только текущую сессию
                if session_data:
                    success = await terminate_session(
                        db, session_data["session_id"], user_id
                    )
                    sessions_terminated = 1 if success else 0

                    # Логируем завершение сессии
                    await log_security_event(
                        db=db,
                        event_type="logout_single_session",
                        user_id=user_id,
                        session_id=session_data["session_id"],
                        details={"refresh_jti": refresh_jti},
                    )

            # Добавляем refresh токен в blacklist
            if refresh_jti and token_exp:
                await blacklist_token(
                    db=db,
                    token_jti=refresh_jti,
                    token_type="refresh",
                    user_id=user_id,
                    expires_at=token_exp,
                    reason="logout",
                )

            return {
                "message": "Successfully logged out",
                "success": True,
                "sessions_terminated": sessions_terminated,
            }

        except Exception as e:
            log.warning("user.logout.failed", error=str(e))
            # Не возвращаем ошибку пользователю для безопасности
            return {
                "message": "Successfully logged out",
                "success": True,
                "sessions_terminated": 0,
            }

    async def generate_csrf_token(
        self, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Генерирует новый CSRF токен для сессии.

        Args:
            user_id: ID пользователя
            session_id: ID сессии

        Returns:
            Словарь с csrf_token и expires_in
        """
        # Удаляем старые CSRF токены для этой сессии
        old_csrf_pattern = f"csrf_token:{session_id}"
        old_csrf_keys = await self.redis.keys(old_csrf_pattern)

        if old_csrf_keys:
            await self.redis.delete(*old_csrf_keys)
            log.info(
                "csrf.tokens.old.deleted",
                user_id=str(user_id),
                session_id=str(session_id),
                deleted_count=len(old_csrf_keys),
            )

        # Генерируем новый CSRF токен
        csrf_token = secrets.token_hex(32)
        expires_in = 3600  # 1 час

        # Сохраняем новый CSRF токен в Redis
        csrf_key = f"csrf_token:{session_id}"
        await self.redis.setex(csrf_key, expires_in, csrf_token)

        log.info(
            "csrf.token.generated",
            user_id=str(user_id),
            session_id=str(session_id),
            csrf_token_key=csrf_key,
        )

        return {"csrf_token": csrf_token, "expires_in": expires_in}

    async def refresh_csrf_token(
        self, db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Обновляет CSRF токен для сессии (POST метод).

        Args:
            db: Database session
            user_id: ID пользователя
            session_id: ID сессии

        Returns:
            Словарь с новым csrf_token и expires_in
        """
        # Удаляем старые CSRF токены для этой сессии
        old_csrf_pattern = f"csrf_token:{session_id}:*"
        old_csrf_keys = await self.redis.keys(old_csrf_pattern)

        if old_csrf_keys:
            await self.redis.delete(*old_csrf_keys)

        # Генерируем новый CSRF токен
        csrf_token = secrets.token_hex(32)
        expires_in = 3600  # 1 час

        # Сохраняем новый CSRF токен в Redis
        csrf_key = f"csrf_token:{session_id}"
        await self.redis.setex(csrf_key, expires_in, csrf_token)

        # Логируем аудит безопасности
        await log_security_event(
            db=db,
            event_type="csrf_token_refreshed",
            user_id=user_id,
            session_id=session_id,
            details={
                "method": "POST",
                "old_tokens_deleted": (
                    len(old_csrf_keys) if old_csrf_keys else 0
                ),
                "expires_in": expires_in,
            },
        )

        return {"csrf_token": csrf_token, "expires_in": expires_in}
