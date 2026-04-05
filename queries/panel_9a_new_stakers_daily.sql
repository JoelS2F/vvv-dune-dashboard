-- PANEL 9A: Daily First-Time VVV Stakers
-- A spike post-April 4 2026 = OpenClaw migration signal
-- Visualization: bar chart with April 4 vertical annotation line
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time,
        amount / 1e18 AS vvv_staked
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= DATE '2026-03-01'
),
first_stakes AS (
    SELECT
        staker,
        MIN(block_time) AS first_stake_time,
        MIN(vvv_staked) AS first_stake_amount
    FROM staking_events
    GROUP BY staker
)
SELECT
    DATE_TRUNC('day', first_stake_time) AS day,
    COUNT(*) AS new_stakers,
    SUM(first_stake_amount) AS total_first_stake_vvv,
    AVG(first_stake_amount) AS avg_first_stake_size,
    SUM(COUNT(*)) OVER (ORDER BY DATE_TRUNC('day', first_stake_time)) AS cumulative_stakers,
    CASE
        WHEN DATE_TRUNC('day', first_stake_time) >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM first_stakes
GROUP BY 1
ORDER BY 1
