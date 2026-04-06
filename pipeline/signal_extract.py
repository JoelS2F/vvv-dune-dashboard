"""
VVV Signal Intelligence — Signal extraction from raw Dune panel data
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    PanelConfig,
    PANELS,
    ROLLING_WINDOW_SHORT,
    ROLLING_WINDOW_LONG,
    ROLLING_WINDOW_MONTH,
    ZSCORE_THRESHOLD,
    BUY_SELL_BULLISH,
    BUY_SELL_BEARISH,
    BUY_SELL_CONSEC_DAYS,
    MINT_ACCEL_BULLISH,
    NUPL_BULLISH_CROSS,
    NUPL_BEARISH_CROSS,
)

log = logging.getLogger(__name__)

# ── SignalEvent type (plain dict) ──────────────────────────────────────────
# {date: str, panel_id: str, direction: "bullish"|"bearish"|"neutral",
#  strength: float 0-1, metadata: dict}


def _to_dataframe(rows: list[dict], date_col: str, metric_col: str) -> pd.DataFrame:
    """Convert raw Dune rows into a sorted DataFrame with parsed dates."""
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if date_col not in df.columns:
        log.warning("Date column '%s' not found in data. Columns: %s", date_col, list(df.columns))
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    df["date"] = df["date"].dt.tz_localize(None)
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    if metric_col in df.columns:
        df["metric"] = pd.to_numeric(df[metric_col], errors="coerce")
    else:
        log.warning("Metric column '%s' not found. Columns: %s", metric_col, list(df.columns))
        df["metric"] = np.nan

    return df


# ── Generic rolling z-score signal ────────────────────────────────────────

def _zscore_signals(
    df: pd.DataFrame,
    panel_id: str,
    window: int,
    threshold: float,
    direction: str = "bullish",
) -> list[dict]:
    """
    Fire a signal when metric exceeds mean + threshold * std over rolling window.
    """
    if df.empty or df["metric"].isna().all():
        return []

    roll_mean = df["metric"].rolling(window, min_periods=max(3, window // 2)).mean()
    roll_std = df["metric"].rolling(window, min_periods=max(3, window // 2)).std()

    events = []
    for i in range(window, len(df)):
        m, s = roll_mean.iloc[i], roll_std.iloc[i]
        if pd.isna(m) or pd.isna(s) or s == 0:
            continue
        z = (df["metric"].iloc[i] - m) / s
        if z > threshold:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": direction,
                "strength": min(z / (threshold * 2), 1.0),
                "metadata": {"z_score": round(z, 3), "value": float(df["metric"].iloc[i])},
            })
    return events


# ── Panel-specific extractors ─────────────────────────────────────────────

def _extract_panel_4(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_4_svvv_staking_flows: net_staking > mean + 1*std (7d rolling)."""
    return _zscore_signals(df, panel_id, ROLLING_WINDOW_SHORT, 1.0, "bullish")


def _extract_panel_7(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_7_dex_buy_sell_ratio: >1.5 for 2+ days bullish, <0.67 bearish."""
    if df.empty or df["metric"].isna().all():
        return []

    events = []
    consec_bull = 0
    consec_bear = 0

    for i in range(len(df)):
        val = df["metric"].iloc[i]
        if pd.isna(val):
            consec_bull = 0
            consec_bear = 0
            continue

        if val > BUY_SELL_BULLISH:
            consec_bull += 1
            consec_bear = 0
            if consec_bull >= BUY_SELL_CONSEC_DAYS:
                events.append({
                    "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                    "panel_id": panel_id,
                    "direction": "bullish",
                    "strength": min((val - 1.0) / 1.0, 1.0),
                    "metadata": {"buy_sell_ratio": round(val, 3), "consec_days": consec_bull},
                })
        elif val < BUY_SELL_BEARISH:
            consec_bear += 1
            consec_bull = 0
            if consec_bear >= BUY_SELL_CONSEC_DAYS:
                events.append({
                    "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                    "panel_id": panel_id,
                    "direction": "bearish",
                    "strength": min((1.0 - val) / 1.0, 1.0),
                    "metadata": {"buy_sell_ratio": round(val, 3), "consec_days": consec_bear},
                })
        else:
            consec_bull = 0
            consec_bear = 0

    return events


def _extract_panel_8(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_8_volume_vs_price: volume > 2*std above 14d mean."""
    return _zscore_signals(df, panel_id, ROLLING_WINDOW_LONG, ZSCORE_THRESHOLD, "bullish")


def _extract_panel_6(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_6_diem_minting: net_diem spike > 2*std above 30d mean."""
    return _zscore_signals(df, panel_id, ROLLING_WINDOW_MONTH, ZSCORE_THRESHOLD, "bullish")


def _extract_panel_10a(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_10a_diem_mint_acceleration: ratio > 2.0 -> bullish."""
    if df.empty or df["metric"].isna().all():
        return []

    events = []
    for i in range(len(df)):
        val = df["metric"].iloc[i]
        if pd.isna(val):
            continue
        if val > MINT_ACCEL_BULLISH:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": "bullish",
                "strength": min(val / (MINT_ACCEL_BULLISH * 2), 1.0),
                "metadata": {"mint_acceleration_ratio": round(val, 3)},
            })
    return events


