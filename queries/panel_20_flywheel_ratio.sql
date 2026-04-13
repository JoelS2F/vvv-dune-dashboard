-- PANEL 20: Flywheel Health Ratio (Section 5 — Flywheel & Repricing)
-- Weekly burn-to-unstake ratio: >1.0 = flywheel tightening, <0.5 = leaking
-- Combines Panel 17 (burns) and Panel 19 (unstakes) logic

WITH weekly_burns AS (
    SELECT
        DATE_TRUNC('week', block_time) AS week,
        SUM(amount) AS tokens_burned
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x0000000000000000000000000000000000000000
      AND amount < 500000  -- exclude one-time airdrop burn
      AND block_time >= NOW() - INTERVAL '182' day
    GROUP BY 1
),
weekly_unstakes AS (
    SELECT
        DATE_TRUNC('week', block_time) AS week,
        SUM(amount) AS tokens_unstaked
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= NOW() - INTERVAL '182' day
    GROUP BY 1
),
combined AS (
    SELECT
        COALESCE(b.week, u.week) AS week,
        COALESCE(b.tokens_burned, 0) AS tokens_burned,
        COALESCE(u.tokens_unstaked, 0) AS tokens_unstaked
    FROM weekly_burns b
    FULL OUTER JOIN weekly_unstakes u ON b.week = u.week
)
SELECT
    week,
    tokens_burned,
    tokens_unstaked,
    COALESCE(
        tokens_burned / NULLIF(tokens_unstaked, 0),
        CASE WHEN tokens_burned > 0 THEN 999.0 ELSE 0 END
    ) AS flywheel_ratio,
    AVG(
        COALESCE(tokens_burned / NULLIF(tokens_unstaked, 0), 0)
    ) OVER (
        ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ) AS ratio_4w_ma,
    CASE
        WHEN COALESCE(tokens_burned / NULLIF(tokens_unstaked, 0), 0) >= 1.0 THEN 'TIGHTENING'
        WHEN COALESCE(tokens_burned / NULLIF(tokens_unstaked, 0), 0) >= 0.5 THEN 'BALANCED'
        ELSE 'LEAKING'
    END AS flywheel_status
FROM combined
ORDER BY week DESC
