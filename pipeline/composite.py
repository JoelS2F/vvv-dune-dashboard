"""
VVV Signal Intelligence — Composite score & regime classification

v2.0 (2026-04-06): Signal overhaul per cross-reference analysis
  - Score decay for stale panels
  - Corrected weights (correlation-justified)
  - Derivatives panel (Panel 11) from DIEM anomaly monitor
  - Risk flag system for buried bearish signals
  - Wallet spike excluded (anti-predictive)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .config import (
    PANELS,
    PanelConfig,
    REGIME_THRESHOLDS,
    CORRECTED_WEIGHTS,
    DECAY_HALF_LIFE_DAYS,
    STALE_THRESHOLD_DAYS,
    RISK_STAKE_VOL_ZSCORE,
    RISK_WALLET_ZSCORE,
)

log = logging.getLogger(__name__)

# ── Weight computation (legacy — kept for A/B comparison) ────────────────

SIGNAL_TYPE_MULTIPLIER = {
    "leading": 2.0,
    "coincident": 1.0,
    "lagging": 0.5,
}

MAX_SINGLE_WEIGHT = 0.40
MIN_SINGLE_WEIGHT = 0.05
MAX_LAGGING_TOTAL = 0.05


def compute_weights(
    backtest_results: dict[str, dict],
) -> dict[str, float]:
    """
    Legacy weight computation from backtest p-values.
    Kept for A/B comparison — not used in corrected composite.
    """
    raw_weights: dict[str, float] = {}

    for panel_id, result in backtest_results.items():
        cfg = PANELS.get(panel_id)
        if not cfg:
            continue

        n_events = result.get("n_events", 0)
        best_p = result.get("best_p_value")
        sufficient = result.get("sufficient_data", False)

        if not sufficient or best_p is None:
            base = 0.3
        elif best_p < 0.05:
            base = 1.0
        elif best_p < 0.10:
            base = 0.5
        else:
            base = 0.0

        if base == 0:
            raw_weights[panel_id] = 0.0
            continue

        multiplier = SIGNAL_TYPE_MULTIPLIER.get(cfg.signal_type, 1.0)
        raw_weights[panel_id] = base * multiplier

    total_raw = sum(raw_weights.values())
    if total_raw == 0:
        log.warning("All panel weights are zero — returning uniform prior")
        active = [pid for pid in backtest_results if PANELS.get(pid)]
        if not active:
            return {}
        uniform = 1.0 / len(active)
        return {pid: uniform for pid in active}

    weights = {pid: w / total_raw for pid, w in raw_weights.items()}
    weights = _apply_caps(weights)

    active = {pid: w for pid, w in weights.items() if w > 0}
    log.info("Legacy weights: %d active panels (of %d total)", len(active), len(weights))
    return weights


def _apply_caps(weights: dict[str, float]) -> dict[str, float]:
    """Apply max/min single-panel and lagging-total caps, then re-normalize."""
    capped = {}
    excess = 0.0
    non_capped_total = 0.0

    for pid, w in weights.items():
        if w <= 0:
            capped[pid] = 0.0
            continue
        if w > MAX_SINGLE_WEIGHT:
            excess += w - MAX_SINGLE_WEIGHT
            capped[pid] = MAX_SINGLE_WEIGHT
        elif w < MIN_SINGLE_WEIGHT:
            capped[pid] = 0.0
            excess += w
        else:
            capped[pid] = w
            non_capped_total += w

    if excess > 0 and non_capped_total > 0:
        for pid in capped:
            if 0 < capped[pid] < MAX_SINGLE_WEIGHT:
                capped[pid] += excess * (capped[pid] / non_capped_total)
                capped[pid] = min(capped[pid], MAX_SINGLE_WEIGHT)

    lagging_total = sum(
        capped.get(pid, 0)
        for pid, cfg in PANELS.items()
        if cfg.signal_type == "lagging" and capped.get(pid, 0) > 0
    )
    if lagging_total > MAX_LAGGING_TOTAL:
        scale = MAX_LAGGING_TOTAL / lagging_total
        lagging_excess = 0.0
        for pid, cfg in PANELS.items():
            if cfg.signal_type == "lagging" and capped.get(pid, 0) > 0:
                old = capped[pid]
                capped[pid] = old * scale
                lagging_excess += old - capped[pid]
        non_lagging = {
            pid: w for pid, w in capped.items()
            if w > 0 and PANELS.get(pid) and PANELS[pid].signal_type != "lagging"
        }
        nl_total = sum(non_lagging.values())
        if nl_total > 0:
            for pid in non_lagging:
                capped[pid] += lagging_excess * (non_lagging[pid] / nl_total)

    total = sum(capped.values())
    if total > 0:
        capped = {pid: w / total for pid, w in capped.items()}

    return capped


# ── Score decay ──────────────────────────────────────────────────────────

def apply_score_decay(
    raw_score: float,
    data_age_days: float,
    half_life: float = DECAY_HALF_LIFE_DAYS,
) -> float:
    """
    Decay panel score toward neutral (50) based on data age.
    Linear decay: score reaches neutral at 2x half_life.
    """
    if data_age_days <= 1:
        return raw_score
    decay_factor = max(0.0, 1.0 - (data_age_days / (half_life * 2)))
    return round(50 + (raw_score - 50) * decay_factor, 2)


def compute_data_age(latest_signal: dict | None) -> float:
    """Compute age in days from latest signal date to now."""
    if not latest_signal:
        return 999.0  # Very stale — no signal ever
    sig_date = latest_signal.get("date", "")
    if not sig_date:
        return 999.0
    try:
        if "T" in sig_date:
            dt = datetime.fromisoformat(sig_date.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(sig_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        return max(0.0, age)
    except (ValueError, TypeError):
        return 999.0


# ── Derivatives scoring (Panel 11) ──────────────────────────────────────

def score_derivatives(oi_zscore: float, funding_zscore: float) -> float:
    """
    Score from OI + funding rate z-scores (DIEM anomaly monitor data).
    OI change r=0.385 and funding rate r=0.366 to VVV 1d forward return.

    Bullish: Rising OI + positive funding (longs paying, trend following)
    Bearish: Falling OI + negative funding (longs liquidating)
    Caution: Rising OI + very high funding (crowded long, reversal risk)
    """
    oi_score = max(0, min(100, 50 + oi_zscore * 20))
    funding_score = max(0, min(100, 50 + funding_zscore * 15))

    # Blend: OI weighted higher based on correlation strength
    blended = oi_score * 0.55 + funding_score * 0.45

    # Crowded long detection
    if oi_score > 75 and funding_score > 75:
        blended *= 0.85  # 15% haircut for crowding risk

    return round(min(100, max(0, blended)), 2)


def extract_derivatives_from_diem(diem_data: dict | None) -> dict:
    """
    Extract OI and funding z-scores from DIEM anomaly monitor data.
    Returns panel-like dict with score, direction, strength, metadata.
    """
    if not diem_data:
        return {"score": 50.0, "direction": "neutral", "strength": 0.5, "metadata": {}}

    z_scores = diem_data.get("z_scores", {})
    oi_z = z_scores.get("open_interest", {}).get("z_score", 0.0)
    funding_z = z_scores.get("funding_rate", {}).get("z_score", 0.0)
    perp_vol_z = z_scores.get("perp_volume", {}).get("z_score", 0.0)

    score = score_derivatives(oi_z, funding_z)

    # Determine direction and strength
    if score > 60:
        direction = "bullish"
        strength = min(1.0, (score - 50) / 50)
    elif score < 40:
        direction = "bearish"
        strength = min(1.0, (50 - score) / 50)
    else:
        direction = "neutral"
        strength = 0.5

    return {
        "score": score,
        "direction": direction,
        "strength": strength,
        "metadata": {
            "oi_zscore": oi_z,
            "funding_zscore": funding_z,
            "perp_vol_zscore": perp_vol_z,
            "oi_value": z_scores.get("open_interest", {}).get("value", 0),
            "funding_value": z_scores.get("funding_rate", {}).get("value", 0),
        },
    }


# ── Flywheel & Repricing scoring (Panels 17-20) ───────────────────────

def score_burn_velocity(data: list[dict]) -> dict:
    """Score Panel 17: Burn Velocity from weekly burn data."""
    if not data:
        return {"score": 50.0, "direction": "neutral", "strength": 0.5, "metadata": {}}

    latest = data[0] if data else {}  # Most recent week (DESC order)
    burn_4w_ma = latest.get("burn_4w_ma", 0)
    wow_growth = latest.get("wow_growth_rate", 0)
    tokens_burned = latest.get("tokens_burned", 0)

    # Score on WoW growth + burn MA trend
    if wow_growth > 0.20:
        score = min(100, 80 + (wow_growth - 0.20) * 50)
    elif wow_growth > 0:
        score = 50 + wow_growth * 150  # 0-30 pts above neutral
    elif wow_growth > -0.20:
        score = 50 + wow_growth * 100  # 30-50
    else:
        score = max(0, 30 + (wow_growth + 0.20) * 50)

    direction = "bullish" if score > 60 else "bearish" if score < 40 else "neutral"
    strength = abs(score - 50) / 50

    return {
        "score": round(max(0, min(100, score)), 2),
        "direction": direction,
        "strength": round(min(1.0, strength), 3),
        "metadata": {
            "burn_weekly_vvv": tokens_burned,
            "burn_4wk_ma": burn_4w_ma,
            "burn_wow_growth_pct": round(wow_growth * 100, 1) if wow_growth else 0,
        },
    }


def score_diem_implied_yield(data: list[dict]) -> dict:
    """Score Panel 18: DIEM Implied Yield from daily trade data."""
    if not data:
        return {"score": 50.0, "direction": "neutral", "strength": 0.5, "metadata": {}}

    latest = data[0] if data else {}
    median_price = latest.get("median_price", 0)
    implied_yield = latest.get("implied_yield_pct", 0)
    discount = latest.get("discount_vs_perpetuity", 0.5)
    yield_change_30d = latest.get("yield_change_30d", 0)

    # Score on discount vs perpetuity — lower discount = more bullish
    if discount < 0.30:
        score = min(100, 80 + (0.30 - discount) * 100)
    elif discount < 0.50:
        score = 50 + (0.50 - discount) * 150  # 50-80 range
    elif discount < 0.70:
        score = 50 - (discount - 0.50) * 100  # 30-50 range
    else:
        score = max(0, 30 - (discount - 0.70) * 100)

    direction = "bullish" if score > 60 else "bearish" if score < 40 else "neutral"
    strength = abs(score - 50) / 50

    return {
        "score": round(max(0, min(100, score)), 2),
        "direction": direction,
        "strength": round(min(1.0, strength), 3),
        "metadata": {
            "diem_price_usd": round(median_price, 2) if median_price else 0,
            "diem_implied_yield_pct": round(implied_yield, 2) if implied_yield else 0,
            "diem_discount_vs_5pct": round(discount, 4) if discount else 0,
            "diem_yield_30d_change_pct": round(yield_change_30d, 2) if yield_change_30d else 0,
        },
    }


def score_staking_flow(data: list[dict]) -> dict:
    """Score Panel 19: sVVV Net Staking Flow from daily data."""
    if not data:
        return {"score": 50.0, "direction": "neutral", "strength": 0.5, "metadata": {}}

    latest = data[0] if data else {}
    net_7d_ma = latest.get("net_flow_7d_ma", 0)
    trend = latest.get("trend", "NEUTRAL")

    # Count consecutive positive/negative 7d MA days
    positive_days = 0
    for row in data[:7]:
        if (row.get("net_flow_7d_ma") or 0) > 0:
            positive_days += 1

    if positive_days >= 5:
        score = min(100, 75 + (positive_days - 5) * 12.5)
    elif positive_days >= 3:
        score = 50 + (positive_days - 3) * 12.5
    elif positive_days <= 2:
        negative_days = 7 - positive_days
        if negative_days >= 5:
            score = max(0, 25 - (negative_days - 5) * 12.5)
        else:
            score = 50 - (negative_days - 2) * 10

    direction = "bullish" if score > 60 else "bearish" if score < 40 else "neutral"
    strength = abs(score - 50) / 50

    return {
        "score": round(max(0, min(100, score)), 2),
        "direction": direction,
        "strength": round(min(1.0, strength), 3),
        "metadata": {
            "staking_net_7d_ma": round(net_7d_ma, 2) if net_7d_ma else 0,
            "staking_trend": trend,
        },
    }


def score_flywheel_ratio(data: list[dict]) -> dict:
    """Score Panel 20: Flywheel Health Ratio from weekly data."""
    if not data:
        return {"score": 50.0, "direction": "neutral", "strength": 0.5, "metadata": {}}

    latest = data[0] if data else {}
    ratio = latest.get("flywheel_ratio", 0)
    status = latest.get("flywheel_status", "LEAKING")
    ratio_4w_ma = latest.get("ratio_4w_ma", 0)

    # Score on ratio level
    if ratio >= 1.0:
        score = min(100, 85 + (ratio - 1.0) * 15)
    elif ratio >= 0.5:
        score = 50 + (ratio - 0.5) * 70  # 50-85 range
    elif ratio >= 0.1:
        score = 20 + (ratio - 0.1) * 75  # 20-50 range
    else:
        score = max(0, ratio * 200)  # 0-20 range

    direction = "bullish" if score > 60 else "bearish" if score < 40 else "neutral"
    strength = abs(score - 50) / 50

    return {
        "score": round(max(0, min(100, score)), 2),
        "direction": direction,
        "strength": round(min(1.0, strength), 3),
        "metadata": {
            "flywheel_ratio": round(ratio, 4) if ratio else 0,
            "flywheel_status": status,
            "flywheel_ratio_4w_ma": round(ratio_4w_ma, 4) if ratio_4w_ma else 0,
        },
    }


def extract_flywheel_data(all_raw_data: dict) -> dict:
    """
    Extract flywheel panel data from raw Dune exports and score all 4 panels.
    Returns dict with per-panel scores + combined flywheel_repricing object.
    """
    p17 = score_burn_velocity(all_raw_data.get("panel_17_burn_velocity", []))
    p18 = score_diem_implied_yield(all_raw_data.get("panel_18_diem_implied_yield", []))
    p19 = score_staking_flow(all_raw_data.get("panel_19_staking_flow", []))
    p20 = score_flywheel_ratio(all_raw_data.get("panel_20_flywheel_ratio", []))

    # Section composite (weighted per plan)
    section_score = (
        p17["score"] * 0.35 +
        p18["score"] * 0.25 +
        p19["score"] * 0.25 +
        p20["score"] * 0.15
    )

    return {
        "panels": {
            "panel_17_burn_velocity": p17,
            "panel_18_diem_implied_yield": p18,
            "panel_19_staking_flow": p19,
            "panel_20_flywheel_ratio": p20,
        },
        "flywheel_repricing": {
            **p17["metadata"],
            **p18["metadata"],
            **p19["metadata"],
            **p20["metadata"],
            "section_score": round(section_score, 2),
        },
    }


# ── Risk flags ──────────────────────────────────────────────────────────

def compute_risk_flags(diem_data: dict | None) -> list[dict]:
    """
    Surface buried bearish signals as independent risk flags.
    These are signals too important to be averaged away in a composite.
    """
    flags: list[dict] = []
    if not diem_data:
        return flags

    # Stake Volume hemorrhage (from organic_demand)
    organic = diem_data.get("organic_demand", {})
    components = organic.get("components", {})
    stake_vol = components.get("stake_volume", {})

    sv_z = stake_vol.get("z_score", 0)
    if sv_z < RISK_STAKE_VOL_ZSCORE:
        flags.append({
            "id": "stake_volume_hemorrhage",
            "severity": "HIGH",
            "metric": "Stake Volume Z-Score",
            "value": sv_z,
            "percentile": stake_vol.get("percentile"),
            "raw_value": stake_vol.get("raw"),
            "description": f"Net unstaking of {stake_vol.get('raw', 0):,.0f} VVV — supply unlocking",
            "action": "Dampens ACCUMULATE conviction — size at half-signal",
            "source": "diem_anomaly_monitor",
        })

    # Wallet activity collapse
    wallet_z = diem_data.get("z_scores", {}).get("unique_wallets_daily", {})
    wz = wallet_z.get("z_score", 0)
    if wz < RISK_WALLET_ZSCORE:
        flags.append({
            "id": "wallet_activity_collapse",
            "severity": "MEDIUM",
            "metric": "Unique Wallets Z-Score",
            "value": wz,
            "percentile": None,
            "raw_value": wallet_z.get("value"),
            "description": f"Daily wallets at {wallet_z.get('value', 0)} vs 30d mean {wallet_z.get('rolling_mean', 0):.0f}",
            "action": "Monitor — activity collapse may precede price weakness",
            "source": "diem_anomaly_monitor",
        })

    return flags


# ── Panel score computation ──────────────────────────────────────────────

def compute_panel_score(
    panel_config: PanelConfig,
    signals: list[dict],
) -> float:
    """
    Compute a 0-100 score for a single panel from its latest signals.
    50 = neutral, >50 = bullish, <50 = bearish.
    """
    if not signals:
        return 50.0

    latest = signals[-1]
    direction = latest.get("direction", "neutral")
    strength = latest.get("strength", 0.5)

    if direction == "bullish":
        score = 50 + strength * 50
    elif direction == "bearish":
        score = 50 - strength * 50
    else:
        score = 50.0

    return round(max(0.0, min(100.0, score)), 2)


# ── Composite score ──────────────────────────────────────────────────────

def compute_composite(
    panel_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Weighted average of panel scores -> composite score 0-100."""
    total_weight = 0.0
    weighted_sum = 0.0

    for pid, score in panel_scores.items():
        w = weights.get(pid, 0.0)
        if w > 0:
            weighted_sum += score * w
            total_weight += w

    if total_weight == 0:
        return 50.0

    composite = weighted_sum / total_weight
    return round(max(0.0, min(100.0, composite)), 2)


