-- PANEL 7: DEX Buy/Sell Ratio
-- Uses dex.trades to classify trade direction
-- Buy = VVV is token_bought | Sell = VVV is token_sold

WITH vvv_dex_trades AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        CASE
            WHEN token_bought_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf THEN 'BUY'
            WHEN token_sold_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf THEN 'SELL'
        END AS direction,
        amount_usd,
        taker
    FROM dex.trades
    WHERE blockchain = 'base'
      AND (
          token_bought_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          OR token_sold_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      )
      AND block_time >= NOW() - INTERVAL '30' day
)
SELECT
    day,
    COUNT(*) FILTER (WHERE direction = 'BUY') AS buy_count,
    COUNT(*) FILTER (WHERE direction = 'SELL') AS sell_count,
    SUM(amount_usd) FILTER (WHERE direction = 'BUY') AS buy_volume_usd,
    SUM(amount_usd) FILTER (WHERE direction = 'SELL') AS sell_volume_usd,
    COUNT(DISTINCT taker) FILTER (WHERE direction = 'BUY') AS unique_buyers,
    COUNT(DISTINCT taker) FILTER (WHERE direction = 'SELL') AS unique_sellers,
    COALESCE(
        SUM(amount_usd) FILTER (WHERE direction = 'BUY')
        / NULLIF(SUM(amount_usd) FILTER (WHERE direction = 'SELL'), 0),
        0
    ) AS buy_sell_ratio
FROM vvv_dex_trades
GROUP BY day
ORDER BY day DESC
