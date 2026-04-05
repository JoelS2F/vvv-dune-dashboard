-- PANEL 3: Holder Cohort Analysis by Wallet Age
-- Classifies current holders by when they first received VVV
-- Visualization: stacked area chart

WITH all_receipts AS (
    SELECT
        "to" AS wallet,
        MIN(block_time) AS first_received
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
    GROUP BY "to"
),
current_balances AS (
    -- Computed from cumulative transfers (balances.erc20_latest not available in DuneSQL)
    SELECT
        wallet,
        SUM(delta) / 1e18 AS vvv_balance
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
    HAVING SUM(delta) > 0
),
holder_cohorts AS (
    SELECT
        cb.wallet,
        cb.vvv_balance,
        ar.first_received,
        CASE
            WHEN ar.first_received >= NOW() - INTERVAL '24' hour THEN '< 24h'
            WHEN ar.first_received >= NOW() - INTERVAL '7' day THEN '1-7d'
            WHEN ar.first_received >= NOW() - INTERVAL '30' day THEN '7-30d'
            WHEN ar.first_received >= NOW() - INTERVAL '90' day THEN '30-90d'
            ELSE '90d+'
        END AS cohort
    FROM current_balances cb
    LEFT JOIN all_receipts ar ON cb.wallet = ar.wallet
)
SELECT
    cohort,
    COUNT(*) AS num_wallets,
    SUM(vvv_balance) AS total_vvv,
    SUM(vvv_balance) / NULLIF((SELECT SUM(vvv_balance) FROM holder_cohorts), 0) AS pct_of_supply,
    AVG(vvv_balance) AS avg_balance,
    APPROX_PERCENTILE(vvv_balance, 0.5) AS median_balance
FROM holder_cohorts
GROUP BY cohort
ORDER BY
    CASE cohort
        WHEN '< 24h' THEN 1
        WHEN '1-7d' THEN 2
        WHEN '7-30d' THEN 3
        WHEN '30-90d' THEN 4
        WHEN '90d+' THEN 5
    END
