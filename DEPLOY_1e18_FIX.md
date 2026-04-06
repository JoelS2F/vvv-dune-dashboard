# VVV Dune Dashboard — 1e18 Fix Deployment
**Issue:** `tokens.transfers` on Base stores VVV amounts in human-readable units.
All `/ 1e18` divisions have been removed. 13 queries need re-pasting on Dune.

**Instructions:** For each query: open the Dune URL → select all → paste updated SQL → Save → Run

---

## Checklist

- [ ]  1. Whale Wallet Monitor — [dune.com/queries/6953189](https://dune.com/queries/6953189)
- [ ]  2. sVVV Staking Flows — [dune.com/queries/6953185](https://dune.com/queries/6953185)
- [ ]  3. Transfer Volume vs Price — [dune.com/queries/6953054](https://dune.com/queries/6953054)
- [ ]  4. STH-NUPL Cost Basis Distribution — [dune.com/queries/6953031](https://dune.com/queries/6953031)
- [ ]  5. STH-NUPL Aggregate Gauge — [dune.com/queries/6953009](https://dune.com/queries/6953009)
- [ ]  6. STH-NUPL Time Series (30d) — [dune.com/queries/6953035](https://dune.com/queries/6953035)
- [ ]  7. CEX Netflows (Daily) — [dune.com/queries/6953018](https://dune.com/queries/6953018)
- [ ]  8. CEX Netflows (Cumulative) — [dune.com/queries/6953223](https://dune.com/queries/6953223)
- [ ]  9. Holder Vintage Bands — [dune.com/queries/6953042](https://dune.com/queries/6953042)
- [ ] 10. DIEM Minting Activity — [dune.com/queries/6953202](https://dune.com/queries/6953202)
- [ ] 11. First-Time Stakers Daily — [dune.com/queries/6953024](https://dune.com/queries/6953024)
- [ ] 12. DIEM Mint Acceleration Ratio — [dune.com/queries/6953027](https://dune.com/queries/6953027)
- [ ] 13. New DIEM Minter Wallets — [dune.com/queries/6953217](https://dune.com/queries/6953217)

---

## 1. Whale Wallet Monitor

**Dune URL:** https://dune.com/queries/6953189

```sql
-- PANEL 5: Top Holder Balance Changes (7-day delta)
-- Identifies accumulation or distribution by large wallets

WITH current_balances AS (
    -- Approximate balances from last 90 days of transfers
    -- (full history scan times out on Dune free tier)
    SELECT
        wallet,
        SUM(delta) AS current_balance
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
    HAVING SUM(delta) > 1000  -- minimum 1K VVV net flow in 90d window
),
-- Net transfers in the last 7 days per wallet
recent_net_transfers AS (
    SELECT
        wallet,
        SUM(net_amount) AS seven_day_change
    FROM (
        -- Inflows
        SELECT "to" AS wallet, SUM(amount) AS net_amount
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '7' day
        GROUP BY "to"

        UNION ALL

        -- Outflows (negative)
        SELECT "from" AS wallet, -SUM(amount) AS net_amount
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
```

---

## 2. sVVV Staking Flows

**Dune URL:** https://dune.com/queries/6953185

```sql
-- PANEL 4: sVVV Staking Flows
-- Track VVV transfers TO the staking contract (stakes) vs FROM (unstakes)
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_flows AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
            ELSE 0
        END) AS tokens_staked,
        SUM(CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount
            ELSE 0
        END) AS tokens_unstaked,
        COUNT(DISTINCT CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN "from"
        END) AS unique_stakers,
        COUNT(DISTINCT CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN "to"
        END) AS unique_unstakers
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '90' day
      AND (
          "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
          OR "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      )
    GROUP BY 1
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '90' day
    GROUP BY 1
)
SELECT
    sf.day,
    sf.tokens_staked,
    sf.tokens_unstaked,
    sf.tokens_staked - sf.tokens_unstaked AS net_staking,
    SUM(sf.tokens_staked - sf.tokens_unstaked) OVER (ORDER BY sf.day) AS cumulative_net_staked,
    (sf.tokens_staked - sf.tokens_unstaked) * p.avg_price AS net_staking_usd,
    sf.unique_stakers,
    sf.unique_unstakers
FROM staking_flows sf
LEFT JOIN daily_prices p ON sf.day = p.day
ORDER BY sf.day DESC
```

---

## 3. Transfer Volume vs Price

**Dune URL:** https://dune.com/queries/6953054

```sql
-- PANEL 8: Transfer Volume vs Price Overlay
-- Visualization: dual-axis chart (volume bars + price line)

SELECT
    DATE_TRUNC('day', t.block_time) AS day,
    COUNT(*) AS num_transfers,
    COUNT(DISTINCT t."from") + COUNT(DISTINCT t."to") AS active_addresses,
    SUM(t.amount) AS total_vvv_transferred,
    SUM(t.amount) * p.avg_price AS volume_usd,
    p.avg_price AS vvv_price
FROM tokens.transfers t
LEFT JOIN (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '90' day
    GROUP BY 1
) p ON DATE_TRUNC('day', t.block_time) = p.day
WHERE t.blockchain = 'base'
  AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
  AND t.block_time >= NOW() - INTERVAL '90' day
GROUP BY DATE_TRUNC('day', t.block_time), p.avg_price
ORDER BY day DESC
```

---

## 4. STH-NUPL Cost Basis Distribution

**Dune URL:** https://dune.com/queries/6953031

```sql
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
```

---

## 5. STH-NUPL Aggregate Gauge

**Dune URL:** https://dune.com/queries/6953009

```sql
-- PANEL 1B: Aggregate STH-NUPL Gauge (single number + phase)
-- Headline metric for the dashboard

WITH vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        amount AS vvv_amount
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '72' hour
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
),
first_entry AS (
    SELECT wallet, MIN(block_time) AS entry_time
    FROM vvv_transfers
    GROUP BY wallet
),
entry_with_price AS (
    SELECT
        fe.wallet,
        p.price AS entry_price
    FROM first_entry fe
    LEFT JOIN prices.usd p
        ON p.blockchain = 'base'
        AND p.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
        AND p.minute = DATE_TRUNC('minute', fe.entry_time)
    WHERE p.price > 0
),
current_price AS (
    SELECT price AS current_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
    ORDER BY minute DESC
    LIMIT 1
)
SELECT
    COUNT(*) AS total_new_wallets,
    AVG((cp.current_price - e.entry_price) / e.entry_price) AS mean_unrealized_pnl,
    APPROX_PERCENTILE((cp.current_price - e.entry_price) / e.entry_price, 0.5) AS median_unrealized_pnl,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0) * 1.0 / COUNT(*) AS pct_in_profit,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.40) * 1.0 / COUNT(*) AS pct_euphoria,
    COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < -0.20) * 1.0 / COUNT(*) AS pct_capitulation,
    CASE
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.40) * 1.0 / COUNT(*) >= 0.80 THEN 'EUPHORIA'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price > 0.25) * 1.0 / COUNT(*) >= 0.60 THEN 'GREED'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < -0.20) * 1.0 / COUNT(*) >= 0.70 THEN 'CAPITULATION'
        WHEN COUNT(*) FILTER (WHERE (cp.current_price - e.entry_price) / e.entry_price < 0) * 1.0 / COUNT(*) >= 0.50 THEN 'FEAR'
        ELSE 'NEUTRAL'
    END AS regime_signal
FROM entry_with_price e
CROSS JOIN current_price cp
```

---

## 6. STH-NUPL Time Series (30d)

**Dune URL:** https://dune.com/queries/6953035

```sql
-- PANEL 1C: STH-NUPL Time Series (daily rolling 72hr window)
-- Tracks how new entrant sentiment evolves over time
-- Visualization: line chart with colored phase bands

WITH date_series AS (
    SELECT dt
    FROM UNNEST(SEQUENCE(
        CURRENT_DATE - INTERVAL '30' day,
        CURRENT_DATE,
        INTERVAL '1' day
    )) AS t(dt)
),
vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        DATE_TRUNC('day', block_time) AS transfer_day,
        amount AS vvv_amount
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= CURRENT_DATE - INTERVAL '33' day  -- 30 days + 3 day lookback
      AND "to" != 0x0000000000000000000000000000000000000000
      AND amount > 0
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS price_day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= CURRENT_DATE - INTERVAL '33' day
    GROUP BY 1
),
-- For each day, find wallets that entered in the prior 72hr window
daily_entrants AS (
    SELECT
        ds.dt AS snapshot_date,
        t.wallet,
        MIN(t.block_time) AS entry_time
    FROM date_series ds
    JOIN vvv_transfers t
        ON t.block_time >= ds.dt - INTERVAL '3' day
        AND t.block_time < ds.dt + INTERVAL '1' day
    GROUP BY ds.dt, t.wallet
),
daily_pnl AS (
    SELECT
        de.snapshot_date,
        de.wallet,
        ep.avg_price AS entry_price,
        sp.avg_price AS snapshot_price,
        (sp.avg_price - ep.avg_price) / NULLIF(ep.avg_price, 0) AS pnl
    FROM daily_entrants de
    LEFT JOIN daily_prices ep ON ep.price_day = DATE_TRUNC('day', de.entry_time)
    LEFT JOIN daily_prices sp ON sp.price_day = de.snapshot_date
    WHERE ep.avg_price > 0
)
SELECT
    snapshot_date,
    COUNT(*) AS new_wallets,
    AVG(pnl) AS mean_sth_nupl,
    APPROX_PERCENTILE(pnl, 0.5) AS median_sth_nupl,
    COUNT(*) FILTER (WHERE pnl > 0) * 1.0 / NULLIF(COUNT(*), 0) AS pct_in_profit,
    COUNT(*) FILTER (WHERE pnl > 0.40) * 1.0 / NULLIF(COUNT(*), 0) AS pct_euphoria
FROM daily_pnl
GROUP BY snapshot_date
ORDER BY snapshot_date
```

---

## 7. CEX Netflows (Daily)

**Dune URL:** https://dune.com/queries/6953018

```sql
-- PANEL 2A: Daily CEX Netflows
-- Negative netflow = tokens leaving exchanges (bullish accumulation signal)
-- Two-layer CEX identification: Dune labels + hardcoded Coinbase Base wallets

WITH cex_addresses AS (
    -- Layer 1: Dune curated labels (auto-maintained, cross-chain)
    SELECT DISTINCT address
    FROM labels.owner_addresses
    WHERE custody_owner = 'Coinbase'
      AND blockchain = 'base'

    UNION

    -- Layer 2: Hardcoded Etherscan-labeled Coinbase wallets
    -- Source: Etherscan public labels + BaseScan multichain portfolio
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
),
inflows AS (
    -- Tokens going TO exchanges (potential sell pressure)
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount) AS tokens_in,
        COUNT(DISTINCT t."from") AS unique_depositors
    FROM tokens.transfers t
    JOIN cex_addresses cex ON t."to" = cex.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '30' day
    GROUP BY 1
),
outflows AS (
    -- Tokens leaving exchanges (accumulation / self-custody)
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount) AS tokens_out,
        COUNT(DISTINCT t."to") AS unique_withdrawers
    FROM tokens.transfers t
    JOIN cex_addresses cex ON t."from" = cex.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '30' day
    GROUP BY 1
),
daily_prices AS (
    SELECT
        DATE_TRUNC('day', minute) AS day,
        AVG(price) AS avg_price
    FROM prices.usd
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND minute >= NOW() - INTERVAL '30' day
    GROUP BY 1
)
SELECT
    COALESCE(i.day, o.day) AS day,
    COALESCE(i.tokens_in, 0) AS cex_inflow_tokens,
    COALESCE(o.tokens_out, 0) AS cex_outflow_tokens,
    COALESCE(o.tokens_out, 0) - COALESCE(i.tokens_in, 0) AS net_flow_tokens,
    (COALESCE(o.tokens_out, 0) - COALESCE(i.tokens_in, 0)) * p.avg_price AS net_flow_usd,
    COALESCE(i.unique_depositors, 0) AS depositors,
    COALESCE(o.unique_withdrawers, 0) AS withdrawers,
    p.avg_price AS vvv_price
FROM inflows i
FULL OUTER JOIN outflows o ON i.day = o.day
LEFT JOIN daily_prices p ON COALESCE(i.day, o.day) = p.day
ORDER BY day DESC
```

---

## 8. CEX Netflows (Cumulative)

**Dune URL:** https://dune.com/queries/6953223

```sql
-- PANEL 2B: Cumulative CEX Netflow (running total)
-- Shows whether exchanges are accumulating or draining over time
-- Visualization: area chart - below zero = bullish

WITH cex_addresses AS (
    -- Layer 1: Dune curated labels (auto-maintained, cross-chain)
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
),
daily_flows AS (
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(CASE WHEN cex_to.address IS NOT NULL THEN t.amount ELSE 0 END) AS inflow,
        SUM(CASE WHEN cex_from.address IS NOT NULL THEN t.amount ELSE 0 END) AS outflow
    FROM tokens.transfers t
    LEFT JOIN cex_addresses cex_to ON t."to" = cex_to.address
    LEFT JOIN cex_addresses cex_from ON t."from" = cex_from.address
    WHERE t.blockchain = 'base'
      AND t.contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND t.block_time >= NOW() - INTERVAL '90' day
      AND (cex_to.address IS NOT NULL OR cex_from.address IS NOT NULL)
    GROUP BY 1
)
SELECT
    day,
    outflow - inflow AS daily_net,
    SUM(outflow - inflow) OVER (ORDER BY day) AS cumulative_net_flow
FROM daily_flows
ORDER BY day
```

---

## 9. Holder Vintage Bands

**Dune URL:** https://dune.com/queries/6953042

```sql
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
        SUM(delta) AS vvv_balance
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
```

---

## 10. DIEM Minting Activity

**Dune URL:** https://dune.com/queries/6953202

```sql
-- PANEL 6: DIEM Token Activity
-- Minting (from 0x0) = new DIEM created by locking sVVV
-- Burns (to 0x0) = DIEM redeemed
-- DIEM contract on Base: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024

WITH diem_activity AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "from" = 0x0000000000000000000000000000000000000000
            THEN amount ELSE 0
        END) AS diem_minted,
        SUM(CASE
            WHEN "to" = 0x0000000000000000000000000000000000000000
            THEN amount ELSE 0
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
```

---

## 11. First-Time Stakers Daily

**Dune URL:** https://dune.com/queries/6953024

```sql
-- PANEL 9A: Daily First-Time VVV Stakers
-- A spike post-April 4 2026 = OpenClaw migration signal
-- Visualization: bar chart with April 4 vertical annotation line
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time,
        amount AS vvv_staked
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= DATE '2026-03-01'
),
first_stakes AS (
    SELECT
        staker,
        MIN(block_time) AS first_stake_time,
        MIN(vvv_staked) AS first_stake_amount
    FROM staking_events
    GROUP BY staker
)
SELECT
    DATE_TRUNC('day', first_stake_time) AS day,
    COUNT(*) AS new_stakers,
    SUM(first_stake_amount) AS total_first_stake_vvv,
    AVG(first_stake_amount) AS avg_first_stake_size,
    SUM(COUNT(*)) OVER (ORDER BY DATE_TRUNC('day', first_stake_time)) AS cumulative_stakers,
    CASE
        WHEN DATE_TRUNC('day', first_stake_time) >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM first_stakes
GROUP BY 1
ORDER BY 1
```

---

## 12. DIEM Mint Acceleration Ratio

**Dune URL:** https://dune.com/queries/6953027

```sql
-- PANEL 10A: DIEM Mint Acceleration Ratio
-- Compares each day's minting vs trailing 7-day average
-- Visualization: bar chart with acceleration ratio line overlay
-- DIEM contract on Base: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
-- Thresholds: >2x = notable migration | >5x = migration wave

WITH daily_mints AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(amount) AS diem_minted,
        COUNT(DISTINCT "to") AS unique_minters
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND "from" = 0x0000000000000000000000000000000000000000
      AND block_time >= DATE '2026-03-01'
    GROUP BY 1
)
SELECT
    day,
    diem_minted,
    unique_minters,
    AVG(diem_minted) OVER (
        ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ) AS seven_day_avg_prior,
    diem_minted / NULLIF(
        AVG(diem_minted) OVER (
            ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ), 0
    ) AS mint_acceleration_ratio,
    CASE
        WHEN day >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM daily_mints
ORDER BY day
```

---

## 13. New DIEM Minter Wallets

**Dune URL:** https://dune.com/queries/6953217

```sql
-- PANEL 10B: New DIEM Minter Wallets (first-time minters)
-- Wallets minting DIEM for the first time = new compute consumers
-- Cross-reference with Panel 9 to see staker->minter conversion funnel
-- DIEM contract on Base: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024

WITH mint_events AS (
    SELECT
        "to" AS minter,
        block_time,
        amount AS diem_amount
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
```

---

