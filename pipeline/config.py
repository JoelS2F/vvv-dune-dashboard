"""
VVV Signal Intelligence — Panel Registry & Constants
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── API endpoints ──────────────────────────────────────────────────────────
DUNE_API_BASE = "https://api.dune.com/api/v1"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
VVV_COINGECKO_ID = "venice-token"
BTC_COINGECKO_ID = "bitcoin"

# ── Regime thresholds (composite score 0-100) ─────────────────────────────
REGIME_THRESHOLDS = {
    "ACCUMULATE": 68,
    "HOLD": 55,
    "NEUTRAL": 38,
    "REDUCE": 22,
    # below REDUCE → HEDGE
}

# ── Backtest constraints ──────────────────────────────────────────────────
MIN_SIGNAL_EVENTS = 20
TRAIN_FRACTION = 0.60          # 60 / 40 chronological split
FORWARD_WINDOWS = [1, 3, 5, 7] # days

# ── Score decay ──────────────────────────────────────────────────────────
DECAY_HALF_LIFE_DAYS = 14  # Score halves toward neutral every 14 days of staleness
STALE_THRESHOLD_DAYS = 3   # Flag panels older than this as stale in dashboard

# ── Corrected weights (cross-ref analysis 2026-04-06) ────────────────────
# Mint/burn Pearson r < 0.05 — no demonstrated price predictive power
# OI/funding r=0.385/0.366 — best forward predictors
CORRECTED_WEIGHTS: dict[str, float] = {
    # Tier 1: Demonstrated price correlation (0.45 → 0.3825 after ×0.85)
    "panel_11_derivatives":             0.1275,  # OI r=0.385, funding r=0.366
    "panel_4_svvv_staking_flows":       0.1020,  # Supply lock — whale confirmed
    "panel_2b_cex_netflows_cumulative": 0.0850,  # Exchange exodus
    "panel_2a_cex_netflows_daily":      0.0680,  # Daily flow direction
    # Tier 2: Structural signals (0.25 → 0.2125)
    "panel_5_whale_wallet_monitor":     0.0680,  # Smart money behavior
    "panel_1c_sth_nupl_time_series":    0.0595,  # STH sentiment
    "panel_1a_sth_nupl_cost_basis":     0.0425,  # Cost basis distribution
    "panel_1b_sth_nupl_gauge":          0.0425,  # Aggregate gauge
    # Tier 3: Low/no correlation — monitoring only (0.15 → 0.1275)
    "panel_3_holder_vintage_bands":     0.0255,  # Lagging
    "panel_8_volume_vs_price":          0.0255,  # Volume spikes
    "panel_6_diem_minting":             0.0170,  # REDUCED — r=0.003
    "panel_10a_diem_mint_acceleration": 0.0255,  # Acceleration > level
    "panel_10b_new_diem_minters":       0.0170,  # REDUCED
    "panel_9b_pre_post_ban_comparison": 0.0170,  # Lagging
    # Tier 4: Near-zero (0.05 → 0.0425)
    "panel_9a_new_stakers_daily":       0.0170,
    "panel_7_dex_buy_sell_ratio":       0.0170,
    "panel_10c_conversion_funnel":      0.0085,
    # Section F: Flywheel & Repricing (0.15 total — new)
    "panel_17_burn_velocity":           0.0525,  # 35% of section — burn momentum
    "panel_18_diem_implied_yield":      0.0375,  # 25% — yield compression
    "panel_19_staking_flow":            0.0375,  # 25% — net staking direction
    "panel_20_flywheel_ratio":          0.0225,  # 15% — composite health
}
# Wallet spike EXCLUDED — 0% win rate 3-10d, anti-predictive
# per cross-ref analysis 2026-04-06
# Sections A-E scaled ×0.85 to accommodate Section F at 15% (2026-04-12)

# ── Risk flag thresholds ─────────────────────────────────────────────────
RISK_STAKE_VOL_ZSCORE = -0.7   # Flag net unstaking below this z-score
RISK_WALLET_ZSCORE = -1.5      # Flag wallet activity collapse

# ── Signal extraction defaults ────────────────────────────────────────────
ROLLING_WINDOW_SHORT = 7
ROLLING_WINDOW_LONG = 14
ROLLING_WINDOW_MONTH = 30
ZSCORE_THRESHOLD = 2.0
BUY_SELL_BULLISH = 1.5
BUY_SELL_BEARISH = 0.67
BUY_SELL_CONSEC_DAYS = 2
MINT_ACCEL_BULLISH = 2.0
NUPL_BULLISH_CROSS = 0.0
NUPL_BEARISH_CROSS = -0.1


@dataclass(frozen=True)
class PanelConfig:
    panel_id: str
    query_id: int
    name: str
    section: Literal["A", "B", "C", "D", "E", "F"]
    signal_type: Literal["leading", "coincident", "lagging"]
    data_type: Literal["time_series", "snapshot"]
    signal_direction: Literal["bullish", "bearish", "directional"]
    signal_rule: str
    date_column: str
    metric_column: str


# ── Panel registry ─────────────────────────────────────────────────────────
PANELS: dict[str, PanelConfig] = {
    "panel_1a_sth_nupl_cost_basis": PanelConfig(
        panel_id="panel_1a_sth_nupl_cost_basis",
        query_id=6953031,
        name="STH-NUPL Cost Basis Distribution",
        section="A",
        signal_type="coincident",
        data_type="snapshot",
        signal_direction="directional",
        signal_rule="Distribution of short-term holder unrealized P/L across cost-basis cohorts",
        date_column="entry_time",
        metric_column="wallet_count",
    ),
    "panel_1b_sth_nupl_gauge": PanelConfig(
        panel_id="panel_1b_sth_nupl_gauge",
        query_id=6953009,
        name="STH-NUPL Aggregate Gauge",
        section="A",
        signal_type="coincident",
        data_type="snapshot",
        signal_direction="directional",
        signal_rule="Aggregate STH-NUPL regime signal: capitulation/fear/neutral/greed/euphoria",
        date_column="snapshot_date",
        metric_column="regime_signal",
    ),
    "panel_1c_sth_nupl_time_series": PanelConfig(
        panel_id="panel_1c_sth_nupl_time_series",
        query_id=6953035,
        name="STH-NUPL Time Series (30d)",
        section="A",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="mean_sth_nupl crossing above 0 -> bullish, below -0.1 -> bearish",
        date_column="snapshot_date",
        metric_column="mean_sth_nupl",
    ),
    "panel_2a_cex_netflows_daily": PanelConfig(
        panel_id="panel_2a_cex_netflows_daily",
        query_id=6953018,
        name="CEX Netflows (Daily)",
        section="A",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="Large net outflows (negative) -> bullish accumulation; net inflows -> bearish selling pressure",
        date_column="day",
        metric_column="net_flow_tokens",
    ),
    "panel_2b_cex_netflows_cumulative": PanelConfig(
        panel_id="panel_2b_cex_netflows_cumulative",
        query_id=6953223,
        name="CEX Netflows (Cumulative)",
        section="A",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="Cumulative net flow declining -> sustained accumulation; rising -> distribution",
        date_column="day",
        metric_column="cumulative_net_flow",
    ),
    "panel_3_holder_vintage_bands": PanelConfig(
        panel_id="panel_3_holder_vintage_bands",
        query_id=6953042,
        name="Holder Vintage Bands",
        section="B",
        signal_type="lagging",
        data_type="snapshot",
        signal_direction="bullish",
        signal_rule="Rising share of old-vintage holders (diamond hands) -> bullish long-term conviction",
        date_column="snapshot_date",
        metric_column="pct_of_supply",
    ),
    "panel_4_svvv_staking_flows": PanelConfig(
        panel_id="panel_4_svvv_staking_flows",
        query_id=6953185,
        name="sVVV Staking Flows",
        section="B",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="net_staking > mean + 1*std (7d rolling) -> bullish conviction signal",
        date_column="day",
        metric_column="net_staking",
    ),
    "panel_5_whale_wallet_monitor": PanelConfig(
        panel_id="panel_5_whale_wallet_monitor",
        query_id=6953189,
        name="Whale Wallet Monitor",
        section="B",
        signal_type="coincident",
        data_type="snapshot",
        signal_direction="directional",
        signal_rule="Whale accumulation behavior -> bullish; distribution -> bearish",
        date_column="snapshot_date",
        metric_column="behavior",
    ),
    "panel_6_diem_minting": PanelConfig(
        panel_id="panel_6_diem_minting",
        query_id=6953202,
        name="DIEM Minting Activity",
        section="C",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="net_diem spike > 2*std above 30d mean -> bullish demand signal",
        date_column="day",
        metric_column="net_diem",
    ),
    "panel_7_dex_buy_sell_ratio": PanelConfig(
        panel_id="panel_7_dex_buy_sell_ratio",
        query_id=6953047,
        name="DEX Buy/Sell Ratio",
        section="C",
        signal_type="coincident",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="buy_sell_ratio > 1.5 for 2+ consecutive days -> bullish; < 0.67 -> bearish",
        date_column="day",
        metric_column="buy_sell_ratio",
    ),
    "panel_8_volume_vs_price": PanelConfig(
        panel_id="panel_8_volume_vs_price",
        query_id=6953054,
        name="Transfer Volume vs Price",
        section="C",
        signal_type="coincident",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="volume > 2*std above 14d mean -> abnormal activity signal",
        date_column="day",
        metric_column="total_vvv_transferred",
    ),
    "panel_9a_new_stakers_daily": PanelConfig(
        panel_id="panel_9a_new_stakers_daily",
        query_id=6953024,
        name="First-Time Stakers Daily",
        section="D",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="new_stakers > 2*std above mean -> bullish adoption wave",
        date_column="day",
        metric_column="new_stakers",
    ),
    "panel_9b_pre_post_ban_comparison": PanelConfig(
        panel_id="panel_9b_pre_post_ban_comparison",
        query_id=6953215,
        name="Pre-Ban vs Post-Ban Stakers",
        section="D",
        signal_type="lagging",
        data_type="snapshot",
        signal_direction="bullish",
        signal_rule="Post-ban stakers_per_day exceeding pre-ban average -> bullish regime shift",
        date_column="snapshot_date",
        metric_column="stakers_per_day",
    ),
    "panel_10a_diem_mint_acceleration": PanelConfig(
        panel_id="panel_10a_diem_mint_acceleration",
        query_id=6953027,
        name="DIEM Mint Acceleration Ratio",
        section="D",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="mint_acceleration_ratio > 2.0 -> bullish acceleration signal",
        date_column="day",
        metric_column="mint_acceleration_ratio",
    ),
    "panel_10b_new_diem_minters": PanelConfig(
        panel_id="panel_10b_new_diem_minters",
        query_id=6953217,
        name="New DIEM Minter Wallets",
        section="D",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="Spike in new minter wallets -> growing ecosystem adoption",
        date_column="day",
        metric_column="new_minters",
    ),
    "panel_10c_conversion_funnel": PanelConfig(
        panel_id="panel_10c_conversion_funnel",
        query_id=6953221,
        name="Conversion Funnel (Post-Ban)",
        section="D",
        signal_type="lagging",
        data_type="snapshot",
        signal_direction="bullish",
        signal_rule="Funnel stage counts showing healthy conversion from holder -> staker -> minter",
        date_column="snapshot_date",
        metric_column="count",
    ),
    # ── Section F: Flywheel & Repricing (panels 17-20) ─────────────────────
    "panel_17_burn_velocity": PanelConfig(
        panel_id="panel_17_burn_velocity",
        query_id=6988823,
        name="Burn Velocity (Weekly)",
        section="F",
        signal_type="leading",
        data_type="time_series",
        signal_direction="bullish",
        signal_rule="Burn 4-week MA trending up + WoW growth >20% -> bullish supply reduction",
        date_column="week",
        metric_column="tokens_burned",
    ),
    "panel_18_diem_implied_yield": PanelConfig(
        panel_id="panel_18_diem_implied_yield",
        query_id=6988826,
        name="DIEM Implied Yield",
        section="F",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="Discount vs perpetuity <30% -> bullish repricing; >50% -> bearish deep discount",
        date_column="day",
        metric_column="implied_yield_pct",
    ),
    "panel_19_staking_flow": PanelConfig(
        panel_id="panel_19_staking_flow",
        query_id=6988829,
        name="sVVV Net Staking Flow (Enhanced)",
        section="F",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="7d MA positive 5+ days -> bullish accumulation; negative 5+ days -> bearish distribution",
        date_column="day",
        metric_column="net_flow",
    ),
    "panel_20_flywheel_ratio": PanelConfig(
        panel_id="panel_20_flywheel_ratio",
        query_id=6988831,
        name="Flywheel Health Ratio",
        section="F",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="Burn-to-unstake ratio >1.0 sustained -> tightening flywheel; <0.5 -> leaking",
        date_column="week",
        metric_column="flywheel_ratio",
    ),
    # ── Synthetic panels (not from Dune — fed from other data sources) ────
    "panel_11_derivatives": PanelConfig(
        panel_id="panel_11_derivatives",
        query_id=0,  # Synthetic — sourced from DIEM anomaly monitor
        name="Perpetual Derivatives (OI + Funding)",
        section="E",
        signal_type="leading",
        data_type="time_series",
        signal_direction="directional",
        signal_rule="OI z-score + funding z-score blended. r=0.385/0.366 to VVV 1d fwd return",
        date_column="timestamp",
        metric_column="oi_zscore",
    ),
}


def get_panels_by_section(section: str) -> list[PanelConfig]:
    """Return all panels in a given section letter."""
    return [p for p in PANELS.values() if p.section == section]


def get_time_series_panels() -> list[PanelConfig]:
    """Return only time-series panels (eligible for rolling signal extraction)."""
    return [p for p in PANELS.values() if p.data_type == "time_series"]


def get_snapshot_panels() -> list[PanelConfig]:
    """Return only snapshot panels."""
    return [p for p in PANELS.values() if p.data_type == "snapshot"]
