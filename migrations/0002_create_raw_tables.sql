CREATE TABLE IF NOT EXISTS raw.algopack_responses
(
    endpoint LowCardinality(String),
    response_kind LowCardinality(String),
    ticker LowCardinality(String),
    request_date Nullable(Date),
    requested_at DateTime DEFAULT now(),
    response_json String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(requested_at)
ORDER BY (endpoint, response_kind, ticker, requested_at);

CREATE TABLE IF NOT EXISTS raw.dataversions
(
    endpoint LowCardinality(String),
    response_kind LowCardinality(String),
    ticker LowCardinality(String),
    data_version UInt64,
    seqnum UInt64,
    trade_date Date,
    trade_session_date Date,
    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY trade_date
ORDER BY (endpoint, ticker, trade_date, seqnum);

CREATE TABLE IF NOT EXISTS raw.obstats
(
    trade_date Date,
    trade_time String,
    event_time DateTime,
    secid LowCardinality(String),

    spread_bbo Float64,
    spread_lv10 Float64,
    spread_1mio Float64,

    levels_b UInt32,
    levels_s UInt32,

    vol_b UInt64,
    vol_s UInt64,
    val_b UInt64,
    val_s UInt64,

    imbalance_vol_bbo Float64,
    imbalance_val_bbo Float64,
    imbalance_vol Float64,
    imbalance_val Float64,

    vwap_b Float64,
    vwap_s Float64,
    vwap_b_1mio Float64,
    vwap_s_1mio Float64,

    systime DateTime,
    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(trade_date)
ORDER BY (secid, trade_date, event_time);

CREATE TABLE IF NOT EXISTS raw.orderstats
(
    trade_date Date,
    trade_time String,
    event_time DateTime,
    secid LowCardinality(String),

    put_orders_b UInt64,
    put_orders_s UInt64,
    put_val_b UInt64,
    put_val_s UInt64,
    put_vol_b UInt64,
    put_vol_s UInt64,
    put_vwap_b Float64,
    put_vwap_s Float64,
    put_vol UInt64,
    put_val UInt64,
    put_orders UInt64,

    cancel_orders_b UInt64,
    cancel_orders_s UInt64,
    cancel_val_b UInt64,
    cancel_val_s UInt64,
    cancel_vol_b UInt64,
    cancel_vol_s UInt64,
    cancel_vwap_b Float64,
    cancel_vwap_s Float64,
    cancel_vol UInt64,
    cancel_val UInt64,
    cancel_orders UInt64,

    systime DateTime,
    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(trade_date)
ORDER BY (secid, trade_date, event_time);

CREATE TABLE IF NOT EXISTS raw.tradestats
(
    trade_date Date,
    trade_time String,
    event_time DateTime,
    secid LowCardinality(String),

    pr_open Float64,
    pr_high Float64,
    pr_low Float64,
    pr_close Float64,
    pr_std Float64,

    vol UInt64,
    val UInt64,
    trades UInt64,
    pr_vwap Float64,
    pr_change Float64,

    trades_b UInt64,
    trades_s UInt64,
    val_b UInt64,
    val_s UInt64,
    vol_b UInt64,
    vol_s UInt64,

    disb Float64,
    pr_vwap_b Float64,
    pr_vwap_s Float64,

    systime DateTime,

    sec_pr_open UInt64,
    sec_pr_high UInt64,
    sec_pr_low UInt64,
    sec_pr_close UInt64,

    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(trade_date)
ORDER BY (secid, trade_date, event_time);

CREATE TABLE IF NOT EXISTS raw.orderbook
(
    trade_date Date,
    snapshot_time String,
    snapshot_ts DateTime,

    boardid LowCardinality(String),
    secid LowCardinality(String),
    side LowCardinality(String),

    price Float64,
    quantity UInt64,
    seqnum UInt64,
    update_time String,
    decimals UInt8,

    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY trade_date
ORDER BY (secid, snapshot_ts, side, price);

CREATE TABLE IF NOT EXISTS raw.instruments
(
    secid LowCardinality(String),
    boardid LowCardinality(String),
    shortname String,
    secname String,
    latname Nullable(String),
    isin Nullable(String),

    marketcode Nullable(String),
    instrid Nullable(String),
    sectype Nullable(String),
    currencyid Nullable(String),
    status Nullable(String),

    lotsize Nullable(Float64),
    minstep Nullable(Float64),
    decimals Nullable(UInt8),
    listlevel Nullable(UInt8),

    prevprice Nullable(Float64),
    prevwaprice Nullable(Float64),
    prevlegalcloseprice Nullable(Float64),
    prevdate Nullable(Date),
    settledate Nullable(Date),

    issuesize Nullable(UInt64),
    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (secid, boardid, loaded_at);

CREATE TABLE IF NOT EXISTS raw.marketdata_snapshots
(
    secid LowCardinality(String),
    boardid LowCardinality(String),

    bid Nullable(Float64),
    biddepth Nullable(Float64),
    offer Nullable(Float64),
    offerdepth Nullable(Float64),
    spread Nullable(Float64),

    open Nullable(Float64),
    low Nullable(Float64),
    high Nullable(Float64),
    last Nullable(Float64),
    waprice Nullable(Float64),

    numtrades Nullable(UInt64),
    voltoday Nullable(Float64),
    valtoday Nullable(Float64),

    tradingstatus Nullable(String),
    updatetime Nullable(String),
    lastbid Nullable(Float64),
    lastoffer Nullable(Float64),
    numbids Nullable(UInt64),
    numoffers Nullable(UInt64),

    time Nullable(String),
    seqnum Nullable(UInt64),
    systime Nullable(DateTime),

    loaded_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(loaded_at)
ORDER BY (secid, boardid, loaded_at);
