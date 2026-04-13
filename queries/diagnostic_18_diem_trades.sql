-- DIAGNOSTIC: DIEM trades on Base DEXes
-- Run this BEFORE deploying Panel 18 to verify DIEM trade data exists
-- Expect: DIEM/WETH or DIEM/USDC trades on Aerodrome

SELECT
    block_time,
    token_bought_amount,
    token_sold_amount,
    amount_usd,
    project
FROM dex.trades
WHERE blockchain = 'base'
  AND (
      token_bought_address = 0xf4d97f2da56e8c3098f3a8d538db636a2606a024
      OR token_sold_address = 0xf4d97f2da56e8c3098f3a8d538db636a2606a024
  )
  AND block_time >= NOW() - INTERVAL '180' day
ORDER BY block_time DESC
LIMIT 20
