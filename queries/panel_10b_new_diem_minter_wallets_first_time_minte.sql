-- Panel 10B: New DIEM Minter Wallets (first-time minters)

-- PANEL 10B: New DIEM Minter Wallets (first-time minters)
-- Wallets minting DIEM for the first time = new compute consumers
-- Cross-reference with Panel 9 to see staker→minter conversion funnel
WITH mint_events AS (
    SELECT
        "to" AS minter,
        block_time,
        amount / 1e18 AS diem_amount
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND "from" = 0x0000000000000000000000000000000000000000
      AND block_time >= DATE '2026-03-01'
),
first_mints AS (
    SELECT
        minter,
        MIN(block_time) AS first_mint_time,
        SUM(diem_amount) AS total_diem_minted
    FROM mint_events
    GROUP BY minter
)
SELECT
    DATE_TRUNC('day', first_mint_time) AS day,
    COUNT(*) AS new_minters,
    SUM(total_diem_minted) AS total_diem_by_new_minters,
    AVG(total_diem_minted) AS avg_diem_per_new_minter,
    SUM(COUNT(*)) OVER (ORDER BY DATE_TRUNC('day', first_mint_time)) AS cumulative_minters,
    CASE
        WHEN DATE_TRUNC('day', first_mint_time) >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM first_mints
GROUP BY 1
ORDER BY 1
