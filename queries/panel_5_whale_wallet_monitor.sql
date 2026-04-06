-- PANEL 5: Top Holder Balance Changes (7-day delta)
-- Identifies accumulation or distribution by large wallets

WITH current_balances AS (
    -- Approximate balances from last 90 days of transfers
    -- (full history scan times out on Dune free tier)
    SELECT
        wallet,
        SUM(delta) / 1e18 AS current_balance
    FROM (
        SELECT "to" AS wallet, CAST(amount AS DOUBLE) AS delta
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '90' day
        UNION ALL
        SELECT "from" AS wallet, -CAST(amount AS DOUBLE) AS delta
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '90' day
    ) t
    WHERE wallet != 0x0000000000000000000000000000000000000000
    GROUP BY wallet
    HAVING SUM(delta) / 1e18 > 1000  -- minimum 1K VVV net flow in 90d window
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
    -- Layer 1: Dune curated labels
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
