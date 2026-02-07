from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Markets(Base):
    """Справочник торговых площадок (бирж)."""

    __tablename__ = "markets"
    __table_args__ = {"schema": "trader_core"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Машиночитаемое имя, например 'moex_stock', 'moex_currency'
    market_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Уникальный код рынка",
        comment="Уникальный код рынка",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Описание торговой площадки",
        comment="Описание торговой площадки",
    )
