"""
Эндпоинты аутентификации - Регистрация и вход в систему.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_schemas.auth import RegisterRequest, UserResponse

from app.core.redis import get_main_redis
from app.schemas.auth import ExtendedLoginRequest, ExtendedTokenResponse
from app.services.auth_service import AuthService

router = APIRouter()


def get_auth_service(
    redis: Annotated[Redis, Depends(get_main_redis)],
) -> AuthService:
    """Получает экземпляр сервиса аутентификации."""
    return AuthService(redis=redis)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
    description="""
    Создает новый аккаунт пользователя в системе Trade Forge.

    **Процесс регистрации:**
    1. Проверяет уникальность email адреса
    2. Валидирует пароль (минимум 8 символов)
    3. Хеширует пароль с использованием bcrypt
    4. Создает пользователя в базе данных
    5. Возвращает информацию о созданном пользователе

    **Требования к паролю:**
    - Минимальная длина: 8 символов
    - Рекомендуется использовать комбинацию букв, цифр и специальных символов

    **После регистрации:**
    - Используйте `/auth/login` для получения токенов доступа
    - ID пользователя будет использоваться для авторизации во всех защищенных эндпоинтах
    """,
)
async def register(
    request: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Регистрирует нового пользователя в системе.

    - Проверяет уникальность email
    - Хеширует пароль с использованием bcrypt
    - Создает пользователя в базе данных
    - Возвращает информацию о созданном пользователе
    """
    user_data = await auth_service.register_user(
        db=db, email=request.email, password=request.password
    )
    return UserResponse(**user_data)


@router.post(
    "/login",
    response_model=ExtendedTokenResponse,
    summary="Расширенная авторизация пользователя",
    description="""
    Авторизует пользователя с полной поддержкой session management.

    **Возможности:**
    - Device fingerprinting и отслеживание устройств
    - Session management с привязкой к устройствам
    - CSRF protection для безопасности
    - Логирование событий безопасности
    - Поддержка "remember me" режима

    **Процесс авторизации:**
    1. Проверяет существование пользователя по email
    2. Сверяет пароль с хешем в базе
    3. Создает сессию в БД с информацией об устройстве
    4. Создает пару JWT токенов с привязкой к сессии
    5. Генерирует CSRF токен для защиты
    6. Логирует событие входа в систему

    **Токены:**
    - **Access Token**: используйте для авторизации API запросов (15 мин)
    - **Refresh Token**: используйте для обновления access токенов (7-30 дней)
    - **CSRF Token**: используйте для критичных операций

    **Использование:**
    - Добавьте в заголовок: `Authorization: Bearer <access_token>`
    - Сохраните session_id и csrf_token для управления сессией
    """,
)
async def login_extended(
    request: ExtendedLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    http_request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Авторизует пользователя с полной поддержкой session management.

    - Проверяет email и пароль
    - Создает сессию в БД с device info
    - Создает JWT токены с session binding
    - Генерирует CSRF токен
    - Логирует событие безопасности
    """
    # Подготавливаем HTTP заголовки для обогащения device_info
    http_headers = {
        "user-agent": http_request.headers.get("user-agent", ""),
        "x-forwarded-for": http_request.headers.get("x-forwarded-for", ""),
        "x-real-ip": http_request.headers.get("x-real-ip", ""),
    }

    token_data = await auth_service.login_user(
        db=db,
        email=request.email,
        password=request.password,
        device_info=(
            request.device_info.model_dump() if request.device_info else None
        ),
        remember_me=request.remember_me,
        http_headers=http_headers,
    )

    return ExtendedTokenResponse(**token_data)
