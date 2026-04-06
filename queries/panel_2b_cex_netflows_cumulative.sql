-- PANEL 2B: Cumulative CEX Netflow (running total)
-- Shows whether exchanges are accumulating or draining over time
-- Visualization: area chart - below zero = bullish

WITH cex_addresses AS (
    -- Layer 1: Dune curated labels (auto-maintained, cross-chain)
    SELECT DISTINCT address
    FROM labels.owner_addresses
    WHERE custody_owner = 'Coinbase'
      AND blockchain = 'base'

    UNION

    -- Layer 2: Hardcoded Etherscan-labeled Coinbase wallets
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
daily_flows AS (
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(CASE WHEN cex_to.address IS NOT NULL THEN t.amount / 1e18 ELSE 0 END) AS inflow,
        SUM(CASE WHEN cex_from.address IS NOT NULL THEN t.amount / 1e18 ELSE 0 END) AS outflow
    FROM tokens.transfers t
    LEFT JOIN cex_addresses cex_to ON t."to" = cex_to.address
    LEFT JOIN cex_addresses cex_from ON t."from" = cex_from.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '90' day
      AND (cex_to.address IS NOT NULL OR cex_from.address IS NOT NULL)
    GROUP BY 1
)
SELECT
    day,
    outflow - inflow AS daily_net,
    SUM(outflow - inflow) OVER (ORDER BY day) AS cumulative_net_flow
FROM daily_flows
ORDER BY day
