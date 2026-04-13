-- DIAGNOSTIC: VVV burns (transfers to null address) on Base
-- Run this BEFORE deploying Panel 17 to verify burn data exists
-- Expect: ~3-4 monthly burns since Dec 2025

SELECT
    block_time,
    "from",
    amount AS vvv_burned,
    tx_hash
FROM tokens.transfers
WHERE blockchain = 'base'
  AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
  AND "to" = 0x0000000000000000000000000000000000000000
  AND block_time >= NOW() - INTERVAL '180' day
ORDER BY block_time DESC
LIMIT 20
