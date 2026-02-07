USE trader;

CREATE TABLE trader.candles_indicators_new
(
    `ticker` String,
    `timeframe` String,
    `begin` DateTime,
    `indicator_key` String,
    `value_key` String,
    `value` Float64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin, indicator_key, value_key);

INSERT INTO trader.candles_indicators_new
SELECT * FROM trader.candles_indicators
WHERE toYear(begin) >= 2000 AND toYear(begin) <= 2025;

RENAME TABLE trader.candles_indicators TO trader.candles_indicators_mergetree_backup;

RENAME TABLE trader.candles_indicators_new TO trader.candles_indicators;

DROP TABLE trader.candles_indicators_mergetree_backup;
