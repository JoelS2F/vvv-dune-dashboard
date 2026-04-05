# VVV On-Chain Intelligence + OpenClaw Migration Dashboard

A Dune Analytics dashboard for the VVV (Venice AI) token on Base chain. Combines a classical STH-NUPL / STH-SOPR market sentiment framework with specific panels designed to detect and quantify on-chain evidence of OpenClaw → Venice migration following Anthropic's April 4, 2026 ban of Claude subscriptions powering third-party agent frameworks.

## Contents

| File | Purpose |
|---|---|
| `vvv_dune_dashboard.md` | 10 panels, 17 SQL queries. Drop into Dune one query at a time. |
| `queries/` | Individual `.sql` files — one per panel for easier iteration |
| `docs/` | Research + handoff docs |

## Resolved Contract Addresses

| Token | Address on Base | Decimals |
|---|---|---|
| VVV | `0xacFE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf` | 18 |
| sVVV | `0x321b7ff75154472B18EDb199033fF4D116F340Ff` | 18 |
| DIEM | `0xf4d97f2da56e8c3098f3a8d538db630a2606a024` | 18 |

## Panels

**Section A — Market Sentiment (STH-NUPL)**
1. Panel 1A — Cost basis distribution (per-wallet PnL)
2. Panel 1B — Aggregate NUPL gauge + regime classification (headline metric)
3. Panel 1C — 30-day NUPL time series

**Section B — Flow Analysis**
4. Panel 2A — Daily CEX netflows
5. Panel 2B — 90-day cumulative netflow
6. Panel 7 — DEX buy/sell pressure ratio
7. Panel 8 — Transfer volume vs price divergence

**Section C — Holder Structure**
8. Panel 3 — Holder vintage bands (cohort analysis)
9. Panel 5 — Whale wallet monitor (7-day balance delta)

**Section D — Venice Ecosystem / OpenClaw Migration**
10. Panel 4 — sVVV staking flows
11. Panel 6 — DIEM mint/burn activity
12. Panel 9A — Daily first-time VVV stakers (with April 4 annotation)
13. Panel 9B — Pre-ban vs post-ban staker comparison
14. Panel 10A — DIEM mint acceleration ratio (headline migration metric)
15. Panel 10B — New DIEM minter wallets
16. Panel 10C — Full conversion funnel (buyers → stakers → minters)

## Ban Timestamp

**April 4, 2026 at 19:00 UTC (12pm PT)** — Anthropic OpenClaw enforcement. All migration panels split data at this moment.

## Threshold Reference

### STH-NUPL phases
- EUPHORIA: 80%+ of 72h wallets at >40% gain
- GREED: 60%+ at >25% gain
- FEAR: 50%+ underwater
- CAPITULATION: 70%+ at >20% loss

### Migration signals
- Migration wave: DIEM mint acceleration > 5x
- Migration notable: acceleration > 2x
- New staker spike: first-time stakers > 3x pre-ban avg
- Funnel conversion: >30% of post-ban VVV buyers also stake within 7 days
- Minter quality: avg DIEM per new minter > 1.0 ($1/day)

## Dune Setup

1. Create a new dashboard on Dune Analytics named **"S2F Capital — VVV On-Chain Intelligence"**
2. For each panel in `vvv_dune_dashboard.md`, paste the SQL into a new DuneSQL query
3. Title each query with its panel number + description (e.g., "VVV Panel 1B — STH-NUPL Gauge")
4. Suggested refresh intervals:
   - STH-NUPL panels (1A/1B/1C): 30 min
   - CEX flows (2A/2B), DEX trades (7, 8): 5 min
   - Holder structure (3, 5): hourly
   - Migration panels (9, 10): hourly
5. Add a **vertical annotation line at April 4, 2026 19:00 UTC** on Panels 9A, 10A, 10B
6. Organize panels per the layout section in the main MD

## Known Limitations

- `prices.usd` may have gaps for VVV on Base — fall back to `prices.day` for daily granularity if needed
- `cex.addresses` and `labels.addresses` coverage on Base may be thin. The CEX-related panels (2A, 2B, 5) include a manual supplementation CTE with known Coinbase Base hot wallets. **Cross-check BaseScan's "Exchange" labels on VVV holder pages and extend this list as you identify new addresses.**
- `balances.erc20_latest` is derived from cumulative transfers and may lag
- `dex.trades` on Base covers Aerodrome + Uniswap V3 — other small DEXs may be missing

## License / Attribution

- Based on Glassnode's STH-NUPL / STH-SOPR methodology (ERC-20 adaptation)
- Migration thesis framework developed for S2F Capital
