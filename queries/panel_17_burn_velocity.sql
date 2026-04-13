-- PANEL 17: Burn Velocity (Section 5 — Flywheel & Repricing)
-- Weekly VVV burns (transfers to null address) with 4-week MA and WoW growth
-- Excludes one-time airdrop burn (> 500K VVV per event)
-- VVV token: 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf

WITH raw_burns AS (
    SELECT
        DATE_TRUNC('week', block_time) AS week,
        SUM(amount) AS tokens_burned,
        COUNT(*) AS burn_events
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x0000000000000000000000000000000000000000
      AND amount < 500000  -- exclude one-time airdrop burn (33.7M)
      AND block_time >= NOW() - INTERVAL '26' week
    GROUP BY 1
)
SELECT
    week,
    tokens_burned,
    burn_events,
    AVG(tokens_burned) OVER (
        ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ) AS burn_4w_ma,
    COALESCE(
        (tokens_burned - LAG(tokens_burned) OVER (ORDER BY week))
        / NULLIF(LAG(tokens_burned) OVER (ORDER BY week), 0),
        0
    ) AS wow_growth_rate
FROM raw_burns
ORDER BY week DESC
