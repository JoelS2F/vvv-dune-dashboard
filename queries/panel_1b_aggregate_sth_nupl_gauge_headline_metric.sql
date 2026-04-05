-- Panel 1B: Aggregate STH-NUPL Gauge (headline metric)

-- PANEL 1B: Aggregate STH-NUPL Gauge (single number + phase)
-- This is the headline metric for the dashboard
WITH vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        amount / 1e18 AS vvv_amount
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '72' hour
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
),
first_entry AS (
    SELECT wallet, MIN(block_time) AS entry_time
    FROM vvv_transfers
    GROUP BY wallet
),
entry_with_price AS (
    SELECT
        fe.wallet,
        p.price AS entry_price
    FROM first_entry fe
    LEFT JOIN prices.usd p
        ON p.blockchain = 'base'
        AND p.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
        AND p.minute = DATE_TRUNC('minute', fe.entry_time)
    WHERE p.price > 0
),
current_price AS (
    SELECT price AS current_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
    ORDER BY minute DESC
    LIMIT 1
)
SELECT
    COUNT(*) AS total_new_wallets,
    AVG((cp.current_price - e.entry_price) / e.entry_price) AS mean_unrealized_pnl,
    APPROX_PERCENTILE((cp.current_price - e.entry_price) / e.entry_price, 0.5) AS median_unrealized_pnl,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0) * 1.0 / COUNT(*) AS pct_in_profit,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.40) * 1.0 / COUNT(*) AS pct_euphoria,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < -0.20) * 1.0 / COUNT(*) AS pct_capitulation,
    CASE
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.40) * 1.0 / COUNT(*) >= 0.80 THEN 'EUPHORIA'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.25) * 1.0 / COUNT(*) >= 0.60 THEN 'GREED'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < -0.20) * 1.0 / COUNT(*) >= 0.70 THEN 'CAPITULATION'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < 0) * 1.0 / COUNT(*) >= 0.50 THEN 'FEAR'
        ELSE 'NEUTRAL'
    END AS regime_signal
FROM entry_with_price e
CROSS JOIN current_price cp
