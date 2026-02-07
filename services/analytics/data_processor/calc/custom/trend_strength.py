"""
Модуль для расчета индикатора силы тренда.

Содержит класс TrendStrengthIndicator, который оценивает силу, качество
и направление текущего тренда на основе анализа цены, объема и волатильности.
"""

import numpy as np
import pandas as pd


class TrendStrengthIndicator:
    """Индикатор определения силы тренда.

    Рассчитывает комплексную оценку силы и качества тренда на основе:
    - Price Action анализа
    - Объемных характеристик
    - Волатильности
    - Моментума

    Args:
        period (int): Основной период расчета. По умолчанию 20.
        smoothing_period (int): Период сглаживания. По умолчанию 3.
        method (str): Метод расчета ("simple" или "advanced"). По умолчанию "advanced".
        use_volume (bool): Использовать ли объем в расчетах. По умолчанию True.
    """

    def __init__(
        self,
        period: int = 20,
        smoothing_period: int = 3,
        method: str = "advanced",
        use_volume: bool = True,
    ):
        self.period = period
        self.smoothing_period = smoothing_period
        self.method = method
        self.use_volume = use_volume

        # Обновленные веса компонентов для лучшего баланса
        self.weights = {
            "price_action": 0.45,
            "volume": 0.20,
            "volatility": 0.15,
            "momentum": 0.20,
        }

        if not use_volume:
            # Перераспределяем вес объема на другие компоненты
            self.weights["price_action"] = 0.55
            self.weights["volatility"] = 0.20
            self.weights["momentum"] = 0.25
            self.weights["volume"] = 0.0

        # Кэш для ATR
        self._atr_cache = None

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитывает индикатор силы тренда.

        Args:
            df (pd.DataFrame): DataFrame с колонками OHLCV.

        Returns:
            pd.DataFrame: DataFrame с добавленными колонками:
                - trend_direction: направление тренда (-1, 0, 1)
                - trend_strength: сила тренда (0-100)
                - trend_quality: качество тренда (0-100)
                - trend_consistency: консистентность (0-100)
                - trend_phase: фаза тренда
        """
        # Инициализация колонок результата
        df = df.copy()

        if len(df) < self.period:
            df[
                [
                    "trend_direction",
                    "trend_strength",
                    "trend_quality",
                    "trend_consistency",
                    "trend_phase",
                ]
            ] = None
            return df

        # Предрасчет часто используемых значений
        close = df["close"]
        self._price_pct_change = close.pct_change()
        self._price_diff = close.diff()

        # Кэшируем ATR для переиспользования
        self._atr_cache = self._calculate_atr(df, self.period)

        # Рассчитываем компоненты с улучшенными методами
        price_action_score = self._calculate_price_action(df)
        volume_score = (
            self._calculate_volume_confirmation(df) if self.use_volume else 0
        )
        volatility_score = self._calculate_volatility_alignment(df)
        momentum_score = self._calculate_momentum(df)

        # Определяем направление тренда (улучшенный метод)
        df["trend_direction"] = self._determine_trend_direction(df)

        # Рассчитываем итоговую силу тренда
        df["trend_strength"] = (
            self.weights["price_action"] * price_action_score
            + self.weights["volume"] * volume_score
            + self.weights["volatility"] * volatility_score
            + self.weights["momentum"] * momentum_score
        )

        # Более мягкое сглаживание результата
        df["trend_strength"] = (
            df["trend_strength"]
            .rolling(window=self.smoothing_period, min_periods=1)
            .mean()
        )

        # Финальный клиппинг значений
        df["trend_strength"] = np.clip(df["trend_strength"], 0, 100)

        # Рассчитываем качество тренда (оптимизированная версия)
        df["trend_quality"] = self._calculate_trend_quality_optimized(df)

        # Рассчитываем консистентность (улучшенная формула)
        df["trend_consistency"] = self._calculate_consistency(df)

        # Определяем фазу тренда (адаптивные пороги)
        df["trend_phase"] = self._determine_trend_phase(df)

        return df

    def _calculate_price_action(self, df: pd.DataFrame) -> pd.Series:
        """Рассчитывает компонент Price Action (оптимизированный)."""
        close = df["close"]

        # Расчет процентного изменения цены за период
        pct_change = close.pct_change(periods=self.period) * 100

        # Векторизованный расчет наклона через линейную регрессию
        # Используем более эффективный метод без apply
        slopes = self._vectorized_slope(close, self.period)

        # Нормализация на основе процентного изменения
        volatility = (
            self._price_pct_change.rolling(window=self.period).std() * 100
        )
        normalized_slopes = np.abs(slopes) / (volatility + 0.1) * 50

        # Комбинируем процентное изменение и наклон
        combined_score = np.abs(pct_change) * 0.4 + normalized_slopes * 0.6

        # Применяем более мягкую нормализацию
        return np.clip(combined_score * 1.5, 0, 100)

    def _vectorized_slope(self, series: pd.Series, window: int) -> pd.Series:
        """Векторизованный расчет наклона линейной регрессии."""
        # Создаем матрицу X для всех окон сразу
        x = np.arange(window).reshape(-1, 1)
        x = np.concatenate([x, np.ones((window, 1))], axis=1)

        # Получаем все окна значений
        values = (
            series.rolling(window=window).apply(lambda y: 0, raw=False).index
        )

        slopes = []
        for i in range(len(series)):
            if i < window - 1:
                slopes.append(0)
            else:
                y = series.iloc[i - window + 1 : i + 1].values
                # Быстрый расчет через нормальные уравнения
                try:
                    coeffs = np.linalg.lstsq(x, y, rcond=None)[0]
                    slopes.append(coeffs[0])
                except:
                    slopes.append(0)

        return pd.Series(slopes, index=series.index)

    def _calculate_volume_confirmation(self, df: pd.DataFrame) -> pd.Series:
        """Рассчитывает компонент подтверждения объемом (оптимизированный)."""
        if "volume" not in df.columns:
            return pd.Series(0, index=df.index)

        volume = df["volume"]

        # Средний объем с адаптивным периодом
        avg_volume = volume.rolling(window=self.period).mean()

        # Направление движения цены (уже предрасчитано)
        price_change = self._price_diff

        # Векторизованный расчет объемов
        volume_up = np.where(price_change > 0, volume, 0)
        volume_down = np.where(price_change < 0, volume, 0)

        # Взвешенные объемы
        price_change_abs = np.abs(price_change)
        volume_up_weighted = volume_up * np.where(
            price_change > 0, price_change_abs, 0
        )
        volume_down_weighted = volume_down * np.where(
            price_change < 0, price_change_abs, 0
        )

        up_sum = (
            pd.Series(volume_up_weighted).rolling(window=self.period).sum()
        )
        down_sum = (
            pd.Series(volume_down_weighted).rolling(window=self.period).sum()
        )
        total_sum = up_sum + down_sum

        # Векторизованный расчет индекса
        volume_ratio = np.where(
            total_sum > 0, np.abs(up_sum - down_sum) / total_sum * 100, 0
        )

        # Относительный объем
        relative_volume = volume / (avg_volume + 1e-10)
        volume_multiplier = np.clip(relative_volume, 0.5, 2.5)

        volume_score = volume_ratio * volume_multiplier * 1.2

        return pd.Series(np.clip(volume_score, 0, 100), index=df.index)

    def _calculate_volatility_alignment(self, df: pd.DataFrame) -> pd.Series:
        """Рассчитывает компонент выравнивания волатильности (оптимизированный)."""
        high = df["high"]
        low = df["low"]

        # Используем кэшированный ATR
        atr = self._atr_cache

        # Диапазон свечей относительно ATR
        candle_range = high - low
        relative_range = candle_range / (atr + 1e-10)

        # Векторизованный расчет оценки волатильности
        optimal_low = 0.5
        optimal_high = 2.0

        # Используем np.select для векторизованных условий
        conditions = [
            (relative_range >= optimal_low) & (relative_range <= optimal_high),
            relative_range < optimal_low,
        ]
        choices = [
            100,
            (relative_range / optimal_low) * 100,
        ]
        default = 100 * np.exp(
            -0.5 * ((relative_range - optimal_high) / optimal_high) ** 2
        )

        volatility_score = np.select(conditions, choices, default=default)

        # Стабильность волатильности
        atr_std = atr.rolling(window=5).std()
        atr_mean = atr.rolling(window=5).mean()
        volatility_stability = 1 - (atr_std / (atr_mean + 1e-10))
        volatility_stability = np.clip(volatility_stability, 0, 1)

        final_score = volatility_score * (0.7 + 0.3 * volatility_stability)

        return pd.Series(np.clip(final_score, 0, 100), index=df.index)

    def _calculate_momentum(self, df: pd.DataFrame) -> pd.Series:
        """Рассчитывает компонент моментума (оптимизированный)."""
        close = df["close"]

        # Rate of Change с адаптивным периодом
        short_roc = close.pct_change(periods=self.period // 2) * 100
        long_roc = close.pct_change(periods=self.period) * 100

        # Комбинированный ROC
        combined_roc = np.abs(short_roc) * 0.6 + np.abs(long_roc) * 0.4

        # Используем RSI если доступен
        if "rsi14" in df.columns:
            rsi = df["rsi14"]
            # Векторизованная конвертация RSI
            momentum_from_rsi = np.where(
                rsi > 50, (rsi - 50) * 2, (50 - rsi) * 2
            )
            extreme_bonus = np.where((rsi > 70) | (rsi < 30), 20, 0)
            momentum_from_rsi = np.abs(momentum_from_rsi) + extreme_bonus
        else:
            # Альтернативный расчет моментума
            sma_fast = close.rolling(window=self.period // 3).mean()
            sma_slow = close.rolling(window=self.period).mean()
            momentum_from_ma = np.abs((sma_fast - sma_slow) / sma_slow * 100)
            momentum_from_rsi = momentum_from_ma * 50

        # Ускорение тренда
        acceleration = combined_roc.diff()
        acceleration_bonus = np.where(
            np.abs(acceleration) > np.abs(combined_roc) * 0.2, 15, 0
        )

        # Комбинированный моментум
        combined_momentum = (
            combined_roc * 0.4
            + momentum_from_rsi * 0.5
            + acceleration_bonus * 0.1
        )

        return pd.Series(
            np.clip(combined_momentum * 1.3, 0, 100), index=df.index
        )

    def _determine_trend_direction(self, df: pd.DataFrame) -> pd.Series:
        """Определяет направление тренда (оптимизированный)."""
        close = df["close"]

        # Скользящие средние (предрасчет)
        sma_short = close.rolling(window=self.period // 4).mean()
        sma_medium = close.rolling(window=self.period // 2).mean()
        sma_long = close.rolling(window=self.period).mean()

        # Упрощенный расчет наклонов
        slope_short = sma_short.diff(self.period // 4)
        slope_long = sma_long.diff(self.period)

        # Векторизованная оценка направления
        position_score = np.where(
            close > sma_long, 0.3, np.where(close < sma_long, -0.3, 0)
        )

        ma_arrangement_score = np.where(
            (sma_short > sma_medium) & (sma_medium > sma_long),
            0.3,
            np.where(
                (sma_short < sma_medium) & (sma_medium < sma_long), -0.3, 0
            ),
        )

        slope_direction_score = (
            np.sign(slope_short) * 0.25 + np.sign(slope_long) * 0.15
        )

        # Комбинированная оценка
        combined_score = (
            position_score + ma_arrangement_score + slope_direction_score
        )

        # Векторизованное определение направления
        direction = np.where(
            combined_score > 0.3, 1, np.where(combined_score < -0.3, -1, 0)
        )

        return pd.Series(direction, index=df.index)

    def _calculate_trend_quality_optimized(
        self, df: pd.DataFrame
    ) -> pd.Series:
        """Рассчитывает качество тренда (оптимизированная версия)."""
        trend_direction = df["trend_direction"]

        # Направленность движений
        aligned_moves = np.where(
            (trend_direction > 0) & (self._price_diff > 0),
            1,
            np.where(
                (trend_direction < 0) & (self._price_diff < 0),
                1,
                np.where(trend_direction == 0, 0.3, 0),
            ),
        )

        alignment_ratio = (
            pd.Series(aligned_moves).rolling(window=self.period).mean() * 100
        )

        # Упрощенный расчет качества отката
        close = df["close"]
        rolling_max = close.rolling(window=self.period).max()
        rolling_min = close.rolling(window=self.period).min()

        # Векторизованная оценка отката
        price_range = rolling_max - rolling_min
        current_position = (close - rolling_min) / (price_range + 1e-10)

        # Качество на основе позиции в диапазоне
        retracement_quality = np.where(
            trend_direction > 0,
            current_position
            * 100,  # Чем выше в диапазоне для восходящего, тем лучше
            np.where(
                trend_direction < 0,
                (1 - current_position)
                * 100,  # Чем ниже в диапазоне для нисходящего, тем лучше
                50,  # Нейтрально для бокового
            ),
        )

        # Стабильность волатильности
        volatility = self._price_pct_change.rolling(window=self.period).std()
        avg_volatility = volatility.rolling(window=self.period * 2).mean()
        volatility_quality = (
            np.exp(
                -np.abs(volatility - avg_volatility) / (avg_volatility + 1e-10)
            )
            * 80
        )

        # Комбинированная оценка
        quality_score = (
            alignment_ratio * 0.3
            + retracement_quality * 0.5
            + volatility_quality * 0.2
        )

        # Штрафы
        trend_strength = df["trend_strength"]
        strength_penalty = np.where(
            trend_strength < 30, 0.5, np.where(trend_strength < 50, 0.8, 1.0)
        )

        quality_score = quality_score * strength_penalty

        # Финальная калибровка
        quality_score = np.where(
            quality_score > 80, 80 + (quality_score - 80) * 0.5, quality_score
        )

        return pd.Series(np.clip(quality_score, 0, 95), index=df.index)

    def _calculate_consistency(self, df: pd.DataFrame) -> pd.Series:
        """Рассчитывает консистентность тренда (оптимизированная)."""
        trend_strength = df["trend_strength"]
        trend_direction = df["trend_direction"]

        # Стабильность силы тренда
        strength_volatility = trend_strength.rolling(
            window=self.period // 2
        ).std()
        avg_strength = trend_strength.rolling(window=self.period).mean()

        normalized_volatility = strength_volatility / (avg_strength + 5)

        # Векторизованная оценка консистентности
        strength_consistency = np.where(
            normalized_volatility < 0.1,
            100,
            np.where(
                normalized_volatility > 1, 0, (1 - normalized_volatility) * 100
            ),
        )

        # Стабильность направления
        direction_changes = np.abs(trend_direction.diff())
        direction_change_rate = (
            pd.Series(direction_changes).rolling(window=self.period).mean()
        )

        direction_stability = np.where(
            direction_change_rate < 0.1,
            100,
            np.where(
                direction_change_rate > 0.5,
                0,
                (1 - direction_change_rate * 2) * 100,
            ),
        )

        # Комбинированная консистентность
        consistency = (
            strength_consistency * 0.6 + direction_stability * 0.4
        ) * 0.8

        return pd.Series(np.clip(consistency, 0, 100), index=df.index)

    def _determine_trend_phase(self, df: pd.DataFrame) -> pd.Series:
        """Определяет фазу тренда (оптимизированная).

        | Название          | Пояснение                                          |
        | ----------------- | -------------------------------------------------- |
        | `no_trend`        | Рынок в боковой зоне, нет выраженного направления. |
        | `start`           | Тренд только зарождается, движение ускоряется.     |
        | `development`     | Тренд устойчиво усиливается, набирается инерция.   |
        | `mature`          | Полная уверенность в тренде, мало колебаний.       |
        | `exhaustion`      | Движение замедляется, возможен разворот.           |
        """
        trend_strength = df["trend_strength"]
        trend_quality = df["trend_quality"]
        trend_consistency = df["trend_consistency"]

        # Скользящие средние для определения динамики
        strength_ma_short = trend_strength.rolling(
            window=max(3, self.period // 6)
        ).mean()
        strength_ma_long = trend_strength.rolling(
            window=self.period // 2
        ).mean()

        # Адаптивные пороги
        strength_low = trend_strength.rolling(window=self.period * 2).quantile(
            0.25
        )
        strength_mid = trend_strength.rolling(window=self.period * 2).quantile(
            0.5
        )
        strength_high = trend_strength.rolling(
            window=self.period * 2
        ).quantile(0.75)

        # Векторизованное определение фазы
        phases = []
        for i in range(len(df)):
            if i < self.period * 2:
                phases.append("undefined")
                continue

            strength = trend_strength.iloc[i]
            quality = trend_quality.iloc[i]
            consistency = trend_consistency.iloc[i]
            strength_short = strength_ma_short.iloc[i]
            strength_long = strength_ma_long.iloc[i]

            low_threshold = strength_low.iloc[i]
            mid_threshold = strength_mid.iloc[i]
            high_threshold = strength_high.iloc[i]

            if strength < low_threshold:
                phase = "no_trend"  # Нет тренда
            elif strength < mid_threshold and strength_short > strength_long:
                phase = "start"  # Начало формирования
            elif strength >= high_threshold and quality > 60:
                phase = "mature"  # Зрелый тренд
            elif strength > high_threshold and strength_short < strength_long:
                phase = "exhaustion"  # Ослабление тренда
            else:
                phase = "development"  # Развитие

            if phase == "mature" and consistency < 30:
                phase = "development"  # Развитие

            if phase == "start" and quality > 70:
                phase = "development"  # Развитие

            phases.append(phase)

        return pd.Series(phases, index=df.index)

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Рассчитывает ATR (оптимизированная версия)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Векторизованный расчет True Range
        close_prev = close.shift(1)
        tr1 = high - low
        tr2 = np.abs(high - close_prev)
        tr3 = np.abs(low - close_prev)

        true_range = np.maximum(np.maximum(tr1, tr2), tr3)

        # ATR
        atr = pd.Series(true_range).rolling(window=period).mean()

        return atr
