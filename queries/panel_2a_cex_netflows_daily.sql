-- PANEL 2A: Daily CEX Netflows
-- Negative netflow = tokens leaving exchanges (bullish accumulation signal)
-- Two-layer CEX identification: Dune labels + hardcoded Coinbase Base wallets

WITH cex_addresses AS (
    -- Layer 1: Dune curated labels (auto-maintained, cross-chain)
    SELECT DISTINCT address
    FROM labels.owner_addresses
    WHERE custody_owner = 'Coinbase'
      AND blockchain = 'base'

    UNION

    -- Layer 2: Hardcoded Etherscan-labeled Coinbase wallets
    -- Source: Etherscan public labels + BaseScan multichain portfolio
    SELECT address FROM (
        VALUES
            (0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43), -- Coinbase (major hot wallet)
            (0x71660c4005ba85c37ccec55d0c4493e66fe775d3), -- Coinbase 1
            (0x503828976d22510aad0201ac7ec88293211d23da), -- Coinbase 12
            (0x3cd751e6b0078be393132286c442345e5dc49699), -- Coinbase 33
            (0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740), -- Coinbase 23
            (0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511), -- Coinbase 44
            (0xeb2629a2734e272bcc07bda959863f316f4bd4cf), -- Coinbase 54
            (0x7830c87c02e56aff27fa8ab1241711331fa86f43)  -- Coinbase: Deposit
    ) AS t(address)
),
inflows AS (
    -- Tokens going TO exchanges (potential sell pressure)
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount) AS tokens_in,
        COUNT(DISTINCT t."from") AS unique_depositors
    FROM tokens.transfers t
    JOIN cex_addresses cex ON t."to" = cex.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '30' day
    GROUP BY 1
),
outflows AS (
    -- Tokens leaving exchanges (accumulation / self-custody)
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount) AS tokens_out,
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
