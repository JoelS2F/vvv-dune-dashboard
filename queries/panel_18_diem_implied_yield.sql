-- PANEL 18: DIEM Implied Yield (Section 5 — Flywheel & Repricing)
-- Daily DIEM price from dex.trades (Aerodrome on Base), implied yield, discount vs perpetuity
-- DIEM token: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
-- Risk-free perpetuity benchmark: $365/5% = $7,300

WITH diem_trades AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        CASE
            WHEN token_bought_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
                THEN amount_usd / NULLIF(token_bought_amount, 0)
            WHEN token_sold_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
                THEN amount_usd / NULLIF(token_sold_amount, 0)
        END AS diem_price_usd,
        amount_usd
    FROM dex.trades
    WHERE blockchain = 'base'
      AND (
          token_bought_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
          OR token_sold_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      )
      AND amount_usd > 0
      AND block_time >= NOW() - INTERVAL '90' day
),
daily_stats AS (
    SELECT
        day,
        APPROX_PERCENTILE(diem_price_usd, 0.5) AS median_price,
        AVG(diem_price_usd) AS avg_price,
        SUM(amount_usd) AS daily_volume_usd,
        COUNT(*) AS trade_count
    FROM diem_trades
    WHERE diem_price_usd > 0
    GROUP BY 1
)
SELECT
    day,
    median_price,
    avg_price,
    daily_volume_usd,
    trade_count,
    365.0 / NULLIF(median_price, 0) AS implied_yield_pct,
    (7300.0 - median_price) / 7300.0 AS discount_vs_perpetuity,
    median_price - LAG(median_price, 30) OVER (ORDER BY day) AS price_change_30d,
    (365.0 / NULLIF(median_price, 0))
        - (365.0 / NULLIF(LAG(median_price, 30) OVER (ORDER BY day), 0))
        AS yield_change_30d
FROM daily_stats
ORDER BY day DESC
