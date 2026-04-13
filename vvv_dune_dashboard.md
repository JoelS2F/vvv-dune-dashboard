# VVV On-Chain Intelligence Dashboard — Dune Queries

**Contract:** `0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf` (VVV on Base)
**Methodology:** ERC-20 adaptation of Glassnode STH-NUPL / STH-SOPR
**Dashboard Name:** S2F Capital — VVV On-Chain Intelligence

---

## Resolved Contract Addresses (Phase 1 complete)

| Token | Address | Source | Decimals |
|---|---|---|---|
| **VVV** | `0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf` | Confirmed | 18 |
| **sVVV** | `0x321b7ff75154472B18EDb199033fF4D116F340Ff` | BaseScan + Venice docs | 18 |
| **DIEM** | `0xf4d97f2da56e8c3098f3a8d538db630a2606a024` | Venice blog + BaseScan verified | 18 |

sVVV lookup methodology: Venice staking docs confirm `0x321b7ff7...` as the staked Venice token on Base, 25M+ supply, 7-day unstaking period. DIEM is an ERC-20 on Base (37,760 supply, 3,288 holders) minted by locking sVVV — BaseScan-verified source says "created by StakingV2 contract by staking sVVV."

---

## DuneSQL (Trino) Corrections Applied

| Issue from original PDF | Fix applied |
|---|---|
| `labels.addresses` used column `category` | Dune schema uses `label_type`. All refs updated. |
| Single CEX source (`labels.addresses`) | Added `cex.addresses` as primary + labels as fallback + manual Coinbase Base hot wallets CTE |
| Placeholder addresses in Panels 4, 6, 9A, 9B, 10A, 10B, 10C | All replaced with resolved sVVV/DIEM |
| Panel 9B ban timestamp | Fixed to `TIMESTAMP '2026-04-04 19:00:00' UTC` (not date-only) |

---

## Panel 1: New Entrant Cost Basis Distribution (STH-NUPL Core)

The foundational query. For every wallet that received VVV in the last 72 hours, compute their acquisition price at the block they received it, then calculate unrealized PnL vs current price.

### Panel 1A: New Entrant Acquisition Price & Unrealized PnL

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

### Panel 1B: Aggregate STH-NUPL Gauge (headline metric)

```sql
-- PANEL 1B: Aggregate STH-NUPL Gauge (single number + phase)
-- This is the headline metric for the dashboard
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

### Panel 1C: STH-NUPL Time Series (30-day history)

```sql
-- PANEL 1C: STH-NUPL Time Series (daily rolling 72hr window)
-- Track how new entrant sentiment evolves over time
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
      AND block_time >= CURRENT_DATE - INTERVAL '33' day
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

## Panel 2: CEX Netflow Tracker

Track VVV flowing to/from known exchange addresses. Replicates netflow analysis methodology.

**CEX address resolution strategy:** Dune's curated `cex.addresses` table is the primary source, supplemented by `labels.addresses` with `label_type = 'cex'` fallback and a manual list of known Coinbase Base hot wallets.

### Panel 2A: Daily CEX Netflows

