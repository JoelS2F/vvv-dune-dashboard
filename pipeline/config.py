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
    section: Literal["A", "B", "C", "D"]
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
