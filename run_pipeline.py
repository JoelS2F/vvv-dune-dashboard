#!/usr/bin/env python3
"""
VVV Signal Intelligence — Pipeline Orchestrator

Usage:
    python run_pipeline.py --stage all
    python run_pipeline.py --stage fetch --no-cache
    python run_pipeline.py --stage backtest --verbose
    python run_pipeline.py --stage composite --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root = directory containing this script
PROJECT_ROOT = Path(__file__).resolve().parent
EXPORTS_DIR = PROJECT_ROOT / "exports"
DATA_DIR = PROJECT_ROOT / "data"
HISTORY_DIR = EXPORTS_DIR / "history"


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def check_prerequisites() -> bool:
    """Verify environment before running."""
    ok = True

    # Check DUNE_API_KEY reachability
    try:
        from pipeline.fetch_dune import _load_api_key
        key = _load_api_key()
        if not key:
            raise ValueError("empty key")
        logging.getLogger(__name__).info("DUNE_API_KEY: ...%s", key[-6:])
    except Exception as exc:
        logging.getLogger(__name__).error("DUNE_API_KEY not available: %s", exc)
        ok = False

    # Check imports
    for mod_name in ["pandas", "numpy", "requests"]:
        try:
            __import__(mod_name)
        except ImportError:
            logging.getLogger(__name__).error("Missing dependency: %s", mod_name)
            ok = False

    # Ensure directories
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    return ok


def stage_fetch(no_cache: bool = False) -> dict[str, Path]:
    """Stage 1: Fetch Dune data + CoinGecko prices."""
    log = logging.getLogger("fetch")

    from pipeline.fetch_dune import export_all_panels
    from pipeline.fetch_prices import fetch_and_save_prices, load_price_data

    log.info("=== STAGE: FETCH ===")

    # Dune panels
    saved = export_all_panels(output_dir=EXPORTS_DIR, no_cache=no_cache)
    log.info("Fetched %d/%d panels", len(saved), 16)

    # Prices
    try:
        vvv_csv = DATA_DIR / "vvv_prices.csv"
        btc_csv = DATA_DIR / "btc_prices.csv"
        cache_age = 6 * 3600

        if (
            not no_cache
            and vvv_csv.is_file()
            and btc_csv.is_file()
            and (time.time() - vvv_csv.stat().st_mtime) < cache_age
        ):
            log.info("Price CSVs are fresh — skipping CoinGecko fetch")
        else:
            fetch_and_save_prices(DATA_DIR, days=90)
    except Exception as exc:
        log.error("Price fetch failed: %s", exc)

    return saved


def stage_backtest() -> tuple[dict, dict, dict]:
    """Stage 2: Extract signals + run backtests."""
    log = logging.getLogger("backtest")
    log.info("=== STAGE: BACKTEST ===")

    from pipeline.signal_extract import extract_all_signals
    from pipeline.fetch_prices import load_price_data
    from pipeline.backtest import run_all_backtests
    from pipeline.output import write_backtest_report

    # Extract signals
    all_signals = extract_all_signals(EXPORTS_DIR, history_dir=HISTORY_DIR)

    # Load prices
    vvv_df, btc_df = load_price_data(DATA_DIR)

    # Run backtests
    backtest_results = run_all_backtests(all_signals, vvv_df, btc_df)

    # Save backtest report
    write_backtest_report(backtest_results, EXPORTS_DIR)

    return all_signals, backtest_results, {"vvv": vvv_df, "btc": btc_df}


def stage_composite(
    all_signals: dict | None = None,
    backtest_results: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Stage 3: Compute composite score + write output."""
    log = logging.getLogger("composite")
    log.info("=== STAGE: COMPOSITE ===")

    from pipeline.composite import build_composite
    from pipeline.output import build_signal_state, write_output

    # If not passed from prior stage, load from disk
    if all_signals is None:
        from pipeline.signal_extract import extract_all_signals
        all_signals = extract_all_signals(EXPORTS_DIR, history_dir=HISTORY_DIR)

    if backtest_results is None:
        bt_file = EXPORTS_DIR / "backtest_report_latest.json"
        if bt_file.is_file():
            backtest_results = json.loads(bt_file.read_text(encoding="utf-8"))
        else:
            log.error("No backtest results found. Run backtest stage first.")
            return {}

    # Build composite
    composite = build_composite(all_signals, backtest_results)

    # Build full state
    state = build_signal_state(
        composite=composite,
        panel_scores=composite["panel_scores"],
        weights=composite["weights"],
        backtest_results=backtest_results,
        all_signals=all_signals,
    )

    if dry_run:
        log.info("DRY RUN — not writing files")
        print(json.dumps(state, indent=2, default=str))
    else:
        write_output(state, EXPORTS_DIR)

    return state


