-- Переходим в нужную базу данных
USE trader;

-- 1. Переименовываем старую таблицу, чтобы сохранить данные
RENAME TABLE trader.candles TO trader.candles_wide_old;

-- 2. Создаем новую таблицу для базовых данных свечей (OHLCV)
CREATE TABLE trader.candles_base
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime,
    `open` Float64,
    `high` Float64,
    `low` Float64,
    `close` Float64,
    `volume` Float64
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin);

-- 3. Создаем новую узкую таблицу для всех значений всех индикаторов
CREATE TABLE trader.candles_indicators
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime,
    -- Ключ индикатора, например, 'sma_20' или 'macd_12_26_9'. Связан с trader_core.indicators.indicator_key
    `indicator_key` String,
    -- Для многокомпонентных индикаторов (напр., 'macd', 'signal', 'hist' для MACD)
    `value_key` String,
    `value` Float64
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(begin)
-- Оптимальный ключ сортировки для выборки одного индикатора за период
ORDER BY (ticker, timeframe, begin, indicator_key, value_key);
