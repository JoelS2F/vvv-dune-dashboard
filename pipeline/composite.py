"""
VVV Signal Intelligence — Composite score & regime classification
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .config import PANELS, PanelConfig, REGIME_THRESHOLDS

log = logging.getLogger(__name__)

# ── Weight computation ─────────────────────────────────────────────────────

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
    Compute panel weights from backtest results.
    Rules:
      - p < 0.05 -> base = 1.0
      - p < 0.10 -> base = 0.5
      - p >= 0.10 -> 0 (excluded)
      - insufficient data -> 0.3 (prior)
      - Multiply by signal_type multiplier (leading 2x, coincident 1x, lagging 0.5x)
      - Cap constraints: no single > 40%, no single < 5% (if included), lagging total <= 5%
    """
    raw_weights: dict[str, float] = {}

    for panel_id, result in backtest_results.items():
        cfg = PANELS.get(panel_id)
        if not cfg:
            continue

        n_events = result.get("n_events", 0)
        best_p = result.get("best_p_value")
        sufficient = result.get("sufficient_data", False)

        # Base weight from statistical significance
        if not sufficient or best_p is None:
            base = 0.3  # prior for insufficient data
        elif best_p < 0.05:
            base = 1.0
        elif best_p < 0.10:
            base = 0.5
        else:
            base = 0.0

        if base == 0:
            raw_weights[panel_id] = 0.0
            continue

        # Signal type multiplier
        multiplier = SIGNAL_TYPE_MULTIPLIER.get(cfg.signal_type, 1.0)
        raw_weights[panel_id] = base * multiplier

    # Normalize to sum = 1.0
    total_raw = sum(raw_weights.values())
    if total_raw == 0:
        log.warning("All panel weights are zero — returning uniform prior")
        active = [pid for pid in backtest_results if PANELS.get(pid)]
        if not active:
            return {}
        uniform = 1.0 / len(active)
        return {pid: uniform for pid in active}

    weights = {pid: w / total_raw for pid, w in raw_weights.items()}

    # Apply cap constraints
    weights = _apply_caps(weights)

    active = {pid: w for pid, w in weights.items() if w > 0}
    log.info("Computed weights for %d active panels (of %d total)", len(active), len(weights))
    return weights


def _apply_caps(weights: dict[str, float]) -> dict[str, float]:
    """Apply max/min single-panel and lagging-total caps, then re-normalize."""
    # Cap individual weights
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
            capped[pid] = 0.0  # exclude too-small weights
            excess += w
        else:
            capped[pid] = w
            non_capped_total += w

    # Redistribute excess proportionally to non-capped weights
    if excess > 0 and non_capped_total > 0:
        for pid in capped:
            if 0 < capped[pid] < MAX_SINGLE_WEIGHT:
                capped[pid] += excess * (capped[pid] / non_capped_total)
                capped[pid] = min(capped[pid], MAX_SINGLE_WEIGHT)

    # Cap lagging total
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
        # Redistribute lagging excess to non-lagging
        non_lagging = {
            pid: w for pid, w in capped.items()
            if w > 0 and PANELS.get(pid) and PANELS[pid].signal_type != "lagging"
        }
        nl_total = sum(non_lagging.values())
        if nl_total > 0:
            for pid in non_lagging:
                capped[pid] += lagging_excess * (non_lagging[pid] / nl_total)

    # Final normalization
    total = sum(capped.values())
    if total > 0:
        capped = {pid: w / total for pid, w in capped.items()}

    return capped


# ── Panel score computation ───────────────────────────────────────────────

def compute_panel_score(
    panel_config: PanelConfig,
    signals: list[dict],
) -> float:
    """
    Compute a 0-100 score for a single panel from its latest signals.
    50 = neutral, >50 = bullish, <50 = bearish.
    """
    if not signals:
        return 50.0  # neutral prior

    # Use the most recent signal
    latest = signals[-1]
    direction = latest.get("direction", "neutral")
    strength = latest.get("strength", 0.5)

    if direction == "bullish":
        score = 50 + strength * 50  # 50-100
    elif direction == "bearish":
        score = 50 - strength * 50  # 0-50
    else:
        score = 50.0

    return round(max(0.0, min(100.0, score)), 2)


# ── Composite score ───────────────────────────────────────────────────────

def compute_composite(
    panel_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """
    Weighted average of panel scores -> composite score 0-100.
    """
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


# ── Regime classification ─────────────────────────────────────────────────

def classify_regime(score: float) -> str:
    """
    Classify composite score into regime:
    >= 75: ACCUMULATE
    >= 60: HOLD
    >= 40: NEUTRAL
    >= 25: REDUCE
    <  25: HEDGE
    """
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


# ── Full composite pipeline ──────────────────────────────────────────────

def build_composite(
    all_signals: dict[str, list[dict]],
    backtest_results: dict[str, dict],
) -> dict[str, Any]:
    """
    Full composite pipeline: weights -> panel scores -> composite -> regime.
    Returns complete composite state dict.
    """
    weights = compute_weights(backtest_results)

    panel_scores: dict[str, float] = {}
    for panel_id, signals in all_signals.items():
        cfg = PANELS.get(panel_id)
        if cfg:
            panel_scores[panel_id] = compute_panel_score(cfg, signals)

    composite_score = compute_composite(panel_scores, weights)
    regime = classify_regime(composite_score)

    log.info("Composite: %.1f -> %s", composite_score, regime)

    return {
        "composite_score": composite_score,
        "regime": regime,
        "panel_scores": panel_scores,
        "weights": weights,
    }
