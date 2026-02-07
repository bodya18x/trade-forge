-- Переходим в БД
USE trader;

ALTER TABLE candles

-- Добавляем индикаторы силы тренда
ADD COLUMN IF NOT EXISTS trend_direction Nullable(Int32) AFTER ICS_26,
ADD COLUMN IF NOT EXISTS trend_strength Nullable(Float64) AFTER trend_direction,
ADD COLUMN IF NOT EXISTS trend_quality Nullable(Float64) AFTER trend_strength,
ADD COLUMN IF NOT EXISTS trend_consistency Nullable(Float64) AFTER trend_quality,
ADD COLUMN IF NOT EXISTS trend_phase Nullable(String) AFTER trend_consistency;
