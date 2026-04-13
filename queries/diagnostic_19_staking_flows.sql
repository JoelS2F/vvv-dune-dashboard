-- DIAGNOSTIC: Daily VVV staking/unstaking flows to sVVV contract
-- Run this BEFORE deploying Panel 19 to verify staking flow data
-- Expect: daily stake/unstake activity over last 30 days

SELECT
    DATE_TRUNC('day', block_time) AS day,
    COUNT(*) FILTER (
        WHERE "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
    ) AS transfers_in,
    SUM(CASE
        WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
        ELSE 0
    END) AS vvv_in,
    COUNT(*) FILTER (
        WHERE "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
    ) AS transfers_out,
    SUM(CASE
        WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
        ELSE 0
    END) AS vvv_out,
    SUM(CASE
        WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
        WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN -amount
        ELSE 0
    END) AS net_flow
FROM tokens.transfers
WHERE blockchain = 'base'
  AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
  AND block_time >= NOW() - INTERVAL '30' day
  AND (
      "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      OR "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
  )
GROUP BY 1
ORDER BY 1 DESC
