USE trader;

-- 1. Создаем новую таблицу с колонкой version
CREATE TABLE trader.candles_indicators_new
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime64(3, 'Europe/Moscow'),
    `indicator_key` String,
    `value_key` String,
    `value` Float64,
    `version` UInt64
)
ENGINE = ReplacingMergeTree(version)  -- Используем version для автоматической дедупликации
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin, indicator_key, value_key)
SETTINGS index_granularity = 8192;

-- 2. Копируем данные из старой таблицы
-- Для существующих данных проставляем version = 0
-- При следующих вставках будут использоваться реальные версии (timestamp в микросекундах)
INSERT INTO trader.candles_indicators_new
SELECT
    ticker,
    timeframe,
    begin,
    indicator_key,
    value_key,
    value,
    0 as version
FROM trader.candles_indicators;

-- 3. Переименовываем таблицы
RENAME TABLE trader.candles_indicators TO trader.candles_indicators_without_version_backup;
RENAME TABLE trader.candles_indicators_new TO trader.candles_indicators;

-- 4. После проверки работоспособности (1-2 дня) можно удалить backup
DROP TABLE trader.candles_indicators_without_version_backup;
