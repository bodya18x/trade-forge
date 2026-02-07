"""
Модели для управления сессиями и безопасности.

- Управление пользовательскими сессиями
- Blacklist токенов
- Логирование событий безопасности
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

import sqlalchemy
from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampTemplate


class UserSessions(TimestampTemplate):
    """
    Модель для управления пользовательскими сессиями.

    Каждая сессия привязана к конкретному устройству и содержит:
    - Информацию об устройстве (user agent, IP, тип устройства)
    - Refresh token JTI для связи с токенами
    - CSRF токен для защиты от межсайтовых атак
    - Геолокацию и время последней активности
    """

    __tablename__ = "user_sessions"
    __table_args__ = {"schema": "auth"}

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Уникальный идентификатор сессии",
        comment="Уникальный идентификатор сессии",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="ID пользователя, владельца сессии",
        comment="ID пользователя, владельца сессии",
    )

    refresh_token_jti: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="JWT ID (JTI) текущего refresh токена сессии",
        comment="JWT ID (JTI) текущего refresh токена сессии",
    )

    # Device информация
    device_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Название устройства (например, 'MacBook Pro')",
        comment="Название устройства (например, 'MacBook Pro')",
    )

    device_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Тип устройства: desktop, mobile, tablet",
        comment="Тип устройства: desktop, mobile, tablet",
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="User-Agent браузера",
        comment="User-Agent браузера",
    )

    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        index=True,
        doc="IP адрес клиента",
        comment="IP адрес клиента",
    )

    # Геолокация
    location_country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Страна по геолокации IP",
        comment="Страна по геолокации IP",
    )

    location_city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Город по геолокации IP",
        comment="Город по геолокации IP",
    )

    # CSRF токен
    csrf_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="CSRF токен для защиты от межсайтовых атак",
        comment="CSRF токен для защиты от межсайтовых атак",
    )

    # Обогащенная информация об устройстве
    enriched_device_info: Mapped[Dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Обогащенная информация об устройстве с GeoIP, парсингом User-Agent и fingerprinting",
        comment="Обогащенная информация об устройстве с GeoIP, парсингом User-Agent и fingerprinting",
    )

    # Активность
    last_activity: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        server_default=sqlalchemy.sql.func.now(),
        nullable=False,
        index=True,
        doc="Время последней активности в сессии",
        comment="Время последней активности в сессии",
    )

    expires_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Время истечения сессии",
        comment="Время истечения сессии",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Активна ли сессия",
        comment="Активна ли сессия",
    )


class TokenBlacklist(TimestampTemplate):
    """
    Модель для blacklist токенов.

    Хранит инвалидированные токены для предотвращения их повторного использования.
    Альтернатива Redis для критически важных операций.
    """

    __tablename__ = "token_blacklist"
    __table_args__ = {"schema": "auth"}

    token_jti: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        doc="JWT ID (JTI) заблокированного токена",
        comment="JWT ID (JTI) заблокированного токена",
    )

    token_type: Mapped[str] = mapped_column(
        Enum("access", "refresh", name="token_type_enum"),
        nullable=False,
        doc="Тип токена: access или refresh",
        comment="Тип токена: access или refresh",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="ID пользователя, владельца токена",
        comment="ID пользователя, владельца токена",
    )

    expires_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Время истечения токена (для автоочистки)",
        comment="Время истечения токена (для автоочистки)",
    )

    reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Причина блокировки токена",
        comment="Причина блокировки токена",
    )


class SecurityEvents(TimestampTemplate):
    """
    Модель для логирования событий безопасности.

    Ведет аудит всех важных событий:
    - Логины и логауты
    - Обновления токенов
    - Подозрительную активность
    - Нарушения безопасности
    """

    __tablename__ = "security_events"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Уникальный идентификатор события",
        comment="Уникальный идентификатор события",
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey("auth.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="ID пользователя (может быть NULL для анонимных событий)",
        comment="ID пользователя (может быть NULL для анонимных событий)",
    )

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(
            "auth.user_sessions.session_id", ondelete="SET NULL"
        ),
        nullable=True,
        doc="ID сессии (если событие связано с сессией)",
        comment="ID сессии (если событие связано с сессией)",
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Тип события: login, logout, token_refresh, suspicious_activity, etc.",
        comment="Тип события: login, logout, token_refresh, suspicious_activity, etc.",
    )

    details: Mapped[Dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Дополнительные детали события в JSON формате",
        comment="Дополнительные детали события в JSON формате",
    )

    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        index=True,
        doc="IP адрес, с которого произошло событие",
        comment="IP адрес, с которого произошло событие",
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="User-Agent браузера",
        comment="User-Agent браузера",
    )
