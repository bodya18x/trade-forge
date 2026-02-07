"""
Унифицированные Pydantic схемы для аутентификации и пользователей.

Содержит схемы для регистрации, аутентификации и управления пользователями.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# === БАЗОВЫЕ СХЕМЫ ПОЛЬЗОВАТЕЛЯ ===


class UserBase(BaseModel):
    """Базовая схема пользователя с общими полями."""

    email: EmailStr = Field(..., description="Email адрес пользователя")


class UserCreate(UserBase):
    """Схема для создания нового пользователя."""

    password: str = Field(
        ..., min_length=8, max_length=128, description="Пароль пользователя"
    )


class UserUpdate(BaseModel):
    """Схема для обновления информации пользователя."""

    email: EmailStr | None = Field(None, description="Новый email адрес")
    password: str | None = Field(
        None, min_length=8, max_length=128, description="Новый пароль"
    )


class UserResponse(UserBase):
    """Схема пользователя в ответах API."""

    id: uuid.UUID = Field(
        ..., description="Уникальный идентификатор пользователя"
    )
    is_active: bool = Field(..., description="Активен ли аккаунт пользователя")
    created_at: datetime = Field(..., description="Время создания аккаунта")
    updated_at: datetime = Field(
        ..., description="Время последнего обновления"
    )

    model_config = {"from_attributes": True}


# === СХЕМЫ АУТЕНТИФИКАЦИИ ===


class LoginRequest(BaseModel):
    """Запрос на аутентификацию пользователя."""

    email: EmailStr = Field(..., description="Email адрес")
    password: str = Field(..., description="Пароль")


class RegisterRequest(BaseModel):
    """Запрос на регистрацию нового пользователя."""

    email: EmailStr = Field(..., description="Email адрес")
    password: str = Field(
        ..., min_length=8, max_length=128, description="Пароль"
    )


class TokenResponse(BaseModel):
    """Ответ с токенами аутентификации."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(
        ..., description="Время жизни access token в секундах"
    )


class RefreshTokenRequest(BaseModel):
    """Запрос на обновление токена."""

    refresh_token: str = Field(..., description="JWT refresh token")


# === СХЕМЫ ДЛЯ ПРОФИЛЯ ===


class ProfileResponse(UserResponse):
    """Полная информация профиля пользователя."""

    # Здесь могут быть дополнительные поля профиля в будущем
    # например: first_name, last_name, avatar_url, timezone и т.д.
    pass


class ProfileUpdateRequest(BaseModel):
    """Запрос на обновление профиля пользователя."""

    email: EmailStr | None = Field(None, description="Новый email адрес")
    # Здесь могут быть дополнительные поля профиля в будущем


# === СХЕМЫ ДЛЯ АДМИНИСТРИРОВАНИЯ ===


class UserAdminResponse(UserResponse):
    """Расширенная информация о пользователе для админов."""

    is_superuser: bool = Field(
        False, description="Является ли пользователь суперпользователем"
    )
    last_login_at: datetime | None = Field(
        None, description="Время последнего входа"
    )
    registration_ip: str | None = Field(
        None, description="IP адрес при регистрации"
    )


class UserCreateAdmin(UserBase):
    """Схема для создания пользователя администратором."""

    password: str = Field(
        ..., min_length=8, max_length=128, description="Пароль пользователя"
    )
    is_active: bool = Field(True, description="Активен ли аккаунт")
    is_superuser: bool = Field(False, description="Суперпользователь")


# === СХЕМЫ ДЛЯ СБРОСА ПАРОЛЯ ===


class PasswordResetRequest(BaseModel):
    """Запрос на сброс пароля."""

    email: EmailStr = Field(..., description="Email адрес для сброса пароля")


class PasswordResetConfirm(BaseModel):
    """Подтверждение сброса пароля с новым паролем."""

    token: str = Field(..., description="Токен сброса пароля")
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="Новый пароль"
    )


class PasswordChangeRequest(BaseModel):
    """Запрос на смену пароля (для авторизованного пользователя)."""

    current_password: str = Field(..., description="Текущий пароль")
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="Новый пароль"
    )
