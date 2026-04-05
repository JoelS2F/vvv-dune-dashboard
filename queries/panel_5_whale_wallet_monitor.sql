-- PANEL 5: Top Holder Balance Changes (7-day delta)
-- Identifies accumulation or distribution by large wallets

WITH current_balances AS (
    -- Computed from cumulative transfers (balances.erc20_latest not available in DuneSQL)
    SELECT
        wallet,
        SUM(delta) / 1e18 AS current_balance
    FROM (
        SELECT "to" AS wallet, CAST(amount AS DOUBLE) AS delta
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
        UNION ALL
        SELECT "from" AS wallet, -CAST(amount AS DOUBLE) AS delta
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
    ) t
    WHERE wallet != 0x0000000000000000000000000000000000000000
    GROUP BY wallet
    HAVING SUM(delta) / 1e18 > 1000  -- minimum 1K VVV to qualify as whale
),
-- Net transfers in the last 7 days per wallet
recent_net_transfers AS (
    SELECT
        wallet,
        SUM(net_amount) AS seven_day_change
    FROM (
        -- Inflows
        SELECT "to" AS wallet, SUM(amount / 1e18) AS net_amount
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '7' day
        GROUP BY "to"

        UNION ALL

        -- Outflows (negative)
        SELECT "from" AS wallet, -SUM(amount / 1e18) AS net_amount
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '7' day
        GROUP BY "from"
    ) sub
    GROUP BY wallet
),
-- Exclude known contracts/exchanges
cex_addresses AS (
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
)
SELECT
    cb.wallet,
    COALESCE(l.name, CAST(cb.wallet AS VARCHAR)) AS label,
    cb.current_balance,
    COALESCE(rnt.seven_day_change, 0) AS seven_day_change,
    COALESCE(rnt.seven_day_change, 0) / NULLIF(cb.current_balance - COALESCE(rnt.seven_day_change, 0), 0) AS pct_change,
    CASE
        WHEN COALESCE(rnt.seven_day_change, 0) > 0 THEN 'ACCUMULATING'
        WHEN COALESCE(rnt.seven_day_change, 0) < 0 THEN 'DISTRIBUTING'
        ELSE 'FLAT'
    END AS behavior
FROM current_balances cb
LEFT JOIN recent_net_transfers rnt ON cb.wallet = rnt.wallet
LEFT JOIN labels.addresses l
    ON cb.wallet = l.address AND l.blockchain = 'base'
LEFT JOIN cex_addresses cex ON cb.wallet = cex.address
WHERE cex.address IS NULL  -- exclude CEX wallets
  AND cb.wallet != 0x0000000000000000000000000000000000000000
ORDER BY cb.current_balance DESC
LIMIT 30
