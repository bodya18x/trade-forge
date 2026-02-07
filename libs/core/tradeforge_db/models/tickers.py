import enum

from sqlalchemy import (
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TickerType(enum.Enum):
    STOCK = "stock"
    CURRENCY = "currency"
    FUTURE = "future"
    OPTION = "option"
    BOND = "bond"


class Tickers(Base):
    """Справочник торгуемых инструментов (тикеров)."""

    __tablename__ = "tickers"
    __table_args__ = (
        UniqueConstraint("symbol", "market_id", name="uq_symbol_market_id"),
        {"schema": "trader_core"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Символ инструмента (тикер)",
        comment="Символ инструмента (тикер)",
    )

    market_id: Mapped[int] = mapped_column(
        ForeignKey("trader_core.markets.id", ondelete="RESTRICT"),
        doc="Внешний ключ к рынку",
        comment="FK на trader_core.markets",
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        doc="Краткое название компании/инструмента, например 'Сбербанк'",
        comment="Краткое название",
    )

    type: Mapped[TickerType] = mapped_column(
        Enum(
            TickerType,
            name="ticker_type_enum",
            create_type=True,
            schema="trader_core",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        doc="Тип инструмента (акция, валюта, фьючерс и т.д.)",
        comment="Тип инструмента",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Флаг активности (используется ли для сбора данных)",
        comment="Флаг активности сбора данных",
    )

    # Торговые параметры
    lot_size: Mapped[int | None] = mapped_column(
        Integer,
        doc="Размер лота (количество в одном лоте)",
        comment="Размер лота",
    )
    min_step: Mapped[float | None] = mapped_column(
        Float, doc="Минимальный шаг цены", comment="Минимальный шаг цены"
    )
    decimals: Mapped[int | None] = mapped_column(
        Integer,
        doc="Количество знаков после запятой в цене",
        comment="Точность цены",
    )

    # Идентификаторы
    isin: Mapped[str | None] = mapped_column(
        String(12),
        unique=True,
        doc="Международный идентификационный код ценной бумаги",
        comment="ISIN",
    )

    # Дополнительные поля, которые могут пригодиться
    currency: Mapped[str | None] = mapped_column(
        String(10),
        doc="Валюта, в которой торгуется инструмент (например, RUB, USD)",
        comment="Валюта торгов",
    )
    short_name: Mapped[str | None] = mapped_column(
        String(100),
        doc="Короткое имя, удобное для отображения (например, Сбербанк)",
        comment="Короткое имя",
    )
    list_level: Mapped[int | None] = mapped_column(
        Integer,
        doc="Уровень листинга (1, 2, 3)",
        comment="Уровень листинга",
    )
