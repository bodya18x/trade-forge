"""
Локальные схемы аутентификации для Gateway API.

Содержит схемы, специфичные только для Gateway API,
которые не используются в других сервисах проекта.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# Новые схемы для Session Management
class DeviceInfo(BaseModel):
    """Информация об устройстве пользователя."""

    user_agent: Optional[str] = Field(
        None, description="User-Agent браузера", max_length=2000
    )
    ip_address: Optional[str] = Field(None, description="IP адрес клиента")
    device_name: Optional[str] = Field(
        None,
        description="Название устройства (например, 'MacBook Pro')",
        max_length=255,
    )
    device_type: Optional[str] = Field(
        None,
        description="Тип устройства: desktop, mobile, tablet",
        max_length=50,
    )


class ExtendedLoginRequest(BaseModel):
    """Расширенный запрос на авторизацию с device info."""

    email: str = Field(..., description="Email пользователя")
    password: str = Field(
        ..., description="Пароль пользователя", max_length=72
    )
    device_info: Optional[DeviceInfo] = Field(
        None, description="Информация об устройстве пользователя"
    )
    remember_me: bool = Field(
        default=False,
        description="Запомнить пользователя (увеличить время жизни refresh токена)",
    )


class ExtendedTokenResponse(BaseModel):
    """Расширенный ответ с токенами и session info."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(
        ..., description="Время жизни access токена в секундах"
    )
    session_id: uuid.UUID = Field(..., description="ID созданной сессии")
    csrf_token: str = Field(..., description="CSRF токен для защиты")
    user: Dict[str, Any] = Field(..., description="Информация о пользователе")


class ExtendedRefreshRequest(BaseModel):
    """
    Запрос на обновление токена с Refresh Token Rotation.

    ВАЖНО: CSRF токен НЕ требуется для refresh операции, т.к.:
    - Refresh token передается вручную в JSON body (не автоматически как cookie)
    - Refresh Token Rotation обеспечивает защиту (каждый токен используется 1 раз)
    - CSRF атака невозможна без знания refresh token
    - JTI проверяется в БД, повторное использование → terminate все сессии
    """

    refresh_token: str = Field(..., description="Текущий refresh token")


class ExtendedLogoutRequest(BaseModel):
    """Расширенный запрос на выход из системы."""

    refresh_token: str = Field(
        ..., description="JWT refresh token для инвалидации"
    )
    logout_all_devices: bool = Field(
        default=False, description="Завершить все сессии пользователя"
    )


class ExtendedLogoutResponse(BaseModel):
    """Расширенный ответ при выходе из системы."""

    message: str = Field(
        default="Successfully logged out",
        description="Сообщение об успешном выходе",
    )
    success: bool = Field(default=True, description="Статус операции выхода")
    sessions_terminated: int = Field(
        default=1, description="Количество завершенных сессий"
    )


class SessionInfo(BaseModel):
    """Информация о пользовательской сессии."""

    session_id: uuid.UUID = Field(..., description="ID сессии")
    device_info: DeviceInfo = Field(
        ..., description="Информация об устройстве"
    )
    created_at: datetime = Field(..., description="Время создания сессии")
    last_activity: datetime = Field(
        ..., description="Время последней активности"
    )
    is_current: bool = Field(..., description="Является ли текущей сессией")
    expires_at: datetime = Field(..., description="Время истечения сессии")
    location: Optional[str] = Field(
        None, description="Геолокация (город, страна)"
    )


class SessionsListResponse(BaseModel):
    """Список активных сессий пользователя."""

    sessions: list[SessionInfo] = Field(..., description="Список сессий")
    total_sessions: int = Field(..., description="Общее количество сессий")


class TerminateSessionResponse(BaseModel):
    """Ответ при завершении сессии."""

    message: str = Field(..., description="Сообщение о результате")
    success: bool = Field(..., description="Статус операции")
    session_id: uuid.UUID = Field(..., description="ID завершенной сессии")


class TerminateAllSessionsRequest(BaseModel):
    """Запрос на завершение всех сессий."""

    keep_current: bool = Field(
        default=True, description="Сохранить текущую сессию"
    )


class TerminateAllSessionsResponse(BaseModel):
    """Ответ при завершении всех сессий."""

    message: str = Field(..., description="Сообщение о результате")
    success: bool = Field(..., description="Статус операции")
    sessions_terminated: int = Field(
        ..., description="Количество завершенных сессий"
    )
    current_session_kept: bool = Field(
        ..., description="Сохранена ли текущая сессия"
    )


# Схемы для CSRF Protection
class CSRFTokenResponse(BaseModel):
    """Ответ с CSRF токеном."""

    csrf_token: str = Field(..., description="CSRF токен")
    expires_in: int = Field(..., description="Время жизни токена в секундах")


class ValidateCSRFRequest(BaseModel):
    """Запрос на валидацию CSRF токена."""

    csrf_token: str = Field(..., description="CSRF токен для валидации")
    action: str = Field(..., description="Действие, которое требует валидации")
    resource_id: Optional[str] = Field(
        None, description="ID ресурса для действия"
    )


class ValidateCSRFResponse(BaseModel):
    """Ответ валидации CSRF токена."""

    valid: bool = Field(..., description="Валиден ли токен")
    action_permitted: bool = Field(..., description="Разрешено ли действие")


# Схемы для Token Blacklisting (admin endpoints)
class BlacklistTokenRequest(BaseModel):
    """Запрос на принудительную блокировку токена."""

    token_jti: str = Field(..., description="JWT ID для блокировки")
    reason: str = Field(..., description="Причина блокировки")


class BlacklistTokenResponse(BaseModel):
    """Ответ блокировки токена."""

    message: str = Field(..., description="Сообщение о результате")
    success: bool = Field(..., description="Статус операции")


class TokenStatusResponse(BaseModel):
    """Статус токена."""

    token_jti: str = Field(..., description="JWT ID токена")
    status: str = Field(
        ..., description="Статус: active, blacklisted, expired"
    )
    blacklisted_at: Optional[datetime] = Field(
        None, description="Время блокировки"
    )
    expires_at: datetime = Field(..., description="Время истечения")


# Старые схемы для backward compatibility
class LogoutRequest(BaseModel):
    """Запрос на выход из системы."""

    refresh_token: str = Field(
        ..., description="JWT refresh token для инвалидации"
    )


class LogoutResponse(BaseModel):
    """Ответ при выходе из системы."""

    message: str = Field(
        default="Successfully logged out",
        description="Сообщение об успешном выходе",
    )
    success: bool = Field(default=True, description="Статус операции выхода")


class CurrentUserInfo(BaseModel):
    """
    Информация о текущем пользователе из JWT токена.

    Используется для строгой типизации current_user в зависимостях и эндпоинтах.
    """

    id: uuid.UUID = Field(..., description="UUID пользователя")
    email: str = Field(..., description="Email пользователя")
    is_active: bool = Field(..., description="Активность пользователя")
    is_admin: bool = Field(default=False, description="Админские права")
    subscription_tier: str = Field(
        default="free", description="Тарифный план пользователя"
    )
    created_at: datetime = Field(..., description="Дата создания аккаунта")
    updated_at: datetime = Field(..., description="Дата последнего обновления")
    session_id: Optional[uuid.UUID] = Field(
        None, description="UUID сессии (если используется extended auth)"
    )
