-- Переходим в БД
USE trader;

-- Таблица рынков
CREATE TABLE IF NOT EXISTS markets
(
    market_id   UInt8,
    market_name String
)
ENGINE = MergeTree
ORDER BY market_id; 

-- Добавляем рынок MOEX:
INSERT INTO markets (market_id, market_name) VALUES (1, 'MOEX');


-- Таблица тикеров
CREATE TABLE IF NOT EXISTS tickers
(
    ticker       String,                                 -- Код инструмента
    ticker_type  Enum8('stock' = 1, 'currency' = 2, 'futures' = 3),
    market_id    UInt8,                                  -- Ссылка на markets.market_id

    active       Boolean DEFAULT True,                   -- Активен ли сбор данных по тикеру или нет?
    
    shortname    Nullable(String),
    lotsize      Nullable(UInt32),
    decimals     Nullable(UInt8),
    minstep      Nullable(Float64),

    issuesize    Nullable(UInt64),
    isin         Nullable(String),
    regnumber    Nullable(String),
    listlevel    Nullable(UInt8)
)
ENGINE = MergeTree
ORDER BY ticker;


-- Таблица со свечами
CREATE TABLE IF NOT EXISTS candles
(
    ticker   String,    -- Ссылка на tickers.ticker

    timeframe String,    -- Таймфрейм сбора
    
    open     Float64,
    close    Float64,
    high     Float64,
    low      Float64,
    
    value    Int64,     -- Объём в деньгах (например, рублях)
    volume   Float64,   -- Объём в лотах
    
    begin    DateTime('UTC'),  -- Время начала свечи
    end      DateTime('UTC')   -- Время окончания свечи
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(begin)   -- Разбиваем на партиции по месяцу начала свечи
ORDER BY (ticker, begin);
