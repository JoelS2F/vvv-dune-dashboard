-- Panel 8: Transfer Volume vs Price (Divergence Detection)

-- PANEL 8: Transfer Volume vs Price Overlay
-- Visualization: dual-axis chart (volume bars + price line)
SELECT
    DATE_TRUNC('day', t.block_time) AS day,
    COUNT(*) AS num_transfers,
    COUNT(DISTINCT t."from") + COUNT(DISTINCT t."to") AS active_addresses,
    SUM(t.amount / 1e18) AS total_vvv_transferred,
    SUM(t.amount / 1e18) * p.avg_price AS volume_usd,
    p.avg_price AS vvv_price
FROM tokens.transfers t
LEFT JOIN (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '90' day
    GROUP BY 1
) p ON DATE_TRUNC('day', t.block_time) = p.day
WHERE t.blockchain = 'base'
  AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
  AND t.block_time >= NOW() - INTERVAL '90' day
GROUP BY DATE_TRUNC('day', t.block_time), p.avg_price
ORDER BY day DESC
