CREATE OR REPLACE VIEW stg.v_obstats AS
SELECT
    trade_date,
    trade_time,
    event_time,
    secid,
    spread_bbo,
    spread_lv10,
    spread_1mio,
    levels_b,
    levels_s,
    vol_b,
    vol_s,
    val_b,
    val_s,
    imbalance_vol_bbo,
    imbalance_val_bbo,
    imbalance_vol,
    imbalance_val,
    vwap_b,
    vwap_s,
    vwap_b_1mio,
    vwap_s_1mio,
    systime
FROM raw.obstats;

CREATE OR REPLACE VIEW stg.v_orderstats AS
SELECT
    *,
    if(put_vol = 0, NULL, (toFloat64(put_vol_b) - toFloat64(put_vol_s)) / toFloat64(put_vol)) AS put_vol_imbalance,
    if(put_val = 0, NULL, (toFloat64(put_val_b) - toFloat64(put_val_s)) / toFloat64(put_val)) AS put_val_imbalance,
    if(cancel_vol = 0, NULL, (toFloat64(cancel_vol_b) - toFloat64(cancel_vol_s)) / toFloat64(cancel_vol)) AS cancel_vol_imbalance,
    if(cancel_val = 0, NULL, (toFloat64(cancel_val_b) - toFloat64(cancel_val_s)) / toFloat64(cancel_val)) AS cancel_val_imbalance
FROM raw.orderstats;

CREATE OR REPLACE VIEW stg.v_tradestats AS
SELECT
    *,
    if(vol = 0, NULL, (toFloat64(vol_b) - toFloat64(vol_s)) / toFloat64(vol)) AS trade_vol_imbalance,
    if(val = 0, NULL, (toFloat64(val_b) - toFloat64(val_s)) / toFloat64(val)) AS trade_val_imbalance
FROM raw.tradestats;

CREATE OR REPLACE VIEW stg.v_instruments_latest AS
SELECT
    secid,
    boardid,
    argMax(shortname, loaded_at) AS shortname,
    argMax(secname, loaded_at) AS secname,
    argMax(latname, loaded_at) AS latname,
    argMax(isin, loaded_at) AS isin,
    argMax(marketcode, loaded_at) AS marketcode,
    argMax(instrid, loaded_at) AS instrid,
    argMax(sectype, loaded_at) AS sectype,
    argMax(currencyid, loaded_at) AS currencyid,
    argMax(status, loaded_at) AS status,
    argMax(lotsize, loaded_at) AS lotsize,
    argMax(minstep, loaded_at) AS minstep,
    argMax(decimals, loaded_at) AS decimals,
    argMax(listlevel, loaded_at) AS listlevel,
    argMax(issuesize, loaded_at) AS issuesize,
    max(loaded_at) AS latest_loaded_at
FROM raw.instruments
GROUP BY secid, boardid;

CREATE OR REPLACE VIEW stg.v_orderbook_top AS
WITH
    best_bid AS
    (
        SELECT
            trade_date,
            snapshot_ts,
            secid,
            max(price) AS best_bid,
            argMax(quantity, price) AS best_bid_qty
        FROM raw.orderbook
        WHERE side = 'B'
        GROUP BY trade_date, snapshot_ts, secid
    ),
    best_ask AS
    (
        SELECT
            trade_date,
            snapshot_ts,
            secid,
            min(price) AS best_ask,
            argMin(quantity, price) AS best_ask_qty
        FROM raw.orderbook
        WHERE side = 'S'
        GROUP BY trade_date, snapshot_ts, secid
    )
SELECT
    b.trade_date,
    b.snapshot_ts,
    b.secid,
    b.best_bid,
    a.best_ask,
    b.best_bid_qty,
    a.best_ask_qty,
    a.best_ask - b.best_bid AS spread,
    (a.best_ask + b.best_bid) / 2 AS mid_price,
    if((b.best_bid_qty + a.best_ask_qty) = 0, NULL,
       (toFloat64(b.best_bid_qty) - toFloat64(a.best_ask_qty)) / (toFloat64(b.best_bid_qty) + toFloat64(a.best_ask_qty))) AS bbo_quantity_imbalance
FROM best_bid b
INNER JOIN best_ask a
    ON b.trade_date = a.trade_date
   AND b.snapshot_ts = a.snapshot_ts
   AND b.secid = a.secid;
