-- Panel 10A: DIEM Mint Acceleration Ratio

-- PANEL 10A: DIEM Mint Acceleration Ratio
-- Compares each day's minting vs trailing 7-day average (excluding current day)
-- Visualization: bar chart with acceleration ratio line overlay
WITH daily_mints AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(amount / 1e18) AS diem_minted,
        COUNT(DISTINCT "to") AS unique_minters
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND "from" = 0x0000000000000000000000000000000000000000
      AND block_time >= DATE '2026-03-01'
    GROUP BY 1
)
SELECT
    day,
    diem_minted,
    unique_minters,
    AVG(diem_minted) OVER (
        ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ) AS seven_day_avg_prior,
    diem_minted / NULLIF(
        AVG(diem_minted) OVER (
            ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ), 0
    ) AS mint_acceleration_ratio,
    CASE
        WHEN day >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM daily_mints
ORDER BY day
