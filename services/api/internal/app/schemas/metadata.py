from pydantic import BaseModel, ConfigDict, Field


class SystemIndicatorResponse(BaseModel):
    """Схема для системного индикатора из справочника."""

    name: str = Field(
        ..., description="Уникальное имя семейства индикаторов, например 'sma'"
    )
    display_name: str = Field(
        ...,
        description="Человекочитаемое название, например 'Simple Moving Average'",
    )
    description: str | None = Field(
        None, description="Описание индикатора для пользователей"
    )
    category: str = Field(
        ..., description="Категория: trend, momentum, volatility, etc."
    )
    complexity: str = Field(
        ..., description="Уровень сложности: basic, intermediate, advanced"
    )
    parameters_schema: dict = Field(
        ..., description="JSON схема параметров с ограничениями"
    )
    output_schema: dict = Field(
        ..., description="JSON схема выходных значений"
    )
    key_template: str = Field(..., description="Шаблон генерации ключа")
    is_enabled: bool = Field(..., description="Включен ли индикатор")

    model_config = ConfigDict(from_attributes=True)
