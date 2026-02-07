from typing import Any

import pandas as pd
import pandas_ta as ta

from calc.base import BaseIndicator


class SuperTrendIndicator(BaseIndicator):
    """
    Расчёт SuperTrend индикатора (трендовый индикатор на основе ATR).

    Lookback Period Calculation:
        Формула: length × 2

        Обоснование:
        - SuperTrend = ATR(length) × multiplier + HL/2
        - ATR (Average True Range) требует прогрева за length периодов
        - length × 1: минимум для расчета ATR
        - length × 1: прогрев для стабилизации трендовых линий
        - SuperTrend генерирует dynamic support/resistance levels

        Пример для SuperTrend(10, 3.0):
        - Lookback = 20 свечей
        - Первые 10: расчет ATR для волатильности
        - Следующие 10: стабилизация трендовых уровней (long/short)
        - Direction flip происходит при пересечении цены с трендовой линией
    """

    name = "supertrend"

    def __init__(
        self, length: int = 10, multiplier: float = 3.0, **params: Any
    ):
        # Приводим length к int, так как pandas_ta требует int для этого параметра
        # JSONB из PostgreSQL может вернуть float для integer значений
        super().__init__(length=int(length), multiplier=multiplier, **params)

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "trend": f"{base_key}_trend",
            "direction": f"{base_key}_direction",
            "long": f"{base_key}_long",
            "short": f"{base_key}_short",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: length × 2."""
        return self.params["length"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["trend", "direction", "long", "short"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        trend_col = self.outputs["trend"]
        if trend_col in df.columns:
            return df

        st_df = df.ta.supertrend(
            length=self.params["length"], multiplier=self.params["multiplier"]
        )

        # Переименовываем колонки в соответствии с контрактом
        # pandas-ta возвращает 4 колонки в строгом порядке
        rename_map = {
            st_df.columns[0]: self.outputs["trend"],
            st_df.columns[1]: self.outputs["direction"],
            st_df.columns[2]: self.outputs["long"],
            st_df.columns[3]: self.outputs["short"],
        }
        st_df.rename(columns=rename_map, inplace=True)
        return pd.concat([df, st_df], axis=1)


class TSIIndicator(BaseIndicator):
    """
    Расчёт True Strength Index (TSI) - индикатор momentum с двойным сглаживанием.

    Lookback Period Calculation:
        Формула: (slow + signal) × 2

        Обоснование:
        - TSI использует двойное экспоненциальное сглаживание price momentum
        - TSI Line = 100 × (Double EMA of momentum / Double EMA of absolute momentum)
        - Signal Line = EMA(TSI, signal period)
        - slow: период для первого уровня сглаживания (самый долгий)
        - signal: период для signal line
        - × 2: консервативный множитель для nested EMA

        Пример для TSI(13, 25, 13):
        - Lookback = (25 + 13) × 2 = 76 свечей
        - Первые 25: прогрев slow double EMA
        - Следующие 13: прогрев signal line
        - × 2: стабилизация вложенных экспоненциальных сглаживаний
    """

    name = "tsi"

    def __init__(
        self, fast: int = 13, slow: int = 25, signal: int = 13, **params: Any
    ):
        # Приводим параметры к int для pandas_ta
        super().__init__(
            fast=int(fast), slow=int(slow), signal=int(signal), **params
        )

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "tsi": f"{base_key}_tsi",
            "signal": f"{base_key}_signal",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: (slow + signal) × 2."""
        return (self.params["slow"] + self.params["signal"]) * 2

    @property
    def value_keys(self) -> list[str]:
        return ["tsi", "signal"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        tsi_col = self.outputs["tsi"]
        if tsi_col in df.columns:
            return df

        tsi_df = ta.tsi(
            df["close"],
            fast=self.params["fast"],
            slow=self.params["slow"],
            signal=self.params["signal"],
        )

        rename_map = {
            tsi_df.columns[0]: self.outputs["tsi"],
            tsi_df.columns[1]: self.outputs["signal"],
        }
        tsi_df.rename(columns=rename_map, inplace=True)
        return pd.concat([df, tsi_df], axis=1)


class SqueezeMomentumIndicator(BaseIndicator):
    """
    Расчёт TTM Squeeze Momentum - индикатор сжатия волатильности.

    Lookback Period Calculation:
        Формула: 20 × 2 = 40 свечей

        Обоснование:
        - TTM Squeeze объединяет Bollinger Bands(20) и Keltner Channels(20)
        - Squeeze ON: когда Bollinger Bands находятся внутри Keltner Channels
        - Squeeze OFF: когда Bollinger Bands выходят за пределы Keltner
        - Momentum: линейная регрессия для определения направления
        - Самый длинный период = 20 (для обоих индикаторов)
        - × 2: стабилизация для расчета volatility squeeze

        Пример для Squeeze (lazybear=True):
        - Lookback = 40 свечей
        - Первые 20: расчет Bollinger Bands (SMA + StdDev)
        - Первые 20: расчет Keltner Channels (EMA + ATR)
        - Следующие 20: стабилизация для определения squeeze состояния
    """

    name = "squeeze"

    def __init__(self, **params: Any):
        super().__init__(**params)

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "squeeze": f"{base_key}_squeeze",
            "on": f"{base_key}_on",
            "off": f"{base_key}_off",
            "no": f"{base_key}_no",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей.
        Для lazybear=True, pandas-ta использует Bollinger Bands(20) и Keltner(20).
        Самый длинный период - 20. Умножаем на 2 для буфера.
        """
        return 20 * 2

    @property
    def value_keys(self) -> list[str]:
        return ["squeeze", "on", "off", "no"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        sqz_col = self.outputs["squeeze"]
        if sqz_col in df.columns:
            return df

        sqz_df = df.ta.squeeze(lazybear=True)

        rename_map = {
            # Имена колонок для lazybear=True фиксированы
            "SQZ_20_2.0_20_1.5_LB": self.outputs["squeeze"],
            "SQZ_ON": self.outputs["on"],
            "SQZ_OFF": self.outputs["off"],
            "SQZ_NO": self.outputs["no"],
        }
        # pandas_ta может не вернуть все колонки, если данных мало
        sqz_df.rename(
            columns={
                k: v for k, v in rename_map.items() if k in sqz_df.columns
            },
            inplace=True,
        )
        return pd.concat([df, sqz_df], axis=1)


class VortexIndicator(BaseIndicator):
    """
    Расчёт Vortex Indicator (VI+ и VI-) - индикатор направленного движения.

    Lookback Period Calculation:
        Формула: length × 2

        Обоснование:
        - Vortex измеряет bullish (VI+) и bearish (VI-) trend movement
        - VI+ = SUM(|High[i] - Low[i-1]|) / SUM(True Range)
        - VI- = SUM(|Low[i] - High[i-1]|) / SUM(True Range)
        - Использует rolling sum за length периодов
        - length × 1: минимум для rolling window
        - length × 1: прогрев для стабилизации vortex movement
        - Пересечение VI+ и VI- сигнализирует о смене тренда

        Пример для Vortex(14):
        - Lookback = 28 свечей
        - Первые 14: расчет rolling sum для vortex movement
        - Следующие 14: стабилизация для определения направления тренда
        - VI+ > VI-: восходящий тренд, VI- > VI+: нисходящий тренд
    """

    name = "vortex"

    def __init__(self, length: int = 14, **params: Any):
        # Приводим length к int для pandas_ta
        super().__init__(length=int(length), **params)

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "p": f"{base_key}_p",  # positive
            "m": f"{base_key}_m",  # minus (negative)
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: length × 2."""
        return self.params["length"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["p", "m"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        vtxp_col = self.outputs["p"]
        if vtxp_col in df.columns:
            return df

        vi_df = df.ta.vortex(length=self.params["length"])

        rename_map = {
            vi_df.columns[0]: self.outputs["p"],
            vi_df.columns[1]: self.outputs["m"],
        }
        vi_df.rename(columns=rename_map, inplace=True)
        return pd.concat([df, vi_df], axis=1)


class IchimokuIndicator(BaseIndicator):
    """
    Расчёт Ichimoku Kinko Hyo - комплексная система анализа тренда.

    Lookback Period Calculation:
        Формула: senkou × 2

        Обоснование:
        - Ichimoku состоит из 5 линий с разными периодами:
          * Tenkan-sen (конверсионная линия): (High + Low) / 2 за tenkan периодов
          * Kijun-sen (базовая линия): (High + Low) / 2 за kijun периодов
          * Senkou Span A: (Tenkan + Kijun) / 2, сдвинутая на kijun вперед
          * Senkou Span B: (High + Low) / 2 за senkou периодов, сдвинутая на kijun вперед
          * Chikou Span: Close price, сдвинутая на kijun назад
        - senkou — самый длинный период (обычно 52)
        - × 2: прогрев для стабилизации всех линий облака

        Пример для Ichimoku(9, 26, 52):
        - Lookback = 104 свечи
        - Первые 52: расчет Senkou Span B (самая долгая линия)
        - Следующие 52: стабилизация для формирования облака (Kumo)
        - Облако между Span A и Span B используется как динамическая поддержка/сопротивление
    """

    name = "ichimoku"

    def __init__(
        self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, **params: Any
    ):
        # Приводим параметры к int для pandas_ta
        super().__init__(
            tenkan=int(tenkan), kijun=int(kijun), senkou=int(senkou), **params
        )

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "span_a": f"{base_key}_span_a",
            "span_b": f"{base_key}_span_b",
            "tenkan": f"{base_key}_tenkan",
            "kijun": f"{base_key}_kijun",
            "chikou": f"{base_key}_chikou",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: senkou × 2."""
        return self.params["senkou"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["span_a", "span_b", "tenkan", "kijun", "chikou"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        spana_col = self.outputs["span_a"]
        if spana_col in df.columns:
            return df

        ichimoku_df, _ = df.ta.ichimoku(
            tenkan=self.params["tenkan"],
            kijun=self.params["kijun"],
            senkou=self.params["senkou"],
        )

        rename_map = {
            ichimoku_df.columns[0]: self.outputs["span_a"],
            ichimoku_df.columns[1]: self.outputs["span_b"],
            ichimoku_df.columns[2]: self.outputs["tenkan"],
            ichimoku_df.columns[3]: self.outputs["kijun"],
            ichimoku_df.columns[4]: self.outputs["chikou"],
        }
        ichimoku_df.rename(columns=rename_map, inplace=True)
        return pd.concat([df, ichimoku_df], axis=1)
