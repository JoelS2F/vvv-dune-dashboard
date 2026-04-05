-- Panel 9B: Pre-Ban vs Post-Ban Staking Comparison

-- PANEL 9B: Pre-Ban vs Post-Ban Staking Comparison
-- Summary counter showing acceleration factor
-- Ban timestamp: April 4, 2026 19:00 UTC (12pm PT)
-- Visualization: two big numbers side by side
WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff
      AND block_time >= DATE '2026-03-01'
),
first_stakes AS (
    SELECT staker, MIN(block_time) AS first_stake_time
    FROM staking_events
    GROUP BY staker
),
periods AS (
    SELECT
        CASE
            WHEN first_stake_time >= TIMESTAMP '2026-04-04 19:00:00'
                THEN 'POST_BAN'
            ELSE 'PRE_BAN'
        END AS period,
        staker,
        first_stake_time
    FROM first_stakes
    WHERE first_stake_time >= DATE '2026-03-04'     -- 30 days pre-ban window
)
SELECT
    period,
    COUNT(*) AS new_stakers,
    COUNT(*) * 1.0 / GREATEST(DATE_DIFF('day',
        MIN(first_stake_time),
        MAX(first_stake_time)
    ), 1) AS stakers_per_day,
    MIN(first_stake_time) AS period_start,
    MAX(first_stake_time) AS period_end
FROM periods
GROUP BY period
