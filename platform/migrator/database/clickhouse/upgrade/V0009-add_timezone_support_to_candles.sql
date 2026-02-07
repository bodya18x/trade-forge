USE trader;

-- 1. Создаем новую таблицу с DateTime64 и таймзоной
CREATE TABLE trader.candles_base_new
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime64(3, 'Europe/Moscow'),
    `open` Float64,
    `high` Float64,
    `low` Float64,
    `close` Float64,
    `volume` Float64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin)
SETTINGS index_granularity = 8192;

-- 2. Копируем данные из старой таблицы, конвертируя DateTime в DateTime64 с таймзоной
-- Предполагаем, что старые данные были в московском времени (naive datetime)
INSERT INTO trader.candles_base_new
SELECT 
    ticker,
    timeframe,
    toDateTime64(begin, 3, 'Europe/Moscow') as begin,
    open,
    high,
    low,
    close,
    volume
FROM trader.candles_base;

-- 3. Переименовываем таблицы
RENAME TABLE trader.candles_base TO trader.candles_base_without_tz_backup;
RENAME TABLE trader.candles_base_new TO trader.candles_base;

-- 4. После проверки работоспособности можно удалить backup
DROP TABLE trader.candles_base_without_tz_backup;

-- 5. Также обновляем таблицу с индикаторами (если нужно)
CREATE TABLE trader.candles_indicators_new
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime64(3, 'Europe/Moscow'),
    `indicator_key` String,
    `value_key` String,
    `value` Float64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin, indicator_key, value_key)
SETTINGS index_granularity = 8192;

-- 6. Копируем данные индикаторов
INSERT INTO trader.candles_indicators_new
SELECT 
    ticker,
    timeframe,
    toDateTime64(begin, 3, 'Europe/Moscow') as begin,
    indicator_key,
    value_key,
    value
FROM trader.candles_indicators;

-- 7. Переименовываем таблицы индикаторов
RENAME TABLE trader.candles_indicators TO trader.candles_indicators_without_tz_backup;
RENAME TABLE trader.candles_indicators_new TO trader.candles_indicators;

-- 8. После проверки удалите backup индикаторов
DROP TABLE trader.candles_indicators_without_tz_backup;