def print_summary(state: dict) -> None:
    """Print a readable summary table."""
    print("\n" + "=" * 72)
    print(f"  VVV SIGNAL INTELLIGENCE — Pipeline Summary")
    print(f"  Generated: {state.get('generated_at', 'N/A')}")
    print("=" * 72)

    score = state.get("composite_score", 50)
    regime = state.get("regime", "NEUTRAL")
    print(f"\n  COMPOSITE SCORE: {score:.1f}  |  REGIME: {regime}")

    # Section breakdown
    sections = state.get("sections", {})
    if sections:
        print(f"\n  {'Section':<12} {'Composite':>10} {'Active':>8}")
        print(f"  {'-'*12} {'-'*10} {'-'*8}")
        for sec_id in sorted(sections.keys()):
            s = sections[sec_id]
            print(f"  Section {sec_id:<4} {s['composite']:>10.1f} {s['n_active']:>5}/{s['n_panels']}")

    # Panel details
    panels = state.get("panels", [])
    if panels:
        print(f"\n  {'Panel':<38} {'Score':>6} {'Weight':>7} {'Events':>7} {'Valid':>6} {'p-val':>7}")
        print(f"  {'-'*38} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*7}")
        for p in panels:
            name = p["name"][:36]
            pval = f"{p['best_p_value']:.3f}" if p.get("best_p_value") is not None else "  ---"
            valid = "YES" if p.get("validated") else " no"
            print(
                f"  {name:<38} {p['score']:>6.1f} {p['weight']:>6.1%} "
                f"{p['n_events']:>7} {valid:>6} {pval:>7}"
            )

    # Backtest summary
    bt = state.get("backtest_summary", {})
    if bt:
        print(f"\n  Validated: {bt.get('validated_panels', 0)}/{bt.get('total_panels', 0)} panels")
        print(f"  Total signal events: {bt.get('total_events', 0)}")

    print("=" * 72 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VVV Signal Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stage",
        choices=["fetch", "backtest", "composite", "all"],
        default="all",
        help="Which pipeline stage(s) to run (default: all)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached data, force re-fetch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout instead of writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    log = logging.getLogger("pipeline")

    log.info("VVV Signal Intelligence Pipeline — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Stage: %s | no-cache: %s | dry-run: %s", args.stage, args.no_cache, args.dry_run)

    if not check_prerequisites():
        log.error("Prerequisites check failed — aborting")
        return 1

    start = time.time()
    all_signals = None
    backtest_results = None
    state = {}

    try:
        if args.stage in ("fetch", "all"):
            stage_fetch(no_cache=args.no_cache)

        if args.stage in ("backtest", "all"):
            all_signals, backtest_results, _ = stage_backtest()

        if args.stage in ("composite", "all"):
            state = stage_composite(
                all_signals=all_signals,
                backtest_results=backtest_results,
                dry_run=args.dry_run,
            )

        elapsed = time.time() - start
        log.info("Pipeline complete in %.1fs", elapsed)

        if state:
            print_summary(state)

        return 0

    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130
    except Exception as exc:
        log.error("Pipeline failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