def _extract_panel_1c(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_1c_sth_nupl_time_series: crossing above 0 bullish, below -0.1 bearish."""
    if df.empty or df["metric"].isna().all():
        return []

    events = []
    for i in range(1, len(df)):
        prev = df["metric"].iloc[i - 1]
        curr = df["metric"].iloc[i]
        if pd.isna(prev) or pd.isna(curr):
            continue

        # Bullish crossover: prev < 0, curr >= 0
        if prev < NUPL_BULLISH_CROSS and curr >= NUPL_BULLISH_CROSS:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": "bullish",
                "strength": min(curr / 0.5, 1.0) if curr > 0 else 0.5,
                "metadata": {"nupl_prev": round(prev, 4), "nupl_curr": round(curr, 4)},
            })
        # Bearish crossover: prev > -0.1, curr <= -0.1
        elif prev > NUPL_BEARISH_CROSS and curr <= NUPL_BEARISH_CROSS:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": "bearish",
                "strength": min(abs(curr) / 0.5, 1.0),
                "metadata": {"nupl_prev": round(prev, 4), "nupl_curr": round(curr, 4)},
            })
    return events


def _extract_panel_9a(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_9a_new_stakers_daily: new_stakers > 2*std above mean."""
    return _zscore_signals(df, panel_id, ROLLING_WINDOW_LONG, ZSCORE_THRESHOLD, "bullish")


def _extract_panel_2a(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_2a_cex_netflows_daily: large negative = bullish outflows."""
    if df.empty or df["metric"].isna().all():
        return []

    roll_mean = df["metric"].rolling(ROLLING_WINDOW_SHORT, min_periods=3).mean()
    roll_std = df["metric"].rolling(ROLLING_WINDOW_SHORT, min_periods=3).std()

    events = []
    for i in range(ROLLING_WINDOW_SHORT, len(df)):
        m, s = roll_mean.iloc[i], roll_std.iloc[i]
        val = df["metric"].iloc[i]
        if pd.isna(m) or pd.isna(s) or s == 0 or pd.isna(val):
            continue
        z = (val - m) / s
        # Negative net flow (outflows) = bullish
        if z < -ZSCORE_THRESHOLD:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": "bullish",
                "strength": min(abs(z) / (ZSCORE_THRESHOLD * 2), 1.0),
                "metadata": {"z_score": round(z, 3), "net_flow": float(val)},
            })
        # Positive net flow (inflows) = bearish
        elif z > ZSCORE_THRESHOLD:
            events.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "panel_id": panel_id,
                "direction": "bearish",
                "strength": min(z / (ZSCORE_THRESHOLD * 2), 1.0),
                "metadata": {"z_score": round(z, 3), "net_flow": float(val)},
            })
    return events


def _extract_panel_10b(df: pd.DataFrame, panel_id: str) -> list[dict]:
    """panel_10b_new_diem_minters: spike in new minters -> bullish."""
    return _zscore_signals(df, panel_id, ROLLING_WINDOW_LONG, ZSCORE_THRESHOLD, "bullish")


# ── Snapshot panel history tracking ───────────────────────────────────────

def _append_snapshot_history(
    panel_id: str,
    rows: list[dict],
    history_dir: Path,
) -> list[dict]:
    """
    Append current snapshot rows to a history JSONL file.
    Returns the full history as a list of dicts.
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"{panel_id}_history.jsonl"

    stamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(history_file, "a", encoding="utf-8") as f:
        for row in rows:
            entry = {"_fetched_at": stamp, **row}
            f.write(json.dumps(entry, default=str) + "\n")

    # Read back full history
    history = []
    if history_file.is_file():
        for line in history_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return history


def _extract_snapshot_state(
    panel_id: str,
    rows: list[dict],
    cfg: PanelConfig,
) -> list[dict]:
    """
    For snapshot panels, extract a single 'current state' signal event.
    """
    if not rows:
        return []

    # Determine direction based on panel-specific heuristics
    events = []
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    if panel_id == "panel_1b_sth_nupl_gauge":
        # Map regime_signal text to direction
        regime_map = {
            "euphoria": ("bullish", 1.0),
            "greed": ("bullish", 0.7),
            "neutral": ("neutral", 0.5),
            "fear": ("bearish", 0.7),
            "capitulation": ("bearish", 1.0),
        }
        for row in rows:
            regime = str(row.get("regime_signal", "")).lower().strip()
            direction, strength = regime_map.get(regime, ("neutral", 0.3))
            events.append({
                "date": date_str,
                "panel_id": panel_id,
                "direction": direction,
                "strength": strength,
                "metadata": {"regime_signal": regime, "raw_row": row},
            })
            break  # single gauge row

    elif panel_id == "panel_5_whale_wallet_monitor":
        # Map whale behavior
        for row in rows:
            behavior = str(row.get("behavior", "")).lower().strip()
            if "accumulat" in behavior:
                direction, strength = "bullish", 0.8
            elif "distribut" in behavior:
                direction, strength = "bearish", 0.8
            else:
                direction, strength = "neutral", 0.4
            events.append({
                "date": date_str,
                "panel_id": panel_id,
                "direction": direction,
                "strength": strength,
                "metadata": {"behavior": behavior, "wallet": row.get("wallet_address", "")},
            })

    elif panel_id in ("panel_3_holder_vintage_bands", "panel_9b_pre_post_ban_comparison",
                       "panel_10c_conversion_funnel", "panel_1a_sth_nupl_cost_basis"):
        # Generic snapshot: just record current state
        events.append({
            "date": date_str,
            "panel_id": panel_id,
            "direction": "neutral",
            "strength": 0.5,
            "metadata": {"row_count": len(rows), "sample": rows[0] if rows else {}},
        })

    return events


# ── Dispatcher ─────────────────────────────────────────────────────────────

_TIME_SERIES_EXTRACTORS: dict[str, Any] = {
    "panel_1c_sth_nupl_time_series": _extract_panel_1c,
    "panel_2a_cex_netflows_daily": _extract_panel_2a,
    "panel_4_svvv_staking_flows": _extract_panel_4,
    "panel_6_diem_minting": _extract_panel_6,
    "panel_7_dex_buy_sell_ratio": _extract_panel_7,
    "panel_8_volume_vs_price": _extract_panel_8,
    "panel_9a_new_stakers_daily": _extract_panel_9a,
    "panel_10a_diem_mint_acceleration": _extract_panel_10a,
    "panel_10b_new_diem_minters": _extract_panel_10b,
}

# Panels with time_series data_type but no specific extractor use generic z-score
_GENERIC_TS_PANELS = {
    "panel_2b_cex_netflows_cumulative",
}


def extract_signals(
    panel_config: PanelConfig,
    raw_data: list[dict],
    history_dir: Path | None = None,
) -> list[dict]:
    """
    Extract signal events from raw Dune data for a single panel.
    Returns list of SignalEvent dicts.
    """
    panel_id = panel_config.panel_id

    if not raw_data:
        log.warning("No data for %s — skipping signal extraction", panel_id)
        return []

    try:
        if panel_config.data_type == "time_series":
            df = _to_dataframe(raw_data, panel_config.date_column, panel_config.metric_column)
            if df.empty:
                log.warning("Empty DataFrame for %s after parsing", panel_id)
                return []

            if panel_id in _TIME_SERIES_EXTRACTORS:
                events = _TIME_SERIES_EXTRACTORS[panel_id](df, panel_id)
            elif panel_id in _GENERIC_TS_PANELS:
                events = _zscore_signals(
                    df, panel_id, ROLLING_WINDOW_LONG, ZSCORE_THRESHOLD, "bullish"
                )
            else:
                # Fallback generic z-score
                events = _zscore_signals(
                    df, panel_id, ROLLING_WINDOW_SHORT, 1.0,
                    panel_config.signal_direction,
                )

            log.info("Extracted %d signals from %s (time_series)", len(events), panel_id)
            return events

        else:  # snapshot
            if history_dir:
                _append_snapshot_history(panel_id, raw_data, history_dir)
            events = _extract_snapshot_state(panel_id, raw_data, panel_config)
            log.info("Extracted %d signals from %s (snapshot)", len(events), panel_id)
            return events

    except Exception as exc:
        log.error("Signal extraction failed for %s: %s", panel_id, exc, exc_info=True)
        return []


def extract_all_signals(
    export_dir: str | Path,
    history_dir: str | Path | None = None,
) -> dict[str, list[dict]]:
    """
    Extract signals from all panels.
    Returns dict of panel_id -> list of SignalEvent.
    """
    from .fetch_dune import load_panel_data

    export_dir = Path(export_dir)
    hist = Path(history_dir) if history_dir else export_dir / "history"

    all_signals: dict[str, list[dict]] = {}

    for panel_id, cfg in PANELS.items():
        raw = load_panel_data(panel_id, export_dir)
        events = extract_signals(cfg, raw, history_dir=hist)
        all_signals[panel_id] = events

    total = sum(len(v) for v in all_signals.values())
    log.info("Total signals extracted: %d across %d panels", total, len(all_signals))
    return all_signals
