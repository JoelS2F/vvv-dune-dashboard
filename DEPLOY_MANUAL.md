# VVV Dune Dashboard - Manual Deployment Guide
**Instructions:** For each block below:
1. Open https://dune.com/queries/new in a new tab
2. Paste the **Title** into the query title field (top of page)
3. Paste the **SQL** into the editor
4. Click **Save** (or Ctrl+S) — Dune will assign a query ID and update the URL
5. Optionally click **Run** to execute and warm the cache
6. Record the query ID in the checklist below

---

## Checklist

- [ ]  1. [S2F] VVV - STH-NUPL Cost Basis Distribution — Dune ID: `__________`
- [ ]  2. [S2F] VVV - STH-NUPL Aggregate Gauge — Dune ID: `__________`
- [ ]  3. [S2F] VVV - STH-NUPL Time Series (30d) — Dune ID: `__________`
- [ ]  4. [S2F] VVV - CEX Netflows (Daily) — Dune ID: `__________`
- [ ]  5. [S2F] VVV - CEX Netflows (Cumulative) — Dune ID: `__________`
- [ ]  6. [S2F] VVV - Holder Vintage Bands — Dune ID: `__________`
- [ ]  7. [S2F] VVV - sVVV Staking Flows — Dune ID: `__________`
- [ ]  8. [S2F] VVV - Whale Wallet Monitor — Dune ID: `__________`
- [ ]  9. [S2F] VVV - DIEM Minting Activity — Dune ID: `__________`
- [ ] 10. [S2F] VVV - DEX Buy/Sell Ratio — Dune ID: `__________`
- [ ] 11. [S2F] VVV - Transfer Volume vs Price — Dune ID: `__________`
- [ ] 12. [S2F] VVV - First-Time Stakers Daily — Dune ID: `__________`
- [ ] 13. [S2F] VVV - Pre-Ban vs Post-Ban Stakers — Dune ID: `__________`
- [ ] 14. [S2F] VVV - DIEM Mint Acceleration Ratio — Dune ID: `__________`
- [ ] 15. [S2F] VVV - New DIEM Minter Wallets — Dune ID: `__________`
- [ ] 16. [S2F] VVV - Conversion Funnel (Post-Ban) — Dune ID: `__________`

---

## 1. [S2F] VVV - STH-NUPL Cost Basis Distribution

**File:** `queries/panel_1a_sth_nupl_cost_basis.sql`  
**Description:** Panel 1A: Per-wallet unrealized PnL for 72hr new entrants. Sentiment phases: EUPHORIA/GREED/HOPE/FEAR/CAPITULATION.

**Title (copy this):**
```
[S2F] VVV - STH-NUPL Cost Basis Distribution
```

**SQL (copy this):**
```sql
-- PANEL 1A: New Entrant Acquisition Price & Unrealized PnL
-- Reconstructs Glassnode STH cost basis for ERC-20 on Base
-- Thresholds: EUPHORIA >40% gain for 80%+ wallets | CAPITULATION >20% loss for 70%+ wallets

WITH vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        block_number,
        amount / 1e18 AS vvv_amount,
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

## 2. [S2F] VVV - STH-NUPL Aggregate Gauge

**File:** `queries/panel_1b_sth_nupl_gauge.sql`  
**Description:** Panel 1B: Headline single-number STH-NUPL gauge with regime classification (EUPHORIA/GREED/FEAR/CAPITULATION/NEUTRAL).

**Title (copy this):**
```
[S2F] VVV - STH-NUPL Aggregate Gauge
```

**SQL (copy this):**
```sql
-- PANEL 1B: Aggregate STH-NUPL Gauge (single number + phase)
-- Headline metric for the dashboard

