import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampTemplate


class Strategies(TimestampTemplate):
    """Модель пользовательских стратегий."""

    __tablename__ = "strategies"
    __table_args__ = (
        # Индекс для эффективной сортировки стратегий пользователя
        Index(
            "idx_strategies_user_sorting",
            "user_id",
            "is_deleted",
            "created_at",
            "name",
            postgresql_where=text("is_deleted = false"),
        ),
        # Индекс для поиска по имени в рамках пользователя
        Index(
            "idx_strategies_user_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "trader_core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        index=True,
        doc="Владелец стратегии",
        comment="FK на auth.users",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Название, данное пользователем",
        comment="Название, данное пользователем",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        doc="Описание стратегии",
        comment="Описание стратегии",
    )
    definition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="Определение стратегии в виде AST (Abstract Syntax Tree)",
        comment="AST стратегии из no-code редактора",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Флаг мягкого удаления стратегии",
        comment="True если стратегия была удалена пользователем",
    )
