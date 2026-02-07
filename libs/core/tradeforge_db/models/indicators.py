from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemIndicators(Base):
    """Системный справочник описаний типов индикаторов с их параметрами и ограничениями."""

    __tablename__ = "system_indicators"
    __table_args__ = {"schema": "trader_core"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        doc="Уникальное имя семейства индикаторов, например, 'sma', 'rsi'",
        comment="Уникальное имя семейства индикаторов",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Человекочитаемое название для фронтенда, например, 'Simple Moving Average'",
        comment="Человекочитаемое название индикатора",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        doc="Описание индикатора для пользователей",
        comment="Описание индикатора для пользователей",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="technical",
        doc="Категория индикатора: trend, momentum, volatility, volume, etc.",
        comment="Категория индикатора",
    )
    complexity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="basic",
        doc="Уровень сложности: basic, intermediate, advanced",
        comment="Уровень сложности индикатора",
    )
    parameters_schema: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="JSON схема параметров индикатора с ограничениями",
        comment="Схема параметров и их ограничения",
    )
    output_schema: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="JSON схема выходных значений индикатора",
        comment="Схема выходных значений",
    )
    key_template: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Шаблон для генерации indicator_key, например, '{name}_timeperiod_{timeperiod}_value'",
        comment="Шаблон генерации ключа",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Включен ли индикатор для использования",
        comment="Статус активности индикатора",
    )


class UsersIndicators(Base):
    """Экземпляры индикаторов, созданные пользователями с конкретными параметрами."""

    __tablename__ = "users_indicators"
    __table_args__ = {"schema": "trader_core"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    indicator_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        doc="Уникальный ключ экземпляра индикатора, например, 'sma_timeperiod_20_value'",
        comment="Уникальный ключ экземпляра индикатора",
    )
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Имя семейства индикаторов, ссылка на system_indicators.name",
        comment="Имя семейства индикаторов",
    )
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="Конкретные параметры экземпляра индикатора в формате JSON",
        comment="Параметры экземпляра индикатора",
    )
    is_hot: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="True, если индикатор нужно считать в real-time",
        comment="Флаг для RT-калькулятора",
    )
