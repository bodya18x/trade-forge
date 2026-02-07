-- Переходим в БД
USE trader;

ALTER TABLE candles

-- Добавляем индикаторы MACD
ADD COLUMN IF NOT EXISTS macd_12_26_9 Nullable(Float64) AFTER timeframe,
ADD COLUMN IF NOT EXISTS macd_signal_12_26_9 Nullable(Float64) AFTER macd_12_26_9,
ADD COLUMN IF NOT EXISTS macd_hist_12_26_9 Nullable(Float64) AFTER macd_signal_12_26_9,

-- Добавляем RSI
ADD COLUMN IF NOT EXISTS rsi14 Nullable(Float64) AFTER macd_hist_12_26_9,

-- Добавляем SMA и EMA
ADD COLUMN IF NOT EXISTS sma20 Nullable(Float64) AFTER rsi14,
ADD COLUMN IF NOT EXISTS ema50 Nullable(Float64) AFTER sma20,

-- Добавляем Bollinger Bands
ADD COLUMN IF NOT EXISTS bb_upper_20_2 Nullable(Float64) AFTER ema50,
ADD COLUMN IF NOT EXISTS bb_middle_20_2 Nullable(Float64) AFTER bb_upper_20_2,
ADD COLUMN IF NOT EXISTS bb_lower_20_2 Nullable(Float64) AFTER bb_middle_20_2,

-- Добавляем ADX
ADD COLUMN IF NOT EXISTS adx14 Nullable(Float64) AFTER bb_lower_20_2,

-- Добавляем ATR
ADD COLUMN IF NOT EXISTS atr14 Nullable(Float64) AFTER adx14,

-- Добавляем Stochastic Oscillator
ADD COLUMN IF NOT EXISTS stoch_k_14_3 Nullable(Float64) AFTER atr14,
ADD COLUMN IF NOT EXISTS stoch_d_14_3 Nullable(Float64) AFTER stoch_k_14_3,

-- Добавляем MFI
ADD COLUMN IF NOT EXISTS mfi14 Nullable(Float64) AFTER stoch_d_14_3,

-- Добавляем TSI
ADD COLUMN IF NOT EXISTS TSI_13_25_13 Nullable(Float64) AFTER mfi14,
ADD COLUMN IF NOT EXISTS TSIs_13_25_13 Nullable(Float64) AFTER TSI_13_25_13,

-- Добавляем Supertrend
ADD COLUMN IF NOT EXISTS `SUPERT_10_3.0` Nullable(Float64) AFTER TSIs_13_25_13,
ADD COLUMN IF NOT EXISTS `SUPERTd_10_3.0` Nullable(Int32) AFTER `SUPERT_10_3.0`,
ADD COLUMN IF NOT EXISTS `SUPERTl_10_3.0` Nullable(Float64) AFTER `SUPERTd_10_3.0`,
ADD COLUMN IF NOT EXISTS `SUPERTs_10_3.0` Nullable(Float64) AFTER `SUPERTl_10_3.0`,

-- Добавляем Squeeze Indicator
ADD COLUMN IF NOT EXISTS `SQZ_20_2.0_20_1.5_LB` Nullable(Float64) AFTER `SUPERTs_10_3.0`,
ADD COLUMN IF NOT EXISTS SQZ_ON Nullable(Int32) AFTER `SQZ_20_2.0_20_1.5_LB`,
ADD COLUMN IF NOT EXISTS SQZ_OFF Nullable(Int32) AFTER SQZ_ON,
ADD COLUMN IF NOT EXISTS SQZ_NO Nullable(Int32) AFTER SQZ_OFF,

-- Добавляем Vortex Indicator
ADD COLUMN IF NOT EXISTS VTXP_14 Nullable(Float64) AFTER SQZ_NO,
ADD COLUMN IF NOT EXISTS VTXM_14 Nullable(Float64) AFTER VTXP_14,

-- Добавляем Ichimoku
ADD COLUMN IF NOT EXISTS ISA_9 Nullable(Float64) AFTER VTXM_14,
ADD COLUMN IF NOT EXISTS ISB_26 Nullable(Float64) AFTER ISA_9,
ADD COLUMN IF NOT EXISTS ITS_9 Nullable(Float64) AFTER ISB_26,
ADD COLUMN IF NOT EXISTS IKS_26 Nullable(Float64) AFTER ITS_9,
ADD COLUMN IF NOT EXISTS ICS_26 Nullable(Float64) AFTER IKS_26;
