"""
VVV Signal Intelligence — Event-study backtester
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    PANELS,
    PanelConfig,
    FORWARD_WINDOWS,
    MIN_SIGNAL_EVENTS,
    TRAIN_FRACTION,
)

log = logging.getLogger(__name__)


# ── Stats without scipy ───────────────────────────────────────────────────

def _t_test_p_value(values: np.ndarray) -> tuple[float, float]:
    """
    One-sample t-test: H0 = mean == 0.
    Returns (t_statistic, p_value) using complementary error function.
    """
    n = len(values)
    if n < 2:
        return 0.0, 1.0
    mean = np.nanmean(values)
    std = np.nanstd(values, ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0, 1.0
    t = mean / (std / math.sqrt(n))
    # Two-tailed p-value via erfc approximation
    p = math.erfc(abs(t) / math.sqrt(2))
    return float(t), float(p)


def _compute_beta(
    vvv_returns: np.ndarray,
    btc_returns: np.ndarray,
) -> float:
    """Compute OLS beta: beta = cov(vvv, btc) / var(btc)."""
    mask = ~(np.isnan(vvv_returns) | np.isnan(btc_returns))
    vr = vvv_returns[mask]
    br = btc_returns[mask]
    if len(br) < 5:
        return 1.0  # fallback
    var_btc = np.var(br)
    if var_btc == 0:
        return 1.0
    cov_matrix = np.cov(vr, br)
    beta = cov_matrix[0, 1] / var_btc
    return float(beta)


# ── Merge signals with price data ─────────────────────────────────────────

def _merge_signals_prices(
    events: list[dict],
    vvv_df: pd.DataFrame,
    btc_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge signal events with VVV/BTC price data on date.
    Returns a DataFrame with signal info + forward returns.
    """
    if not events:
        return pd.DataFrame()

    sig_df = pd.DataFrame(events)
    sig_df["date"] = pd.to_datetime(sig_df["date"])

    # Merge VVV forward returns
    vvv_cols = ["date"] + [f"fwd_ret_{w}d" for w in FORWARD_WINDOWS if f"fwd_ret_{w}d" in vvv_df.columns]
    merged = sig_df.merge(
        vvv_df[vvv_cols],
        on="date",
        how="left",
        suffixes=("", "_vvv"),
    )

    # Merge BTC forward returns
    btc_rename = {f"fwd_ret_{w}d": f"btc_fwd_ret_{w}d" for w in FORWARD_WINDOWS}
    btc_cols = ["date"] + [f"fwd_ret_{w}d" for w in FORWARD_WINDOWS if f"fwd_ret_{w}d" in btc_df.columns]
    btc_sub = btc_df[btc_cols].rename(columns=btc_rename)
    merged = merged.merge(btc_sub, on="date", how="left")

    return merged.sort_values("date").reset_index(drop=True)


# ── Single panel event study ──────────────────────────────────────────────

def _event_study_single_window(
    merged: pd.DataFrame,
    window: int,
    split_idx: int,
) -> dict:
    """Run event study for one forward window, split into train/test."""
    vvv_col = f"fwd_ret_{window}d"
    btc_col = f"btc_fwd_ret_{window}d"

    if vvv_col not in merged.columns or btc_col not in merged.columns:
        return {}

    # Full sample
    valid = merged.dropna(subset=[vvv_col, btc_col])
    if valid.empty:
        return {}

    vvv_ret = valid[vvv_col].values
    btc_ret = valid[btc_col].values

    beta = _compute_beta(vvv_ret, btc_ret)
    alpha = vvv_ret - beta * btc_ret

    # Direction-adjust: bearish signals expect negative returns
    directions = valid["direction"].values
    adj_alpha = np.where(
        np.array([d == "bearish" for d in directions]),
        -alpha,
        alpha,
    )

    # Train/test split
    train_alpha = adj_alpha[:split_idx]
    test_alpha = adj_alpha[split_idx:]

    t_stat_train, p_train = _t_test_p_value(train_alpha)
    t_stat_test, p_test = _t_test_p_value(test_alpha)

    # Hit rate (positive alpha)
    hit_train = float(np.mean(train_alpha > 0)) if len(train_alpha) > 0 else 0.0
    hit_test = float(np.mean(test_alpha > 0)) if len(test_alpha) > 0 else 0.0

    return {
        f"T+{window}": {
            "beta": round(beta, 4),
            "n_total": len(valid),
            "n_train": len(train_alpha),
            "n_test": len(test_alpha),
            "train": {
                "avg_alpha": round(float(np.nanmean(train_alpha)), 6) if len(train_alpha) else None,
                "avg_raw_return": round(float(np.nanmean(vvv_ret[:split_idx])), 6) if split_idx > 0 else None,
                "hit_rate": round(hit_train, 4),
                "t_stat": round(t_stat_train, 3),
                "p_value": round(p_train, 4),
            },
            "test": {
                "avg_alpha": round(float(np.nanmean(test_alpha)), 6) if len(test_alpha) else None,
                "avg_raw_return": round(float(np.nanmean(vvv_ret[split_idx:])), 6) if len(test_alpha) else None,
                "hit_rate": round(hit_test, 4),
                "t_stat": round(t_stat_test, 3),
                "p_value": round(p_test, 4),
            },
        }
    }


