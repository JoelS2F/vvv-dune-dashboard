-- PANEL 10C: Venice API Proxy Signal - VVV -> sVVV -> DIEM Conversion Funnel
-- Tracks the full journey: acquire VVV -> stake -> mint DIEM -> consume compute
-- Visualization: funnel chart or stacked bar
-- Post-ban window: all filters use DATE '2026-04-04' consistently
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH vvv_buyers AS (
    SELECT COUNT(DISTINCT taker) AS unique_buyers
    FROM dex.trades
    WHERE blockchain = 'base'
      AND token_bought_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= DATE '2026-04-04'
),
vvv_stakers AS (
    SELECT COUNT(DISTINCT "from") AS unique_stakers
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= DATE '2026-04-04'
),
diem_minters AS (
    SELECT COUNT(DISTINCT "to") AS unique_minters
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND "from" = 0x0000000000000000000000000000000000000000
      AND block_time >= DATE '2026-04-04'
)
SELECT
    'VVV Buyers (DEX)' AS stage, unique_buyers AS count FROM vvv_buyers
UNION ALL
SELECT
    'VVV Stakers' AS stage, unique_stakers AS count FROM vvv_stakers
UNION ALL
SELECT
    'DIEM Minters' AS stage, unique_minters AS count FROM diem_minters
