-- PANEL 19: sVVV Net Staking Flow (Section 5 — Flywheel & Repricing)
-- Daily staking/unstaking flows with 7d/30d MAs and trend classification
-- sVVV staking: 0x321b7ff75154472B18EDb199033fF4D116F340Ff
-- VVV token: 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf

WITH daily_flows AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
            ELSE 0
        END) AS vvv_staked,
        SUM(CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
            ELSE 0
        END) AS vvv_unstaked,
        COUNT(*) FILTER (
            WHERE "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
        ) AS stake_count,
        COUNT(*) FILTER (
            WHERE "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
        ) AS unstake_count
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '90' day
      AND (
          "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
          OR "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      )
    GROUP BY 1
)
SELECT
    day,
    vvv_staked,
    vvv_unstaked,
    vvv_staked - vvv_unstaked AS net_flow,
    stake_count,
    unstake_count,
    SUM(vvv_staked - vvv_unstaked) OVER (ORDER BY day) AS cumulative_net_staked,
    AVG(vvv_staked - vvv_unstaked) OVER (
        ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS net_flow_7d_ma,
    AVG(vvv_staked - vvv_unstaked) OVER (
        ORDER BY day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS net_flow_30d_ma,
    CASE
        WHEN AVG(vvv_staked - vvv_unstaked) OVER (
            ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) > 1000 THEN 'ACCUMULATING'
        WHEN AVG(vvv_staked - vvv_unstaked) OVER (
            ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) < -1000 THEN 'DISTRIBUTING'
        ELSE 'NEUTRAL'
    END AS trend
FROM daily_flows
ORDER BY day DESC
