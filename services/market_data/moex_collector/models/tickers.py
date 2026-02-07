"""
Модели для работы с тикерами MOEX.

Содержит Pydantic модели для валидации данных о тикерах с биржи.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MoexTicker(BaseModel):
    """Pydantic-модель для валидации и преобразования данных о тикере с API MOEX."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    symbol: str = Field(..., alias="SECID", description="Код тикера")
    description: str = Field(
        ..., alias="SECNAME", description="Полное наименование"
    )
    short_name: str = Field(
        ..., alias="SHORTNAME", description="Краткое наименование"
    )
    type: str = Field(default="stock", description="Тип инструмента")
    is_active: bool = Field(
        ..., alias="STATUS", description="Активен ли инструмент"
    )
    lot_size: int = Field(..., alias="LOTSIZE", description="Размер лота")
    min_step: float = Field(
        ..., alias="MINSTEP", description="Минимальный шаг цены"
    )
    decimals: int = Field(
        ..., alias="DECIMALS", description="Знаков после запятой"
    )
    isin: str | None = Field(None, alias="ISIN", description="ISIN код")
    currency: str = Field(..., alias="CURRENCYID", description="Валюта торгов")
    list_level: int = Field(
        ..., alias="LISTLEVEL", description="Уровень листинга"
    )

    @field_validator("is_active", mode="before")
    @classmethod
    def status_to_bool(cls, v: str) -> bool:
        """
        Преобразует статус MOEX в булево значение.

        Args:
            v: Статус из API MOEX ('A' = активен, другое = неактивен)

        Returns:
            True если активен, False иначе
        """
        return v == "A"

    @field_validator("currency", mode="before")
    @classmethod
    def currency_to_standard(cls, v: str) -> str:
        """
        Преобразует код валюты MOEX в стандартный формат.

        Args:
            v: Код валюты из API MOEX ('SUR' = рубль)

        Returns:
            Стандартный ISO код валюты
        """
        return "RUB" if v == "SUR" else v
