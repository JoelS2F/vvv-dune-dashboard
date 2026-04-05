-- PANEL 4: sVVV Staking Flows
-- Track VVV transfers TO the staking contract (stakes) vs FROM (unstakes)
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_flows AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount / 1e18
            ELSE 0
        END) AS tokens_staked,
        SUM(CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount / 1e18
            ELSE 0
        END) AS tokens_unstaked,
        COUNT(DISTINCT CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN "from"
        END) AS unique_stakers,
        COUNT(DISTINCT CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN "to"
        END) AS unique_unstakers
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '90' day
      AND (
          "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
          OR "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      )
    GROUP BY 1
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '90' day
    GROUP BY 1
)
SELECT
    sf.day,
    sf.tokens_staked,
    sf.tokens_unstaked,
    sf.tokens_staked - sf.tokens_unstaked AS net_staking,
    SUM(sf.tokens_staked - sf.tokens_unstaked) OVER (ORDER BY sf.day) AS cumulative_net_staked,
    (sf.tokens_staked - sf.tokens_unstaked) * p.avg_price AS net_staking_usd,
    sf.unique_stakers,
    sf.unique_unstakers
FROM staking_flows sf
LEFT JOIN daily_prices p ON sf.day = p.day
ORDER BY sf.day DESC
