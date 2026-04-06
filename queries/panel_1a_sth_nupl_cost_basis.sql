-- PANEL 1A: New Entrant Acquisition Price & Unrealized PnL
-- Reconstructs Glassnode STH cost basis for ERC-20 on Base
-- Thresholds: EUPHORIA >40% gain for 80%+ wallets | CAPITULATION >20% loss for 70%+ wallets

WITH vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        block_number,
        amount AS vvv_amount,
        tx_hash
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '72' hour
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
),
-- First inbound transfer per wallet in the window = their "entry"
first_entry AS (
    SELECT
        wallet,
        MIN(block_time) AS entry_time,
        MIN(block_number) AS entry_block
    FROM vvv_transfers
    GROUP BY wallet
),
-- Match entry time to VVV price at that moment
entry_with_price AS (
    SELECT
        fe.wallet,
        fe.entry_time,
        p.price AS entry_price
    FROM first_entry fe
    LEFT JOIN prices.usd p
        ON p.blockchain = 'base'
        AND p.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
        AND p.minute = DATE_TRUNC('minute', fe.entry_time)
),
-- Get current VVV price (latest available)
current_price AS (
    SELECT price AS current_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
    ORDER BY minute DESC
    LIMIT 1
),
-- Compute unrealized PnL per wallet
wallet_pnl AS (
    SELECT
        e.wallet,
        e.entry_time,
        e.entry_price,
        cp.current_price,
        (cp.current_price - e.entry_price) / NULLIF(e.entry_price, 0) AS unrealized_pnl_pct
    FROM entry_with_price e
    CROSS JOIN current_price cp
    WHERE e.entry_price > 0
)
SELECT
    wallet,
    entry_time,
    entry_price,
    current_price,
    unrealized_pnl_pct,
    CASE
        WHEN unrealized_pnl_pct > 0.40 THEN 'EUPHORIA'
        WHEN unrealized_pnl_pct > 0.25 THEN 'GREED'
        WHEN unrealized_pnl_pct > 0.00 THEN 'HOPE'
        WHEN unrealized_pnl_pct > -0.20 THEN 'FEAR'
        ELSE 'CAPITULATION'
    END AS sentiment_phase
FROM wallet_pnl
ORDER BY unrealized_pnl_pct DESC
