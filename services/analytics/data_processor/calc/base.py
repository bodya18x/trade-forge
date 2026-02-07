from __future__ import annotations

import abc
from typing import Any

import pandas as pd


class BaseIndicator(abc.ABC):
    """
    Абстрактный базовый класс для всех индикаторов с 'выходным контрактом'.
    """

    name: str  # Должен быть определен в подклассе, например, 'sma'

    def __init__(self, **params: Any):
        self.params: dict[str, Any] = params
        # `outputs` будет определен в __init__ дочернего класса
        self.outputs: dict[str, str] = {}
        self._initialize_outputs()

    @abc.abstractmethod
    def _initialize_outputs(self) -> None:
        """
        Инициализирует словарь self.outputs.
        Здесь определяется "выходной контракт" индикатора.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Выполняет расчет и добавляет колонки в DataFrame,
        используя имена из self.outputs.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def lookback(self) -> int:
        """Минимальное кол-во свечей для 'прогрева'."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def value_keys(self) -> list[str]:
        """Список ВСЕХ возможных 'value_key', которые производит индикатор."""
        raise NotImplementedError

    def get_value_keys(self) -> list[str]:
        """Возвращает список ключей значений из контракта. Надежно и просто."""
        return list(self.outputs.keys())

    def get_base_key(self) -> str:
        """Генерирует уникальный базовый ключ для этого экземпляра индикатора."""
        sorted_params = sorted(self.params.items())
        param_str = "_".join(f"{k}_{v}" for k, v in sorted_params)
        return f"{self.name}_{param_str}" if param_str else self.name


class IndicatorPipeline:
    """
    Хранит в себе набор (pipeline) индикаторов и последовательно применяет их
    к DataFrame. Можно легко расширять, добавляя в список новые индикаторы.
    """

    def __init__(self, indicators: list[BaseIndicator] | None = None):
        self.indicators = indicators or []

    def add_indicator(self, indicator: BaseIndicator) -> None:
        self.indicators.append(indicator)

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        for indicator in self.indicators:
            df = indicator.compute(df)
        return df
