-- Panel 6: DIEM Minting Activity (Venice Ecosystem Health)

-- PANEL 6: DIEM Token Activity
-- Minting (from 0x0) = new DIEM created by locking sVVV
-- Burns (to 0x0) = DIEM redeemed
WITH diem_activity AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "from" = 0x0000000000000000000000000000000000000000
                THEN amount / 1e18 ELSE 0
        END) AS diem_minted,
        SUM(CASE
            WHEN "to" = 0x0000000000000000000000000000000000000000
                THEN amount / 1e18 ELSE 0
        END) AS diem_burned,
        COUNT(DISTINCT CASE
            WHEN "from" = 0x0000000000000000000000000000000000000000
                THEN "to"
        END) AS unique_minters
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND block_time >= NOW() - INTERVAL '90' day
    GROUP BY 1
)
SELECT
    day,
    diem_minted,
    diem_burned,
    diem_minted - diem_burned AS net_diem,
    SUM(diem_minted - diem_burned) OVER (ORDER BY day) AS cumulative_diem_supply,
    unique_minters
FROM diem_activity
ORDER BY day DESC