# ── Regime classification ────────────────────────────────────────────────

def classify_regime(score: float) -> str:
    """Classify composite score into regime."""
    if score >= REGIME_THRESHOLDS["ACCUMULATE"]:
        return "ACCUMULATE"
    elif score >= REGIME_THRESHOLDS["HOLD"]:
        return "HOLD"
    elif score >= REGIME_THRESHOLDS["NEUTRAL"]:
        return "NEUTRAL"
    elif score >= REGIME_THRESHOLDS["REDUCE"]:
        return "REDUCE"
    else:
        return "HEDGE"


# ── Full composite pipeline ─────────────────────────────────────────────

def build_composite(
    all_signals: dict[str, list[dict]],
    backtest_results: dict[str, dict],
    diem_data: dict | None = None,
    flywheel_raw_data: dict | None = None,
    use_corrected_weights: bool = True,
) -> dict[str, Any]:
    """
    Full composite pipeline: weights -> panel scores -> decay -> composite -> regime.

    v2.0: Supports corrected weights, score decay, derivatives panel, and risk flags.
    """
    # --- Weights ---
    if use_corrected_weights:
        weights = dict(CORRECTED_WEIGHTS)
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in weights.items()}
        log.info("Using corrected weights (%d panels)", len(weights))
    else:
        weights = compute_weights(backtest_results)
        log.info("Using legacy backtest-derived weights")

    # Also compute legacy weights for comparison
    legacy_weights = compute_weights(backtest_results)

    # --- Raw panel scores ---
    panel_scores: dict[str, float] = {}
    panel_details: dict[str, dict] = {}

    for panel_id, signals in all_signals.items():
        cfg = PANELS.get(panel_id)
        if cfg:
            raw_score = compute_panel_score(cfg, signals)
            latest = signals[-1] if signals else None
            data_age = compute_data_age(latest)
            decayed_score = apply_score_decay(raw_score, data_age)

            panel_scores[panel_id] = decayed_score  # Use decayed for composite
            panel_details[panel_id] = {
                "raw_score": raw_score,
                "decayed_score": decayed_score,
                "data_age_days": round(data_age, 1),
                "is_stale": data_age > STALE_THRESHOLD_DAYS,
            }

    # --- Derivatives panel (Panel 11) ---
    deriv_info = extract_derivatives_from_diem(diem_data)
    panel_scores["panel_11_derivatives"] = deriv_info["score"]
    panel_details["panel_11_derivatives"] = {
        "raw_score": deriv_info["score"],
        "decayed_score": deriv_info["score"],  # Live data, no decay
        "data_age_days": 0.0,
        "is_stale": False,
        "metadata": deriv_info["metadata"],
    }

    # --- Flywheel & Repricing panels (17-20) ---
    flywheel_info = extract_flywheel_data(flywheel_raw_data or {})
    for pid, pdata in flywheel_info["panels"].items():
        panel_scores[pid] = pdata["score"]
        panel_details[pid] = {
            "raw_score": pdata["score"],
            "decayed_score": pdata["score"],  # Fresh Dune data, no decay
            "data_age_days": 0.0,
            "is_stale": False,
            "metadata": pdata["metadata"],
        }

    # --- Risk flags ---
    risk_flags = compute_risk_flags(diem_data)

    # --- Composite (corrected) ---
    corrected_composite = compute_composite(panel_scores, weights)
    corrected_regime = classify_regime(corrected_composite)

    # --- Raw composite (legacy weights, no decay) ---
    raw_panel_scores = {pid: d["raw_score"] for pid, d in panel_details.items()}
    raw_composite = compute_composite(raw_panel_scores, legacy_weights)

    log.info(
        "Composite: %.1f (corrected) vs %.1f (raw) -> %s",
        corrected_composite, raw_composite, corrected_regime,
    )

    # --- Stale panels list ---
    stale_panels = [
        pid for pid, d in panel_details.items()
        if d["is_stale"] and d["data_age_days"] < 900
    ]
    if stale_panels:
        log.warning("Stale panels (%d): %s", len(stale_panels), ", ".join(stale_panels))

    return {
        "composite_score": corrected_composite,
        "raw_composite": raw_composite,
        "regime": corrected_regime,
        "panel_scores": panel_scores,
        "panel_details": panel_details,
        "weights": weights,
        "legacy_weights": legacy_weights,
        "risk_flags": risk_flags,
        "derivatives_panel": deriv_info,
        "flywheel_repricing": flywheel_info.get("flywheel_repricing", {}),
        "stale_panels": stale_panels,
        "signal_quality": {
            "pct_correlation_justified": sum(
                w for pid, w in weights.items()
                if pid in (
                    "panel_11_derivatives", "panel_4_svvv_staking_flows",
                    "panel_2b_cex_netflows_cumulative", "panel_2a_cex_netflows_daily",
                )
            ),
            "excluded_panels": ["wallet_spike"],
            "stale_panels": stale_panels,
        },
    }
