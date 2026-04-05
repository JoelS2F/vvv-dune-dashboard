-- Panel 2A: Daily CEX Netflows

-- PANEL 2A: Daily CEX Netflows
-- Negative netflow = tokens leaving exchanges (bullish accumulation signal)
-- Multi-source CEX identification: cex.addresses + labels.addresses + manual list

WITH cex_addresses AS (
    -- Primary: Dune's curated CEX table (most reliable for Base)
    SELECT DISTINCT address
    FROM cex.addresses
    WHERE blockchain = 'base'
    UNION
    -- Fallback: labels.addresses filtered to cex
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
    UNION
    -- Manual supplementation: known Coinbase Base hot wallets
    -- (Replace/extend as BaseScan coverage improves)
    SELECT address FROM (VALUES
        -- Coinbase institutional hot wallets on Base (verify on BaseScan)
        (0x20fe562d797a42dcb3399062ae9546cd06f63280),  -- Coinbase 10 (common)
        (0x71660c4005ba85c37ccec55d0c4493e66fe775d3)   -- Coinbase 6 (common)
    ) AS t(address)
),
inflows AS (
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount / 1e18) AS tokens_in,
        COUNT(DISTINCT t."from") AS unique_depositors
    FROM tokens.transfers t
    JOIN cex_addresses cex ON t."to" = cex.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '30' day
    GROUP BY 1
),
outflows AS (
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount / 1e18) AS tokens_out,
        COUNT(DISTINCT t."to") AS unique_withdrawers
    FROM tokens.transfers t
    JOIN cex_addresses cex ON t."from" = cex.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '30' day
    GROUP BY 1
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '30' day
    GROUP BY 1
)
SELECT
    COALESCE(i.day, o.day) AS day,
    COALESCE(i.tokens_in, 0) AS cex_inflow_tokens,
    COALESCE(o.tokens_out, 0) AS cex_outflow_tokens,
    COALESCE(o.tokens_out, 0) - COALESCE(i.tokens_in, 0) AS net_flow_tokens,
    (COALESCE(o.tokens_out, 0) - COALESCE(i.tokens_in, 0)) * p.avg_price AS net_flow_usd,
    COALESCE(i.unique_depositors, 0) AS depositors,
    COALESCE(o.unique_withdrawers, 0) AS withdrawers,
    p.avg_price AS vvv_price
FROM inflows i
FULL OUTER JOIN outflows o ON i.day = o.day
LEFT JOIN daily_prices p ON COALESCE(i.day, o.day) = p.day
ORDER BY day DESC
