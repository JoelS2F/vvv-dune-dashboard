"""
VVV Signal Intelligence — Output builder & writer
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PANELS

log = logging.getLogger(__name__)

REMOTE_DIR = Path("F:/Projects/signal-command-center/signals")


def build_signal_state(
    composite: dict[str, Any],
    panel_scores: dict[str, float],
    weights: dict[str, float],
    backtest_results: dict[str, dict],
    all_signals: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """
    Build the full signal state JSON that the React dashboard consumes.
    """
    now = datetime.now(timezone.utc)

    # Per-panel detail
    panels_detail: list[dict] = []
    for panel_id, cfg in PANELS.items():
        bt = backtest_results.get(panel_id, {})
        score = panel_scores.get(panel_id, 50.0)
        weight = weights.get(panel_id, 0.0)

        # Latest signal
        signals = (all_signals or {}).get(panel_id, [])
        latest_signal = signals[-1] if signals else None

        panels_detail.append({
            "panel_id": panel_id,
            "name": cfg.name,
            "section": cfg.section,
            "signal_type": cfg.signal_type,
            "data_type": cfg.data_type,
            "score": score,
            "weight": round(weight, 4),
            "n_events": bt.get("n_events", 0),
            "validated": bt.get("validated", False),
            "best_p_value": bt.get("best_p_value"),
            "best_hit_rate": bt.get("best_hit_rate"),
            "best_window": bt.get("best_window"),
            "latest_signal": latest_signal,
        })

    # Section summaries
    sections: dict[str, dict] = {}
    for sec in ("A", "B", "C", "D"):
        sec_panels = [p for p in panels_detail if p["section"] == sec]
        sec_scores = [p["score"] for p in sec_panels if p["weight"] > 0]
        sec_weights = [p["weight"] for p in sec_panels if p["weight"] > 0]
        if sec_weights:
            total_w = sum(sec_weights)
            sec_composite = sum(s * w for s, w in zip(sec_scores, sec_weights)) / total_w
        else:
            sec_composite = 50.0
        sections[sec] = {
            "composite": round(sec_composite, 2),
            "n_panels": len(sec_panels),
            "n_active": sum(1 for p in sec_panels if p["weight"] > 0),
        }

    state = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "composite_score": composite.get("composite_score", 50.0),
        "regime": composite.get("regime", "NEUTRAL"),
        "sections": sections,
        "panels": panels_detail,
        "backtest_summary": {
            "total_panels": len(PANELS),
            "validated_panels": sum(1 for r in backtest_results.values() if r.get("validated")),
            "total_events": sum(r.get("n_events", 0) for r in backtest_results.values()),
        },
    }

    return state


def write_output(
    state: dict[str, Any],
    local_dir: str | Path,
    remote_dir: str | Path | None = None,
) -> list[Path]:
    """
    Write signal state JSON to local exports dir and optionally to
    the signal-command-center remote signals dir.
    Returns list of written file paths.
    """
    written: list[Path] = []

    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    # Timestamped filename
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"vvv_signal_state_{ts}.json"
    latest_name = "vvv_signal_state_latest.json"

    content = json.dumps(state, indent=2, default=str)

    # Write timestamped
    local_ts = local_dir / filename
    local_ts.write_text(content, encoding="utf-8")
    written.append(local_ts)
    log.info("Wrote %s", local_ts)

    # Write latest symlink/copy
    local_latest = local_dir / latest_name
    local_latest.write_text(content, encoding="utf-8")
    written.append(local_latest)
    log.info("Wrote %s", local_latest)

    # Remote copy
    if remote_dir is None:
        remote_dir = REMOTE_DIR

    remote_dir = Path(remote_dir)
    if remote_dir.is_dir():
        remote_file = remote_dir / latest_name
        remote_file.write_text(content, encoding="utf-8")
        written.append(remote_file)
        log.info("Wrote remote %s", remote_file)
    else:
        log.warning("Remote dir not found: %s — skipping remote write", remote_dir)

    return written


def write_backtest_report(
    backtest_results: dict[str, dict],
    output_dir: str | Path,
) -> Path:
    """
    Write detailed backtest results JSON for audit/debug.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"backtest_report_{ts}.json"
    path.write_text(
        json.dumps(backtest_results, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Wrote backtest report -> %s", path)

    # Also write latest
    latest = output_dir / "backtest_report_latest.json"
    latest.write_text(
        json.dumps(backtest_results, indent=2, default=str),
        encoding="utf-8",
    )

    return path
