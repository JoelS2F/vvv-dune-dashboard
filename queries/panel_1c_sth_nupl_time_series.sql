-- PANEL 1C: STH-NUPL Time Series (daily rolling 72hr window)
-- Tracks how new entrant sentiment evolves over time
-- Visualization: line chart with colored phase bands

WITH date_series AS (
    SELECT dt
    FROM UNNEST(SEQUENCE(
        CURRENT_DATE - INTERVAL '30' day,
        CURRENT_DATE,
        INTERVAL '1' day
    )) AS t(dt)
),
vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        DATE_TRUNC('day', block_time) AS transfer_day,
        amount AS vvv_amount
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= CURRENT_DATE - INTERVAL '33' day  -- 30 days + 3 day lookback
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS price_day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= CURRENT_DATE - INTERVAL '33' day
    GROUP BY 1
),
-- For each day, find wallets that entered in the prior 72hr window
daily_entrants AS (
    SELECT
        ds.dt AS snapshot_date,
        t.wallet,
        MIN(t.block_time) AS entry_time
    FROM date_series ds
    JOIN vvv_transfers t
        ON t.block_time >= ds.dt - INTERVAL '3' day
        AND t.block_time < ds.dt + INTERVAL '1' day
    GROUP BY ds.dt, t.wallet
),
daily_pnl AS (
    SELECT
        de.snapshot_date,
        de.wallet,
        ep.avg_price AS entry_price,
        sp.avg_price AS snapshot_price,
        (sp.avg_price - ep.avg_price) / NULLIF(ep.avg_price, 0) AS pnl
    FROM daily_entrants de
    LEFT JOIN daily_prices ep ON ep.price_day = DATE_TRUNC('day', de.entry_time)
    LEFT JOIN daily_prices sp ON sp.price_day = de.snapshot_date
    WHERE ep.avg_price > 0
)
SELECT
    snapshot_date,
    COUNT(*) AS new_wallets,
    AVG(pnl) AS mean_sth_nupl,
    APPROX_PERCENTILE(pnl, 0.5) AS median_sth_nupl,
    COUNT(*) FILTER (WHERE pnl > 0) * 1.0 / NULLIF(COUNT(*), 0) AS pct_in_profit,
    COUNT(*) FILTER (WHERE pnl > 0.40) * 1.0 / NULLIF(COUNT(*), 0) AS pct_euphoria
FROM daily_pnl
GROUP BY snapshot_date
ORDER BY snapshot_date
