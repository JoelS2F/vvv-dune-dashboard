-- PANEL 2B: Cumulative CEX Netflow (running total)
-- Shows whether exchanges are accumulating or draining over time
-- Visualization: area chart - below zero = bullish

WITH cex_addresses AS (
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
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
