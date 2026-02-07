USE trader;

CREATE TABLE trader.candles_base_new
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
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(begin)
ORDER BY (ticker, timeframe, begin);

INSERT INTO trader.candles_base_new
SELECT * FROM trader.candles_base
WHERE toYear(begin) >= 2000 AND toYear(begin) <= 2025;

RENAME TABLE trader.candles_base TO trader.candles_base_mergetree_backup;

RENAME TABLE trader.candles_base_new TO trader.candles_base;

DROP TABLE trader.candles_base_mergetree_backup;

DROP TABLE IF EXISTS trader.candles_wide_old;