```sql
-- PANEL 2A: Daily CEX Netflows
-- Negative netflow = tokens leaving exchanges (bullish accumulation signal)
-- Multi-source CEX identification: cex.addresses + labels.addresses + manual list

WITH cex_addresses AS (
    -- Primary: Dune's curated CEX table (most reliable for Base)
    SELECT DISTINCT address
    FROM cex.addresses
    WHERE blockchain = 'base'
    UNION
    -- Fallback: labels.addresses filtered to cex
    SELECT DISTINCT address
    FROM labels.addresses
    WHERE blockchain = 'base'
      AND label_type = 'cex'
    UNION
    -- Manual supplementation: known Coinbase Base hot wallets
    -- (Replace/extend as BaseScan coverage improves)
    SELECT address FROM (VALUES
        -- Coinbase institutional hot wallets on Base (verify on BaseScan)
        (0x20fe562d797a42dcb3399062ae9546cd06f63280),  -- Coinbase 10 (common)
        (0x71660c4005ba85c37ccec55d0c4493e66fe775d3)   -- Coinbase 6 (common)
    ) AS t(address)
),
inflows AS (
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

### Panel 2B: Cumulative CEX Netflow (90-day running total)

```sql
-- PANEL 2B: Cumulative CEX Netflow (running total)
-- Shows whether exchanges are accumulating or draining over time
-- Visualization: area chart — below zero = bullish
WITH cex_addresses AS (
    SELECT DISTINCT address FROM cex.addresses WHERE blockchain = 'base'
    UNION
    SELECT DISTINCT address FROM labels.addresses
    WHERE blockchain = 'base' AND label_type = 'cex'
    UNION
    SELECT address FROM (VALUES
        (0x20fe562d797a42dcb3399062ae9546cd06f63280),
        (0x71660c4005ba85c37ccec55d0c4493e66fe775d3)
    ) AS t(address)
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

## Panel 3: Holder Vintage Bands

What percentage of VVV supply is held by wallets of different ages? Shows whether the holder base is maturing or dominated by hot money.

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

## Panel 4: sVVV Staking Flow (Conviction Proxy)

Net staking vs unstaking activity. Rising staking = holders locking tokens for API inference access = structural demand removal from circulating supply.

**sVVV contract:** `0x321b7ff75154472B18EDb199033fF4D116F340Ff`

```sql
-- PANEL 4: sVVV Staking Flows
-- Track VVV transfers TO the staking contract (stakes) vs FROM (unstakes)
WITH staking_flows AS (
    SELECT
        DATE_TRUNC('day', block_time) AS day,
        SUM(CASE
            WHEN "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff THEN amount / 1e18
            ELSE 0
        END) AS tokens_staked,
        SUM(CASE
            WHEN "from" = 0x321b7ff75154472b18edb199033ff4d116f340ff THEN amount / 1e18
            ELSE 0
        END) AS tokens_unstaked,
        COUNT(DISTINCT CASE
            WHEN "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff THEN "from"
        END) AS unique_stakers,
        COUNT(DISTINCT CASE
            WHEN "from" = 0x321b7ff75154472b18edb199033ff4d116f340ff THEN "to"
        END) AS unique_unstakers
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND block_time >= NOW() - INTERVAL '90' day
      AND (
          "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff
          OR "from" = 0x321b7ff75154472b18edb199033ff4d116f340ff
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

## Panel 5: Whale Wallet Monitor

Top 20 non-exchange, non-contract wallets with balance changes over the last 7 days.

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
      AND balance / 1e18 > 1000   -- minimum 1K VVV to qualify as whale
),
recent_net_transfers AS (
    SELECT
        wallet,
        SUM(net_amount) AS seven_day_change
    FROM (
        SELECT "to" AS wallet, SUM(amount / 1e18) AS net_amount
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '7' day
        GROUP BY "to"
        UNION ALL
        SELECT "from" AS wallet, -SUM(amount / 1e18) AS net_amount
        FROM tokens.transfers
        WHERE blockchain = 'base'
          AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
          AND block_time >= NOW() - INTERVAL '7' day
        GROUP BY "from"
    ) sub
    GROUP BY wallet
),
cex_addresses AS (
    SELECT DISTINCT address FROM cex.addresses WHERE blockchain = 'base'
    UNION
    SELECT DISTINCT address FROM labels.addresses
    WHERE blockchain = 'base' AND label_type = 'cex'
)
SELECT
    cb.wallet,
    COALESCE(l.name, CAST(cb.wallet AS VARCHAR)) AS label,
    cb.current_balance,
    COALESCE(rnt.seven_day_change, 0) AS seven_day_change,
    COALESCE(rnt.seven_day_change, 0)
        / NULLIF(cb.current_balance - COALESCE(rnt.seven_day_change, 0), 0) AS pct_change_7d,
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
WHERE cex.address IS NULL                    -- exclude CEX wallets
  AND cb.wallet != 0x0000000000000000000000000000000000000000
  AND cb.wallet != 0x321b7ff75154472b18edb199033ff4d116f340ff  -- exclude sVVV staking contract
ORDER BY cb.current_balance DESC
LIMIT 30
```

---

## Panel 6: DIEM Minting Activity (Venice Ecosystem Health)

DIEM is minted by locking sVVV. Surging DIEM mints = protocols/agents ramping up API consumption through Venice.

**DIEM contract:** `0xf4d97f2da56e8c3098f3a8d538db630a2606a024`

```sql
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
```

---

## Panel 7: Buy/Sell Pressure Ratio (DEX Trade Direction)

Classifies DEX swaps as buys vs sells based on which side of the pair VVV is on.

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

## Panel 8: Transfer Volume vs Price (Divergence Detection)

When transfer volume spikes without price following (or vice versa), it signals distribution or stealth accumulation.

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

## Panel 9: OpenClaw Migration Tracker — New Staker Acceleration

The critical migration signal. First-time VVV stakers spiking after April 4, 2026 19:00 UTC (Anthropic's OpenClaw ban enforcement timestamp) = displaced agent operators locking in Venice compute. **This is the single most important panel for proving the migration thesis.**

### Panel 9A: Daily First-Time VVV Stakers

```sql
-- PANEL 9A: Daily First-Time VVV Stakers
-- A spike post-April 4 2026 = OpenClaw migration signal
-- Visualization: bar chart with April 4 vertical annotation line
WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time,
        amount / 1e18 AS vvv_staked
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff
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
    -- Day-level period classification (April 4 = ban day; straddle logic handled in 9B)
    CASE
        WHEN DATE_TRUNC('day', first_stake_time) >= DATE '2026-04-04' THEN 'POST_BAN'
        ELSE 'PRE_BAN'
    END AS period
FROM first_stakes
GROUP BY DATE_TRUNC('day', first_stake_time)
ORDER BY 1
```

### Panel 9B: Pre-Ban vs Post-Ban Staking Comparison

```sql
-- PANEL 9B: Pre-Ban vs Post-Ban Staking Comparison
-- Summary counter showing acceleration factor
-- Ban timestamp: April 4, 2026 19:00 UTC (12pm PT)
-- Visualization: two big numbers side by side
WITH staking_events AS (
    SELECT
        "from" AS staker,
        block_time
    FROM tokens.transfers
    WHERE blockchain = 'base'
      AND contract_address = 0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf
      AND "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff
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
    WHERE first_stake_time >= DATE '2026-03-04'     -- 30 days pre-ban window
)
SELECT
    period,
    COUNT(*) AS new_stakers,
    COUNT(*) * 1.0 / GREATEST(DATE_DIFF('day',
        MIN(first_stake_time),
        MAX(first_stake_time)
    ), 1) AS stakers_per_day,
    MIN(first_stake_time) AS period_start,
    MAX(first_stake_time) AS period_end
FROM periods
GROUP BY period
```

---

## Panel 10: DIEM Mint Acceleration (Compute Lockup Velocity)

DIEM minting is the strongest conversion signal — it means someone is locking sVVV specifically to secure perpetual API compute access. A mint acceleration ratio > 2x post-ban is notable, > 5x is a migration wave.

### Panel 10A: DIEM Mint Acceleration Ratio

```sql
-- PANEL 10A: DIEM Mint Acceleration Ratio
-- Compares each day's minting vs trailing 7-day average (excluding current day)
-- Visualization: bar chart with acceleration ratio line overlay
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

### Panel 10B: New DIEM Minter Wallets (first-time minters)

```sql
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
```

### Panel 10C: Venice API Proxy Signal — VVV→sVVV→DIEM Conversion Funnel

```sql
-- PANEL 10C: Venice API Proxy Signal — VVV→sVVV→DIEM Conversion Funnel
-- Tracks the full journey: acquire VVV → stake → mint DIEM → consume compute
-- All three CTEs use consistent post-ban filter: DATE '2026-04-04'
-- Visualization: funnel chart or stacked bar
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
      AND "to" = 0x321b7ff75154472b18edb199033ff4d116f340ff
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
SELECT 'VVV Buyers (DEX)' AS stage, unique_buyers AS count, 1 AS stage_order FROM vvv_buyers
UNION ALL
SELECT 'VVV Stakers' AS stage, unique_stakers AS count, 2 AS stage_order FROM vvv_stakers
UNION ALL
SELECT 'DIEM Minters' AS stage, unique_minters AS count, 3 AS stage_order FROM diem_minters
ORDER BY stage_order
```

---

## Dashboard Layout (Recommended Order)

**Section A: Market Sentiment (STH-NUPL)**
1. STH-NUPL Gauge (Panel 1B) — single counter, top of dashboard
2. STH-NUPL Time Series (Panel 1C) — line chart with phase bands
3. Cost Basis Distribution (Panel 1A) — histogram

**Section B: Flow Analysis**
4. CEX Netflows (Panel 2A + 2B) — bar chart + cumulative area
5. Buy/Sell Ratio (Panel 7) — bar chart with ratio overlay
6. Volume vs Price (Panel 8) — dual-axis

**Section C: Holder Structure**
7. Holder Vintage Bands (Panel 3) — stacked area
8. Whale Monitor (Panel 5) — table

**Section D: Venice Ecosystem / OpenClaw Migration**
9. New Staker Acceleration (Panel 9A) — bar chart with April 4 annotation
10. Pre vs Post Ban Comparison (Panel 9B) — counter cards
11. DIEM Mint Acceleration (Panel 10A) — bar + ratio line
12. New DIEM Minters (Panel 10B) — bar chart
13. Conversion Funnel (Panel 10C) — funnel chart
14. Staking Flows (Panel 4) — bar chart with cumulative line
15. DIEM Activity (Panel 6) — bar chart

---

## Key Thresholds (DO NOT MODIFY)

### STH-NUPL (validated in FAI analysis)

| Signal | Condition | Interpretation |
|---|---|---|
| **EUPHORIA** | 80%+ of 72hr wallets at >40% gain | Highest pullback probability |
| **GREED** | 60%+ at >25% gain | Correction pressure building |
| **FEAR** | 50%+ underwater | Weak hand selling pressure |
| **CAPITULATION** | 70%+ at >20% loss | Contrarian bottom signal |
| **CEX drain** | Cumulative netflow negative + accelerating | Bullish accumulation |
| **Staking surge** | Net staking > 2x 30-day avg | Structural demand signal |

### Migration-Specific Thresholds (OpenClaw → Venice)

| Signal | Condition | Interpretation |
|---|---|---|
| **Migration wave** | DIEM mint acceleration ratio > 5x post-April 4 | Strong agent migration evidence |
| **Migration notable** | DIEM mint acceleration ratio > 2x post-April 4 | Early migration signal |
| **New staker spike** | Daily first-time stakers > 3x pre-ban avg | Compute demand influx |
| **Funnel conversion** | >30% of post-ban VVV buyers also stake within 7 days | Usage-driven demand (not speculative) |
| **DIEM minter quality** | Avg DIEM per new minter > 1.0 | Serious compute consumers ($1+/day) |

### Key Date: April 4, 2026 19:00 UTC (12pm PT)

Anthropic OpenClaw ban enforcement timestamp. Panels 9A, 9B, 10A, 10B, 10C split data at this moment. Panels 9 and 10 should include a vertical annotation line at this date in the Dune viz config.

---

## Dune-Specific Tips

- Always include `blockchain = 'base'` and `block_time` filters first for query performance
- `prices.usd` may have gaps for VVV — use `prices.day` as fallback for daily granularity
- `labels.addresses` uses `label_type` column (not `category`) — Dune current schema
- `cex.addresses` is Dune's curated CEX-specific table (more reliable than labels.addresses for exchange identification)
- `balances.erc20_latest` is derived from cumulative transfers, may lag slightly
- `dex.trades` on Base covers Aerodrome, Uniswap V3, and other Base DEXs
- Address literals in DuneSQL: write as `0xabc...` (varbinary) — **do NOT quote as strings**
- `APPROX_PERCENTILE`, `FILTER (WHERE ...)`, `SEQUENCE() + UNNEST()` are all valid Trino syntax
- `DATE_DIFF('day', a, b)` returns the day difference in Trino
- Community canonical CEX address lists: [Dune query 3761086](https://dune.com/queries/3761086) ("CEX Wallet Addresses — Complete"), [3237025](https://dune.com/queries/3237025) (hildobby's EVM CEX list), [3311867](https://dune.com/queries/3311867) (All Known CEX)

---

## Research Context (the "why")

On **April 4, 2026 at 19:00 UTC (12pm PT)**, Anthropic blocked Claude Pro/Max subscriptions from powering OpenClaw and other third-party agent frameworks. OpenClaw had ~135K active instances, many running on subsidized $20/month Claude subscriptions that consumed $1,000-5,000/day in equivalent API costs. Venice AI is OpenClaw's officially recommended model provider (since March 2026). Venice's DIEM token provides $1/day of perpetual API compute credit per token — making it the only option where displaced agent operators can lock in fixed compute costs permanently rather than renting from another provider subject to future pricing changes. This dashboard exists to provide on-chain proof of whether that migration is actually happening.

**Thesis test:** If Panels 9A/10A show a sustained >2x acceleration in post-April-4 first-time stakers and DIEM mint velocity relative to the March 2026 baseline, the migration is real. If Panel 10C shows conversion rates >30% (buyers → stakers → minters), the demand is usage-driven rather than speculative.

---

## Section 5: Flywheel & Repricing (Panels 17-20)

Tracks the VVV deflationary flywheel: revenue buyback burns, DIEM implied yield, staking flow trends, and the composite burn-to-unstake health ratio.

| Panel | Name | Status | Query ID | Description |
|---|---|---|---|---|
| 17 | Burn Velocity | PENDING DEPLOYMENT | PENDING | Weekly burns with 4-week MA and WoW growth. Excludes >500K airdrop burn. |
| 18 | DIEM Implied Yield | PENDING DEPLOYMENT | PENDING | Daily DIEM price from Aerodrome, implied yield (365/price), discount vs $7,300 perpetuity. |
| 19 | sVVV Net Staking Flow | PENDING DEPLOYMENT | PENDING | Daily net staking with 7d/30d MAs, cumulative, trend classification. |
| 20 | Flywheel Health Ratio | PENDING DEPLOYMENT | PENDING | Weekly burn-to-unstake ratio. >1.0 tightening, <0.5 leaking. |

### Diagnostic Queries (pre-deployment verification)

| Diagnostic | Tests | Expected |
|---|---|---|
| diagnostic_17_burns.sql | VVV transfers to null address | ~3-4 monthly burns since Dec 2025 |
| diagnostic_18_diem_trades.sql | DIEM in dex.trades | DIEM/WETH or DIEM/USDC on Aerodrome |
| diagnostic_19_staking_flows.sql | VVV to/from sVVV contract | Daily stake/unstake activity |
