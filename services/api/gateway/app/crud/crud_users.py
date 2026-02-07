"""
CRUD операции для работы с пользователями.

Использует SQLAlchemy 2.0+ синтаксис с ORM моделями из tradeforge_db.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import Users
from tradeforge_logger import get_logger
from tradeforge_schemas.auth import UserCreate, UserUpdate

from app.core.security import hash_password, verify_password

log = get_logger(__name__)


async def create_user(db: AsyncSession, *, user_in: UserCreate) -> Users:
    """
    Создает нового пользователя в базе данных.

    Args:
        db: Асинхронная сессия базы данных
        user_in: Данные для создания пользователя

    Returns:
        Созданный объект Users

    Raises:
        ValueError: Если пользователь с таким email уже существует
    """
    # Проверяем, что пользователь с таким email не существует
    existing_user = await get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise ValueError(f"User with email {user_in.email} already exists")

    # Хешируем пароль
    hashed_password_str = hash_password(user_in.password)
    user_id = uuid.uuid4()

    # Создаем пользователя через ORM
    new_user = Users(
        id=user_id,
        email=user_in.email,
        hashed_password=hashed_password_str,
        is_active=True,
    )

    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    log.info("user.created", user_id=str(user_id), email=user_in.email)
    return new_user


async def get_user_by_email(
    db: AsyncSession, *, email: str
) -> Optional[Users]:
    """
    Получает пользователя по email.

    Args:
        db: Асинхронная сессия базы данных
        email: Email пользователя

    Returns:
        Объект Users или None если не найден
    """
    stmt = select(Users).where(Users.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(
    db: AsyncSession, *, user_id: uuid.UUID
) -> Optional[Users]:
    """
    Получает пользователя по ID.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя

    Returns:
        Объект Users или None если не найден
    """
    stmt = select(Users).where(Users.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, *, email: str, password: str
) -> Optional[Users]:
    """
    Аутентифицирует пользователя по email и паролю.

    Args:
        db: Асинхронная сессия базы данных
        email: Email пользователя
        password: Пароль пользователя

    Returns:
        Объект Users если аутентификация успешна, None иначе
    """
    user = await get_user_by_email(db, email=email)
    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    return user


async def update_user(
    db: AsyncSession, *, user_id: uuid.UUID, user_in: UserUpdate
) -> Optional[Users]:
    """
    Обновляет данные пользователя.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        user_in: Новые данные пользователя

    Returns:
        Обновленный объект Users или None если не найден
    """
    user = await get_user_by_id(db, user_id=user_id)
    if not user:
        return None

    update_data = user_in.model_dump(exclude_unset=True)

    # Если обновляется пароль, хешируем его
    if "password" in update_data:
        hashed_password_str = hash_password(update_data.pop("password"))
        update_data["hashed_password"] = hashed_password_str

    if not update_data:
        return user

    # Обновляем поля ORM объекта
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)

    log.info("user.updated", user_id=str(user_id))

    return user