WITH vvv_transfers AS (
    SELECT
        "to" AS wallet,
        block_time,
        amount / 1e18 AS vvv_amount
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

## 3. [S2F] VVV - STH-NUPL Time Series (30d)

**File:** `queries/panel_1c_sth_nupl_time_series.sql`  
**Description:** Panel 1C: Daily rolling 72hr STH-NUPL over 30 days. Line chart with colored phase bands.

**Title (copy this):**
```
[S2F] VVV - STH-NUPL Time Series (30d)
```

**SQL (copy this):**
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
        amount / 1e18 AS vvv_amount
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

## 4. [S2F] VVV - CEX Netflows (Daily)

**File:** `queries/panel_2a_cex_netflows_daily.sql`  
**Description:** Panel 2A: Daily VVV inflow/outflow to labeled CEX wallets. Negative net = bullish accumulation.

**Title (copy this):**
```
[S2F] VVV - CEX Netflows (Daily)
```

**SQL (copy this):**
```sql
-- PANEL 2A: Daily CEX Netflows
-- Negative netflow = tokens leaving exchanges (bullish accumulation signal)
-- Uses Dune's labels.addresses for CEX identification
-- TODO: supplement cex_addresses CTE with hardcoded Coinbase Base hot wallets

WITH cex_addresses AS (
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
),
inflows AS (
    -- Tokens going TO exchanges (potential sell pressure)
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(t.amount / 1e18) AS tokens_in,
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
        SUM(t.amount / 1e18) AS tokens_out,
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

## 5. [S2F] VVV - CEX Netflows (Cumulative)

**File:** `queries/panel_2b_cex_netflows_cumulative.sql`  
**Description:** Panel 2B: 90-day running total of CEX net flow. Below zero = exchanges draining.

**Title (copy this):**
```
[S2F] VVV - CEX Netflows (Cumulative)
```

**SQL (copy this):**
```sql
-- PANEL 2B: Cumulative CEX Netflow (running total)
-- Shows whether exchanges are accumulating or draining over time
-- Visualization: area chart - below zero = bullish

WITH cex_addresses AS (
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
),
daily_flows AS (
    SELECT
        DATE_TRUNC('day', t.block_time) AS day,
        SUM(CASE WHEN cex_to.address IS NOT NULL THEN t.amount / 1e18 ELSE 0 END) AS inflow,
        SUM(CASE WHEN cex_from.address IS NOT NULL THEN t.amount / 1e18 ELSE 0 END) AS outflow
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

## 6. [S2F] VVV - Holder Vintage Bands

**File:** `queries/panel_3_holder_vintage_bands.sql`  
**Description:** Panel 3: Current holders classified by first-receive age (<24h, 1-7d, 7-30d, 30-90d, 90d+). Stacked area.

**Title (copy this):**
```
[S2F] VVV - Holder Vintage Bands
```

**SQL (copy this):**
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
    SELECT
        address AS wallet,
        balance / 1e18 AS vvv_balance
    FROM balances.erc20_latest
    WHERE blockchain = 'base'
      AND token_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND balance > 0
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

## 7. [S2F] VVV - sVVV Staking Flows

**File:** `queries/panel_4_svvv_staking_flows.sql`  
**Description:** Panel 4: Daily stake/unstake volume into sVVV contract. Conviction proxy + structural supply removal.

**Title (copy this):**
```
[S2F] VVV - sVVV Staking Flows
```

**SQL (copy this):**
```sql
-- PANEL 4: sVVV Staking Flows
-- Track VVV transfers TO the staking contract (stakes) vs FROM (unstakes)
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_flows AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount / 1e18
            ELSE 0
        END) AS tokens_staked,
        SUM(CASE
            WHEN "from" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff THEN amount / 1e18
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

## 8. [S2F] VVV - Whale Wallet Monitor

**File:** `queries/panel_5_whale_wallet_monitor.sql`  
**Description:** Panel 5: Top 30 non-CEX wallets (>1K VVV) with 7-day delta. ACCUMULATING/DISTRIBUTING/FLAT.

**Title (copy this):**
```
[S2F] VVV - Whale Wallet Monitor
```

**SQL (copy this):**
```sql
-- PANEL 5: Top Holder Balance Changes (7-day delta)
-- Identifies accumulation or distribution by large wallets

WITH current_balances AS (
    SELECT
        address AS wallet,
        balance / 1e18 AS current_balance
    FROM balances.erc20_latest
    WHERE blockchain = 'base'
      AND token_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND balance / 1e18 > 1000  -- minimum 1K VVV to qualify as whale
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
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
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

## 9. [S2F] VVV - DIEM Minting Activity

**File:** `queries/panel_6_diem_minting.sql`  
**Description:** Panel 6: Daily DIEM mints (from 0x0) and burns (to 0x0). Venice ecosystem health signal.

**Title (copy this):**
```
[S2F] VVV - DIEM Minting Activity
```

**SQL (copy this):**
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
```

---

## 10. [S2F] VVV - DEX Buy/Sell Ratio

**File:** `queries/panel_7_dex_buy_sell_ratio.sql`  
**Description:** Panel 7: 30-day DEX trade direction (Aerodrome + Uniswap V3 on Base). Buy/sell ratio + volumes.

**Title (copy this):**
```
[S2F] VVV - DEX Buy/Sell Ratio
```

**SQL (copy this):**
```sql
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
```

---

## 11. [S2F] VVV - Transfer Volume vs Price

**File:** `queries/panel_8_volume_vs_price.sql`  
**Description:** Panel 8: 90-day transfer volume, active addresses, and VVV price. Divergence detection.

**Title (copy this):**
```
[S2F] VVV - Transfer Volume vs Price
```

**SQL (copy this):**
```sql
-- PANEL 8: Transfer Volume vs Price Overlay
-- Visualization: dual-axis chart (volume bars + price line)

SELECT
    DATE_TRUNC('day', t.block_time) AS day,
    COUNT(*) AS num_transfers,
    COUNT(DISTINCT t."from") + COUNT(DISTINCT t."to") AS active_addresses,
    SUM(t.amount / 1e18) AS total_vvv_transferred,
    SUM(t.amount / 1e18) * p.avg_price AS volume_usd,
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

## 12. [S2F] VVV - First-Time Stakers Daily

**File:** `queries/panel_9a_new_stakers_daily.sql`  
**Description:** Panel 9A: Daily first-time VVV stakers since March 2026. Post-April 4 spike = OpenClaw migration.

**Title (copy this):**
```
[S2F] VVV - First-Time Stakers Daily
```

**SQL (copy this):**
```sql
-- PANEL 9A: Daily First-Time VVV Stakers
-- A spike post-April 4 2026 = OpenClaw migration signal
-- Visualization: bar chart with April 4 vertical annotation line
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time,
        amount / 1e18 AS vvv_staked
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

## 13. [S2F] VVV - Pre-Ban vs Post-Ban Stakers

**File:** `queries/panel_9b_pre_post_ban_comparison.sql`  
**Description:** Panel 9B: Staker acceleration factor across April 4 2026 19:00 UTC ban moment.

**Title (copy this):**
```
[S2F] VVV - Pre-Ban vs Post-Ban Stakers
```

**SQL (copy this):**
```sql
-- PANEL 9B: Pre-Ban vs Post-Ban Staking Comparison
-- Summary counter showing acceleration factor
-- Visualization: two big numbers side by side
-- Ban timestamp: April 4, 2026 19:00 UTC (12pm PT)
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= DATE '2026-03-01'
),
first_stakes AS (
    SELECT staker, MIN(block_time) AS first_stake_time
    FROM staking_events
    GROUP BY staker
),
periods AS (
    SELECT
        CASE
            WHEN first_stake_time >= TIMESTAMP '2026-04-04 19:00:00'
                THEN 'POST_BAN'
            ELSE 'PRE_BAN'
        END AS period,
        staker,
        first_stake_time
    FROM first_stakes
    WHERE first_stake_time >= DATE '2026-03-04'  -- 30 days pre-ban window
)
SELECT
    period,
    COUNT(*) AS new_stakers,
    COUNT(*) * 1.0 / NULLIF(DATE_DIFF('day',
        MIN(first_stake_time),
        MAX(first_stake_time)
    ), 0) AS stakers_per_day,
    MIN(first_stake_time) AS period_start,
    MAX(first_stake_time) AS period_end
FROM periods
GROUP BY period
```

---

## 14. [S2F] VVV - DIEM Mint Acceleration Ratio

**File:** `queries/panel_10a_diem_mint_acceleration.sql`  
**Description:** Panel 10A: Daily DIEM mint volume / trailing 7-day avg. >2x = notable, >5x = migration wave.

**Title (copy this):**
```
[S2F] VVV - DIEM Mint Acceleration Ratio
```

**SQL (copy this):**
```sql
-- PANEL 10A: DIEM Mint Acceleration Ratio
-- Compares each day's minting vs trailing 7-day average
-- Visualization: bar chart with acceleration ratio line overlay
-- DIEM contract on Base: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
-- Thresholds: >2x = notable migration | >5x = migration wave

WITH daily_mints AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(amount / 1e18) AS diem_minted,
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

## 15. [S2F] VVV - New DIEM Minter Wallets

**File:** `queries/panel_10b_new_diem_minters.sql`  
**Description:** Panel 10B: First-time DIEM minters per day = new Venice compute consumers.

**Title (copy this):**
```
[S2F] VVV - New DIEM Minter Wallets
```

**SQL (copy this):**
```sql
-- PANEL 10B: New DIEM Minter Wallets (first-time minters)
-- Wallets minting DIEM for the first time = new compute consumers
-- Cross-reference with Panel 9 to see staker->minter conversion funnel
-- DIEM contract on Base: 0xf4d97f2da56e8c3098f3a8d538db630a2606a024

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
```

---

## 16. [S2F] VVV - Conversion Funnel (Post-Ban)

**File:** `queries/panel_10c_conversion_funnel.sql`  
**Description:** Panel 10C: VVV buyers -> stakers -> DIEM minters funnel from April 4, 2026.

**Title (copy this):**
```
[S2F] VVV - Conversion Funnel (Post-Ban)
```

**SQL (copy this):**
```sql
-- PANEL 10C: Venice API Proxy Signal - VVV -> sVVV -> DIEM Conversion Funnel
-- Tracks the full journey: acquire VVV -> stake -> mint DIEM -> consume compute
-- Visualization: funnel chart or stacked bar
-- Post-ban window: all filters use DATE '2026-04-04' consistently
-- sVVV staking contract: 0x321b7ff75154472B18EDb199033fF4D116F340Ff

WITH vvv_buyers AS (
    SELECT COUNT(DISTINCT taker) AS unique_buyers
    FROM dex.trades
    WHERE blockchain = 'base'
      AND token_bought_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= DATE '2026-04-04'
),
vvv_stakers AS (
    SELECT COUNT(DISTINCT "from") AS unique_stakers
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472B18EDb199033fF4D116F340Ff
      AND block_time >= DATE '2026-04-04'
),
diem_minters AS (
    SELECT COUNT(DISTINCT "to") AS unique_minters
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xf4d97f2da56e8c3098f3a8d538db630a2606a024
      AND "from" = 0x0000000000000000000000000000000000000000
      AND block_time >= DATE '2026-04-04'
)
SELECT
    'VVV Buyers (DEX)' AS stage, unique_buyers AS count FROM vvv_buyers
UNION ALL
SELECT
    'VVV Stakers' AS stage, unique_stakers AS count FROM vvv_stakers
UNION ALL
SELECT
    'DIEM Minters' AS stage, unique_minters AS count FROM diem_minters
```

---

