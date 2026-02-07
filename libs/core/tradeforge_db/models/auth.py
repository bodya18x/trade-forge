import uuid

import sqlalchemy
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampTemplate


class Users(TimestampTemplate):
    """Модель пользователей системы."""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        index=True,
        nullable=False,
        doc="Email пользователя",
        comment="Email пользователя",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Хэш пароля пользователя",
        comment="Хэш пароля пользователя",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Активен ли пользователь",
        comment="Активен ли пользователь",
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Является ли пользователь администратором",
        comment="Является ли пользователь администратором",
    )
    subscription_tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
        doc="Тарифный план пользователя",
        comment="Тарифный план пользователя (free, pro, enterprise)",
    )
