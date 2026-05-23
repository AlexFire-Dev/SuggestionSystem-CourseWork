CREATE OR REPLACE VIEW dwh.fct_market_5m AS
SELECT
    o.trade_date AS trade_date,
    o.trade_time AS trade_time,
    o.event_time AS event_time,
    o.secid AS secid,

    i.shortname AS shortname,
    i.secname AS secname,

    o.spread_bbo AS spread_bbo,
    o.spread_lv10 AS spread_lv10,
    o.spread_1mio AS spread_1mio,
    o.levels_b AS levels_b,
    o.levels_s AS levels_s,
    o.vol_b AS book_vol_b,
    o.vol_s AS book_vol_s,
    o.val_b AS book_val_b,
    o.val_s AS book_val_s,
    o.imbalance_vol AS book_vol_imbalance,
    o.imbalance_val AS book_val_imbalance,
    o.imbalance_vol_bbo AS imbalance_vol_bbo,
    o.imbalance_val_bbo AS imbalance_val_bbo,
    o.vwap_b AS vwap_b,
    o.vwap_s AS vwap_s,
    o.vwap_b_1mio AS vwap_b_1mio,
    o.vwap_s_1mio AS vwap_s_1mio,
    (o.vwap_b_1mio + o.vwap_s_1mio) / 2 AS mid_1mio,
    if(((o.vwap_b_1mio + o.vwap_s_1mio) / 2) = 0, NULL,
       o.spread_1mio / ((o.vwap_b_1mio + o.vwap_s_1mio) / 2)) AS relative_spread_1mio,

    os.put_orders AS put_orders,
    os.put_orders_b AS put_orders_b,
    os.put_orders_s AS put_orders_s,
    os.put_vol AS put_vol,
    os.put_vol_b AS put_vol_b,
    os.put_vol_s AS put_vol_s,
    os.put_val AS put_val,
    os.put_val_b AS put_val_b,
    os.put_val_s AS put_val_s,
    os.put_vol_imbalance AS put_vol_imbalance,
    os.put_val_imbalance AS put_val_imbalance,

    os.cancel_orders AS cancel_orders,
    os.cancel_orders_b AS cancel_orders_b,
    os.cancel_orders_s AS cancel_orders_s,
    os.cancel_vol AS cancel_vol,
    os.cancel_vol_b AS cancel_vol_b,
    os.cancel_vol_s AS cancel_vol_s,
    os.cancel_val AS cancel_val,
    os.cancel_val_b AS cancel_val_b,
    os.cancel_val_s AS cancel_val_s,
    os.cancel_vol_imbalance AS cancel_vol_imbalance,
    os.cancel_val_imbalance AS cancel_val_imbalance,

    ts.pr_open AS pr_open,
    ts.pr_high AS pr_high,
    ts.pr_low AS pr_low,
    ts.pr_close AS pr_close,
    ts.pr_vwap AS pr_vwap,
    ts.pr_change AS pr_change,
    ts.vol AS trade_vol,
    ts.val AS trade_val,
    ts.trades AS trades,
    ts.trades_b AS trades_b,
    ts.trades_s AS trades_s,
    ts.trade_vol_imbalance AS trade_vol_imbalance,
    ts.trade_val_imbalance AS trade_val_imbalance,
    ts.disb AS trade_direction_imbalance
FROM stg.v_obstats AS o
LEFT JOIN stg.v_orderstats AS os
    ON o.trade_date = os.trade_date
   AND o.trade_time = os.trade_time
   AND o.secid = os.secid
LEFT JOIN stg.v_tradestats AS ts
    ON o.trade_date = ts.trade_date
   AND o.trade_time = ts.trade_time
   AND o.secid = ts.secid
LEFT JOIN stg.v_instruments_latest AS i
    ON o.secid = i.secid;


CREATE OR REPLACE VIEW mart.v_intraday_liquidity_state AS
SELECT
    trade_date,
    trade_time,
    event_time,
    secid,
    shortname,
    secname,

    spread_bbo,
    spread_lv10,
    spread_1mio,
    levels_b,
    levels_s,

    book_vol_b,
    book_vol_s,
    book_val_b,
    book_val_s,
    book_vol_imbalance,
    book_val_imbalance,
    imbalance_vol_bbo,
    imbalance_val_bbo,

    vwap_b,
    vwap_s,
    vwap_b_1mio,
    vwap_s_1mio,
    mid_1mio,
    relative_spread_1mio,

    put_orders,
    put_orders_b,
    put_orders_s,
    put_vol,
    put_vol_b,
    put_vol_s,
    put_val,
    put_val_b,
    put_val_s,
    put_vol_imbalance,
    put_val_imbalance,

    cancel_orders,
    cancel_orders_b,
    cancel_orders_s,
    cancel_vol,
    cancel_vol_b,
    cancel_vol_s,
    cancel_val,
    cancel_val_b,
    cancel_val_s,
    cancel_vol_imbalance,
    cancel_val_imbalance,

    pr_open,
    pr_high,
    pr_low,
    pr_close,
    pr_vwap,
    pr_change,

    trade_vol,
    trade_val,
    trades,
    trades_b,
    trades_s,
    trade_vol_imbalance,
    trade_val_imbalance,
    trade_direction_imbalance,

    multiIf(
        spread_bbo >= 2
            OR abs(book_vol_imbalance) >= 0.30
            OR abs(trade_direction_imbalance) >= 0.60,
        'liquidity_stress',

        put_vol_imbalance >= 0.30
            AND trade_direction_imbalance >= 0.30,
        'buy_pressure',

        put_vol_imbalance <= -0.30
            AND trade_direction_imbalance <= -0.30,
        'sell_pressure',

        cancel_vol_imbalance >= 0.30
            OR cancel_vol_imbalance <= -0.30,
        'active_cancellations',

        'normal'
    ) AS market_state
FROM dwh.fct_market_5m;


CREATE OR REPLACE VIEW mart.v_daily_instrument_summary AS
SELECT
    trade_date,
    secid,
    any(shortname) AS shortname,
    count() AS intervals,
    avg(spread_bbo) AS avg_spread_bbo,
    max(spread_bbo) AS max_spread_bbo,
    avg(book_vol_imbalance) AS avg_book_vol_imbalance,
    max(abs(book_vol_imbalance)) AS max_abs_book_vol_imbalance,
    sum(trade_vol) AS total_trade_vol,
    sum(trade_val) AS total_trade_val,
    sum(trades) AS total_trades,
    countIf(market_state = 'liquidity_stress') AS stress_intervals
FROM mart.v_intraday_liquidity_state
GROUP BY
    trade_date,
    secid;