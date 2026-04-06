"""
VVV Signal Intelligence — Price data fetcher (CoinGecko + CSV fallback)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import COINGECKO_BASE, VVV_COINGECKO_ID, BTC_COINGECKO_ID, FORWARD_WINDOWS

log = logging.getLogger(__name__)

COINGECKO_RATE_DELAY = 4  # seconds between calls


# ── CoinGecko fetch ───────────────────────────────────────────────────────

def fetch_coingecko_history(
    coin_id: str,
    days: int = 90,
    vs_currency: str = "usd",
) -> pd.DataFrame:
    """
    Fetch daily price + volume from CoinGecko /coins/{id}/market_chart.
    Returns DataFrame with columns: date, price, volume.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": vs_currency,
        "days": days,
        "interval": "daily",
    }
    log.info("Fetching CoinGecko history: %s (days=%d)", coin_id, days)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    records = []
    vol_map = {int(v[0]): v[1] for v in volumes}
    for ts_ms, price in prices:
        ts_ms_int = int(ts_ms)
        records.append({
            "date": pd.Timestamp(ts_ms_int, unit="ms", tz="UTC").normalize(),
            "price": price,
            "volume": vol_map.get(ts_ms_int, 0.0),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    log.info("  -> %d daily records for %s", len(df), coin_id)
    return df


def fetch_and_save_prices(
    data_dir: str | Path,
    days: int = 90,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch VVV + BTC prices from CoinGecko, save CSVs, return both DataFrames.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    vvv_df = fetch_coingecko_history(VVV_COINGECKO_ID, days=days)
    vvv_path = data_dir / "vvv_prices.csv"
    vvv_df.to_csv(vvv_path, index=False)
    log.info("Saved VVV prices -> %s", vvv_path)

    time.sleep(COINGECKO_RATE_DELAY)

    btc_df = fetch_coingecko_history(BTC_COINGECKO_ID, days=days)
    btc_path = data_dir / "btc_prices.csv"
    btc_df.to_csv(btc_path, index=False)
    log.info("Saved BTC prices -> %s", btc_path)

    return vvv_df, btc_df


# ── Load from CSV ─────────────────────────────────────────────────────────

def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _add_forward_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Add forward return columns: fwd_ret_1d, fwd_ret_3d, etc."""
    df = df.copy()
    for w in FORWARD_WINDOWS:
        col = f"fwd_ret_{w}d"
        df[col] = df["price"].pct_change(periods=w).shift(-w)
    return df


def load_price_data(data_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load VVV and BTC price CSVs, compute forward returns.
    Returns (vvv_df, btc_df) with fwd_ret_Xd columns.
    """
    data_dir = Path(data_dir)

    vvv_path = data_dir / "vvv_prices.csv"
    btc_path = data_dir / "btc_prices.csv"

    if not vvv_path.is_file() or not btc_path.is_file():
        raise FileNotFoundError(
            f"Price CSVs not found in {data_dir}. Run fetch stage first."
        )

    vvv_df = _add_forward_returns(_load_csv(vvv_path))
    btc_df = _add_forward_returns(_load_csv(btc_path))

    log.info(
        "Loaded prices: VVV %d rows (%s to %s), BTC %d rows",
        len(vvv_df),
        vvv_df["date"].min().date() if len(vvv_df) else "?",
        vvv_df["date"].max().date() if len(vvv_df) else "?",
        len(btc_df),
    )
    return vvv_df, btc_df
