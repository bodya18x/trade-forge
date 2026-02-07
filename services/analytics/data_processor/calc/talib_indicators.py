from typing import Any

import pandas as pd
import talib

from calc.base import BaseIndicator


class RSIIndicator(BaseIndicator):
    """
    Расчёт Relative Strength Index (RSI).

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - timeperiod × 1: минимум для первого расчета RSI
        - timeperiod × 1: дополнительно для прогрева внутренней EMA
        - RSI использует экспоненциальное сглаживание, требующее прогрева

        Пример для RSI(14):
        - Lookback = 28 свечей
        - Первые 14: начальный расчет
        - Следующие 14: стабилизация EMA
        - С 29-й свечи: полностью стабильные значения
    """

    name = "rsi"

    def __init__(self, timeperiod: int = 14, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей для прогрева: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        close_array = df["close"].astype(float).values
        rsi_values = talib.RSI(
            close_array, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = rsi_values
        return df


class MACDIndicator(BaseIndicator):
    """
    Расчёт Moving Average Convergence/Divergence (MACD).

    Lookback Period Calculation:
        Формула: (slowperiod + signalperiod) × 2

        Обоснование:
        - MACD = EMA(fast) - EMA(slow)
        - Signal = EMA(MACD, signalperiod)
        - slowperiod: прогрев медленной EMA (самая долгая)
        - signalperiod: прогрев signal line (EMA от MACD)
        - × 2: консервативный множитель для стабилизации вложенных EMA

        Пример для MACD(12, 26, 9):
        - Lookback = (26 + 9) × 2 = 70 свечей
        - Первые 26: прогрев slow EMA
        - Следующие 9: прогрев signal EMA
        - × 2: обеспечивает стабильность для backtesting
    """

    name = "macd"

    def __init__(
        self,
        fastperiod: int = 12,
        slowperiod: int = 26,
        signalperiod: int = 9,
        **params: Any,
    ):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(
            fastperiod=int(fastperiod),
            slowperiod=int(slowperiod),
            signalperiod=int(signalperiod),
            **params,
        )

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "macd": f"{base_key}_macd",
            "signal": f"{base_key}_signal",
            "hist": f"{base_key}_hist",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: (slowperiod + signalperiod) × 2."""
        return (self.params["slowperiod"] + self.params["signalperiod"]) * 2

    @property
    def value_keys(self) -> list[str]:
        return ["macd", "signal", "hist"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        macd_col, signal_col, hist_col = (
            self.outputs["macd"],
            self.outputs["signal"],
            self.outputs["hist"],
        )
        if macd_col in df.columns:
            return df

        close_array = df["close"].astype(float).values
        macd, signal, hist = talib.MACD(
            close_array,
            fastperiod=self.params["fastperiod"],
            slowperiod=self.params["slowperiod"],
            signalperiod=self.params["signalperiod"],
        )
        df[macd_col] = macd
        df[signal_col] = signal
        df[hist_col] = hist
        return df


class SMAIndicator(BaseIndicator):
    """
    Расчёт Simple Moving Average (SMA).

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - timeperiod × 1: минимум для расчета первого значения SMA
        - timeperiod × 1: дополнительный буфер для стабильности rolling window
        - SMA(N) требует N предыдущих значений

        Пример для SMA(20):
        - Lookback = 40 свечей
        - Обеспечивает стабильные значения для backtesting
    """

    name = "sma"

    def __init__(self, timeperiod: int = 20, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        close_array = df["close"].astype(float).values
        sma_values = talib.SMA(
            close_array, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = sma_values
        return df


class EMAIndicator(BaseIndicator):
    """
    Расчёт Exponential Moving Average (EMA).

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - timeperiod × 1: минимум для начального расчета EMA
        - timeperiod × 1: прогрев экспоненциальных весов
        - EMA(N) придает больший вес последним значениям, но учитывает всю историю

        Пример для EMA(20):
        - Lookback = 40 свечей
        - После 40 свечей веса полностью стабилизированы
    """

    name = "ema"

    def __init__(self, timeperiod: int = 20, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        close_array = df["close"].astype(float).values
        ema_values = talib.EMA(
            close_array, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = ema_values
        return df


class BollingerBandsIndicator(BaseIndicator):
    """
    Расчёт Bollinger Bands (полос Боллинджера).

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - BBands = SMA(N) ± k × StdDev(N)
        - timeperiod × 1: минимум для расчета SMA и StdDev
        - timeperiod × 1: стабилизация rolling window
        - Стандартное отклонение требует достаточного количества данных

        Пример для BBands(20, 2, 2):
        - Lookback = 40 свечей
        - Обеспечивает статистически значимую волатильность
    """

    name = "bbands"

    def __init__(
        self,
        timeperiod: int = 20,
        nbdevup: float = 2.0,
        nbdevdn: float = 2.0,
        **params: Any,
    ):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(
            timeperiod=int(timeperiod),
            nbdevup=nbdevup,
            nbdevdn=nbdevdn,
            **params,
        )

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "upper": f"{base_key}_upper",
            "middle": f"{base_key}_middle",
            "lower": f"{base_key}_lower",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["upper", "middle", "lower"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        upper_col, middle_col, lower_col = (
            self.outputs["upper"],
            self.outputs["middle"],
            self.outputs["lower"],
        )
        if upper_col in df.columns:
            return df

        close_array = df["close"].astype(float).values
        upper, middle, lower = talib.BBANDS(
            close_array,
            timeperiod=self.params["timeperiod"],
            nbdevup=self.params["nbdevup"],
            nbdevdn=self.params["nbdevdn"],
            matype=0,
        )
        df[upper_col] = upper
        df[middle_col] = middle
        df[lower_col] = lower
        return df


class ADXIndicator(BaseIndicator):
    """
    Расчёт Average Directional Movement Index (ADX).

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - ADX измеряет силу тренда через сглаживание DI+ и DI-
        - timeperiod × 1: расчет directional movement
        - timeperiod × 1: прогрев внутренней EMA для ADX

        Пример для ADX(14):
        - Lookback = 28 свечей
        - Обеспечивает корректное определение силы тренда
    """

    name = "adx"

    def __init__(self, timeperiod: int = 14, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        high, low, close = (
            df["high"].astype(float),
            df["low"].astype(float),
            df["close"].astype(float),
        )
        adx_values = talib.ADX(
            high, low, close, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = adx_values
        return df


class ATRIndicator(BaseIndicator):
    """
    Расчёт Average True Range (ATR) - индикатор волатильности.

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - ATR = EMA(True Range, timeperiod)
        - timeperiod × 1: минимум для расчета первого ATR
        - timeperiod × 1: прогрев EMA для сглаживания True Range
        - Измеряет волатильность, требует стабильных значений

        Пример для ATR(14):
        - Lookback = 28 свечей
        - Обеспечивает точную оценку волатильности
    """

    name = "atr"

    def __init__(self, timeperiod: int = 14, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        high, low, close = (
            df["high"].astype(float),
            df["low"].astype(float),
            df["close"].astype(float),
        )
        atr_values = talib.ATR(
            high, low, close, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = atr_values
        return df


class StochasticIndicator(BaseIndicator):
    """
    Расчёт Stochastic Oscillator (стохастический осциллятор).

    Lookback Period Calculation:
        Формула: (fastk_period + slowk_period + slowd_period) × 2

        Обоснование:
        - Stochastic имеет трёхуровневое сглаживание:
          1. Fast %K: rolling min/max за fastk_period
          2. Slow %K: SMA(Fast %K, slowk_period)
          3. %D: SMA(Slow %K, slowd_period)
        - Каждый уровень добавляет свой период к lookback
        - × 2: консервативный множитель для стабилизации cascading SMA

        Пример для Stochastic(14, 3, 3):
        - Lookback = (14 + 3 + 3) × 2 = 40 свечей
        - Первые 14: расчет Fast %K (highest high / lowest low)
        - Следующие 3: прогрев Slow %K (SMA от Fast %K)
        - Следующие 3: прогрев %D (SMA от Slow %K)
        - × 2: обеспечивает стабильность вложенных скользящих средних
    """

    name = "stoch"

    def __init__(
        self,
        fastk_period: int = 14,
        slowk_period: int = 3,
        slowd_period: int = 3,
        **params: Any,
    ):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(
            fastk_period=int(fastk_period),
            slowk_period=int(slowk_period),
            slowd_period=int(slowd_period),
            **params,
        )

    def _initialize_outputs(self) -> None:
        base_key = self.get_base_key()
        self.outputs = {
            "k": f"{base_key}_k",
            "d": f"{base_key}_d",
        }

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: (fastk_period + slowk_period + slowd_period) × 2."""
        return (
            self.params["fastk_period"]
            + self.params["slowk_period"]
            + self.params["slowd_period"]
        ) * 2

    @property
    def value_keys(self) -> list[str]:
        return ["k", "d"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        k_col, d_col = self.outputs["k"], self.outputs["d"]
        if k_col in df.columns:
            return df

        high, low, close = (
            df["high"].astype(float),
            df["low"].astype(float),
            df["close"].astype(float),
        )
        k_values, d_values = talib.STOCH(
            high,
            low,
            close,
            fastk_period=self.params["fastk_period"],
            slowk_period=self.params["slowk_period"],
            slowk_matype=0,
            slowd_period=self.params["slowd_period"],
            slowd_matype=0,
        )
        df[k_col] = k_values
        df[d_col] = d_values
        return df


class MFIIndicator(BaseIndicator):
    """
    Расчёт Money Flow Index (MFI) - индикатор денежного потока с учетом объема.

    Lookback Period Calculation:
        Формула: timeperiod × 2

        Обоснование:
        - MFI похож на RSI, но учитывает объем торгов
        - MFI = 100 - (100 / (1 + Money Flow Ratio))
        - Требует типичную цену (High+Low+Close)/3 и money flow
        - Использует соотношение positive/negative money flow за timeperiod
        - × 2: прогрев для стабилизации денежных потоков

        Пример для MFI(14):
        - Lookback = 28 свечей
        - Первые 14: расчет начального money flow ratio
        - Следующие 14: стабилизация соотношения positive/negative flow
        - MFI учитывает как ценовое движение, так и объем
    """

    name = "mfi"

    def __init__(self, timeperiod: int = 14, **params: Any):
        # Приводим integer параметры к int (JSONB из PostgreSQL может вернуть float)
        super().__init__(timeperiod=int(timeperiod), **params)

    def _initialize_outputs(self) -> None:
        self.outputs["value"] = self.get_base_key()

    @property
    def lookback(self) -> int:
        """Минимальное количество свечей: timeperiod × 2."""
        return self.params["timeperiod"] * 2

    @property
    def value_keys(self) -> list[str]:
        return ["value"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        col_name = self.outputs["value"]
        if col_name in df.columns:
            return df

        high, low, close, volume = (
            df["high"].astype(float),
            df["low"].astype(float),
            df["close"].astype(float),
            df["volume"].astype(float),
        )
        mfi_values = talib.MFI(
            high, low, close, volume, timeperiod=self.params["timeperiod"]
        )
        df[col_name] = mfi_values
        return df