def run_event_study(
    events: list[dict],
    vvv_prices: pd.DataFrame,
    btc_prices: pd.DataFrame,
    panel_config: PanelConfig | None = None,
) -> dict[str, Any]:
    """
    Run full event study for a panel's signal events.
    Returns BacktestResult dict with per-window statistics.
    """
    panel_id = events[0]["panel_id"] if events else "unknown"
    n_events = len(events)

    result: dict[str, Any] = {
        "panel_id": panel_id,
        "n_events": n_events,
        "sufficient_data": n_events >= MIN_SIGNAL_EVENTS,
        "windows": {},
        "validated": False,
    }

    if n_events < 3:
        log.warning("%s: only %d events — skipping backtest", panel_id, n_events)
        return result

    merged = _merge_signals_prices(events, vvv_prices, btc_prices)
    if merged.empty:
        log.warning("%s: no price-matched events", panel_id)
        return result

    split_idx = int(len(merged) * TRAIN_FRACTION)

    for w in FORWARD_WINDOWS:
        window_result = _event_study_single_window(merged, w, split_idx)
        result["windows"].update(window_result)

    # Validation: check T+5 test set p < 0.10
    t5 = result["windows"].get("T+5", {})
    test_data = t5.get("test", {})
    if test_data:
        p_val = test_data.get("p_value", 1.0)
        hit = test_data.get("hit_rate", 0.0)
        result["validated"] = (
            p_val is not None
            and p_val < 0.10
            and hit is not None
            and hit > 0.50
            and n_events >= MIN_SIGNAL_EVENTS
        )

    # Summary stats for composite weighting
    best_window = None
    best_p = 1.0
    for wname, wdata in result["windows"].items():
        test_p = wdata.get("test", {}).get("p_value", 1.0)
        if test_p is not None and test_p < best_p:
            best_p = test_p
            best_window = wname

    result["best_window"] = best_window
    result["best_p_value"] = round(best_p, 4) if best_p < 1.0 else None
    result["best_hit_rate"] = (
        result["windows"].get(best_window, {}).get("test", {}).get("hit_rate")
        if best_window else None
    )

    log.info(
        "%s: %d events, validated=%s, best_p=%s, best_hit=%s",
        panel_id, n_events, result["validated"],
        result["best_p_value"], result["best_hit_rate"],
    )
    return result


def run_all_backtests(
    all_signals: dict[str, list[dict]],
    vvv_prices: pd.DataFrame,
    btc_prices: pd.DataFrame,
) -> dict[str, dict]:
    """
    Run event studies for all panels.
    Returns dict of panel_id -> BacktestResult.
    """
    results: dict[str, dict] = {}

    for panel_id, events in all_signals.items():
        if not events:
            results[panel_id] = {
                "panel_id": panel_id,
                "n_events": 0,
                "sufficient_data": False,
                "windows": {},
                "validated": False,
            }
            continue

        cfg = PANELS.get(panel_id)
        try:
            results[panel_id] = run_event_study(events, vvv_prices, btc_prices, cfg)
        except Exception as exc:
            log.error("Backtest failed for %s: %s", panel_id, exc, exc_info=True)
            results[panel_id] = {
                "panel_id": panel_id,
                "n_events": len(events),
                "sufficient_data": False,
                "windows": {},
                "validated": False,
                "error": str(exc),
            }

    validated = sum(1 for r in results.values() if r.get("validated"))
    log.info(
        "Backtest complete: %d/%d panels validated",
        validated, len(results),
    )
    return results
