#!/usr/bin/env python3
"""
Phase 5: VVV Dune Dashboard - Programmatic Query Deployment (API)
S2F Capital | April 2026

Deploys all 16 .sql files from queries/ to Dune Analytics via the API.
Avoids Cloudflare bot-detection that blocks browser automation.

Usage:
    1. Set API key: export DUNE_API_KEY="your-key-here"
       (or add to .env file, or source from ~/.config/bd-briefing/.env)
    2. Run:         python deploy_dune_queries.py
    3. Optional flags:
        --dry-run      Preview what would be deployed without hitting the API
        --private      Create all queries as private (default: public)
        --update       Update existing queries instead of creating new ones
                       (requires query_manifest.json from a prior deploy)
        --execute      Execute each query after creation to warm the cache

Requires: pip install requests python-dotenv
"""
import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    # Load local .env first, then fall back to bd-briefing .env for DUNE_API_KEY
    load_dotenv()
    bd_briefing_env = Path.home() / ".config" / "bd-briefing" / ".env"
    if bd_briefing_env.exists() and not os.environ.get("DUNE_API_KEY"):
        load_dotenv(bd_briefing_env)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DUNE_API_BASE = "https://api.dune.com/api/v1"
MANIFEST_FILE = "query_manifest.json"

QUERY_METADATA = {
    "panel_1a_sth_nupl_cost_basis": {
        "name": "[S2F] VVV - STH-NUPL Cost Basis Distribution",
        "description": "Panel 1A: Per-wallet unrealized PnL for 72hr new entrants. Sentiment phases: EUPHORIA/GREED/HOPE/FEAR/CAPITULATION.",
    },
    "panel_1b_sth_nupl_gauge": {
        "name": "[S2F] VVV - STH-NUPL Aggregate Gauge",
        "description": "Panel 1B: Headline single-number STH-NUPL gauge with regime classification (EUPHORIA/GREED/FEAR/CAPITULATION/NEUTRAL).",
    },
    "panel_1c_sth_nupl_time_series": {
        "name": "[S2F] VVV - STH-NUPL Time Series (30d)",
        "description": "Panel 1C: Daily rolling 72hr STH-NUPL over 30 days. Line chart with colored phase bands.",
    },
    "panel_2a_cex_netflows_daily": {
        "name": "[S2F] VVV - CEX Netflows (Daily)",
        "description": "Panel 2A: Daily VVV inflow/outflow to labeled CEX wallets. Negative net = bullish accumulation.",
    },
    "panel_2b_cex_netflows_cumulative": {
        "name": "[S2F] VVV - CEX Netflows (Cumulative)",
        "description": "Panel 2B: 90-day running total of CEX net flow. Below zero = exchanges draining.",
    },
    "panel_3_holder_vintage_bands": {
        "name": "[S2F] VVV - Holder Vintage Bands",
        "description": "Panel 3: Current holders classified by first-receive age (<24h, 1-7d, 7-30d, 30-90d, 90d+). Stacked area.",
    },
    "panel_4_svvv_staking_flows": {
        "name": "[S2F] VVV - sVVV Staking Flows",
        "description": "Panel 4: Daily stake/unstake volume into sVVV contract. Conviction proxy + structural supply removal.",
    },
    "panel_5_whale_wallet_monitor": {
        "name": "[S2F] VVV - Whale Wallet Monitor",
        "description": "Panel 5: Top 30 non-CEX wallets (>1K VVV) with 7-day delta. ACCUMULATING/DISTRIBUTING/FLAT.",
    },
    "panel_6_diem_minting": {
        "name": "[S2F] VVV - DIEM Minting Activity",
        "description": "Panel 6: Daily DIEM mints (from 0x0) and burns (to 0x0). Venice ecosystem health signal.",
    },
    "panel_7_dex_buy_sell_ratio": {
        "name": "[S2F] VVV - DEX Buy/Sell Ratio",
        "description": "Panel 7: 30-day DEX trade direction (Aerodrome + Uniswap V3 on Base). Buy/sell ratio + volumes.",
    },
    "panel_8_volume_vs_price": {
        "name": "[S2F] VVV - Transfer Volume vs Price",
        "description": "Panel 8: 90-day transfer volume, active addresses, and VVV price. Divergence detection.",
    },
    "panel_9a_new_stakers_daily": {
        "name": "[S2F] VVV - First-Time Stakers Daily",
        "description": "Panel 9A: Daily first-time VVV stakers since March 2026. Post-April 4 spike = OpenClaw migration.",
    },
    "panel_9b_pre_post_ban_comparison": {
        "name": "[S2F] VVV - Pre-Ban vs Post-Ban Stakers",
        "description": "Panel 9B: Staker acceleration factor across April 4 2026 19:00 UTC ban moment.",
    },
    "panel_10a_diem_mint_acceleration": {
        "name": "[S2F] VVV - DIEM Mint Acceleration Ratio",
        "description": "Panel 10A: Daily DIEM mint volume / trailing 7-day avg. >2x = notable, >5x = migration wave.",
    },
    "panel_10b_new_diem_minters": {
        "name": "[S2F] VVV - New DIEM Minter Wallets",
        "description": "Panel 10B: First-time DIEM minters per day = new Venice compute consumers.",
    },
    "panel_10c_conversion_funnel": {
        "name": "[S2F] VVV - Conversion Funnel (Post-Ban)",
        "description": "Panel 10C: VVV buyers -> stakers -> DIEM minters funnel from April 4, 2026.",
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dune-deploy")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def get_api_key() -> str:
    key = os.environ.get("DUNE_API_KEY", "")
    if not key:
        log.error("DUNE_API_KEY not set. Export it or add to .env file.")
        sys.exit(1)
    return key


def dune_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-DUNE-API-KEY": api_key,
    }


def create_query(api_key, name, sql, description="", is_private=False):
    payload = {
        "name": name,
        "query_sql": sql,
        "description": description,
        "is_private": is_private,
    }
    resp = requests.post(
        f"{DUNE_API_BASE}/query",
        headers=dune_headers(api_key),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_query(api_key, query_id, name, sql, description=""):
    payload = {
        "name": name,
        "query_sql": sql,
        "description": description,
    }
    resp = requests.patch(
        f"{DUNE_API_BASE}/query/{query_id}",
        headers=dune_headers(api_key),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def execute_query(api_key, query_id):
    resp = requests.post(
        f"{DUNE_API_BASE}/query/{query_id}/execute",
        headers=dune_headers(api_key),
        json={},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# File discovery + manifest
# ---------------------------------------------------------------------------
def discover_queries(queries_dir: Path) -> list:
    if not queries_dir.is_dir():
        log.error(f"Queries directory not found: {queries_dir}")
        sys.exit(1)

    sql_files = sorted(queries_dir.glob("*.sql"))
    if not sql_files:
        log.error(f"No .sql files found in {queries_dir}")
        sys.exit(1)

    queries = []
    for f in sql_files:
        stem = f.stem
        sql_text = f.read_text(encoding="utf-8").strip()

        if stem in QUERY_METADATA:
            meta = QUERY_METADATA[stem]
            name = meta["name"]
            desc = meta["description"]
        else:
            name = f"[S2F] VVV - {stem.replace('_', ' ').title()}"
            desc = f"Auto-deployed from {f.name}"
            log.warning(f"No metadata for '{stem}' - using auto-generated name")

        queries.append({
            "stem": stem,
            "path": str(f),
            "name": name,
            "description": desc,
            "sql": sql_text,
        })

    return queries


def load_manifest(project_dir: Path) -> dict:
    p = project_dir / MANIFEST_FILE
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_manifest(project_dir: Path, manifest: dict):
    p = project_dir / MANIFEST_FILE
    p.write_text(json.dumps(manifest, indent=2) + "\n")
    log.info(f"Manifest saved: {p}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def deploy(args):
    project_dir = Path(args.project_dir).resolve()
    queries_dir = project_dir / "queries"

    log.info(f"Project: {project_dir}")
    log.info(f"Queries: {queries_dir}")

    queries = discover_queries(queries_dir)
    log.info(f"Discovered {len(queries)} SQL files")

    if args.dry_run:
        log.info("=== DRY RUN - no API calls ===")
        for i, q in enumerate(queries, 1):
            lines = q["sql"].count("\n") + 1
            log.info(f"  [{i:2d}] {q['name']}")
            log.info(f"       {q['path']} ({lines} lines, {len(q['sql'])} chars)")
        log.info(f"\nTotal: {len(queries)} queries ready for deployment")
        return

    api_key = get_api_key()
    manifest = load_manifest(project_dir) if args.update else {}
    results = []
    errors = []

    for i, q in enumerate(queries, 1):
        stem = q["stem"]
        try:
            if args.update and stem in manifest:
                query_id = manifest[stem]["query_id"]
                log.info(f"[{i:2d}/{len(queries)}] Updating: {q['name']} (ID: {query_id})")
                update_query(api_key, query_id, q["name"], q["sql"], q["description"])
                action = "updated"
            else:
                log.info(f"[{i:2d}/{len(queries)}] Creating: {q['name']}")
                resp = create_query(api_key, q["name"], q["sql"], q["description"], args.private)
                query_id = resp.get("query_id")
                action = "created"

            url = f"https://dune.com/queries/{query_id}"
            result_entry = {
                "stem": stem,
                "name": q["name"],
                "query_id": query_id,
                "action": action,
                "url": url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            results.append(result_entry)
            manifest[stem] = {
                "query_id": query_id,
                "name": q["name"],
                "url": url,
                "last_deployed": datetime.now(timezone.utc).isoformat(),
            }

            log.info(f"  {action.upper()} -> ID: {query_id} | {url}")

            if args.execute and query_id:
                try:
                    exec_resp = execute_query(api_key, query_id)
                    exec_id = exec_resp.get("execution_id", "unknown")
                    log.info(f"  Execution triggered: {exec_id}")
                except Exception as ex:
                    log.warning(f"  Execution failed: {ex}")

            time.sleep(0.1)

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            body = e.response.text[:400] if e.response else str(e)
            log.error(f"  FAILED ({status}): {body}")
            errors.append({"stem": stem, "name": q["name"], "error": f"HTTP {status}: {body}"})
        except Exception as e:
            log.error(f"  FAILED: {e}")
            errors.append({"stem": stem, "name": q["name"], "error": str(e)})

    save_manifest(project_dir, manifest)

    log.info("")
    log.info("=" * 60)
    log.info("DEPLOYMENT SUMMARY")
    log.info("=" * 60)
    log.info(f"  Total:     {len(queries)}")
    log.info(f"  Succeeded: {len(results)}")
    log.info(f"  Failed:    {len(errors)}")

    if results:
        log.info("")
        log.info("Deployed queries:")
        for r in results:
            log.info(f"  [{r['action']:7s}] {r['name']}")
            log.info(f"              {r['url']}")

    if errors:
        log.info("")
        log.info("ERRORS:")
        for e in errors:
            log.info(f"  {e['name']}: {e['error']}")

    report_path = project_dir / f"deploy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "method": "api",
        "total": len(queries),
        "succeeded": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    log.info(f"\nFull report: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy VVV Dune Dashboard queries via Dune Analytics API",
    )
    parser.add_argument("--project-dir", default=".", help="Path to vvv-dune-dashboard/ root")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--private", action="store_true", help="Create as private (default: public)")
    parser.add_argument("--update", action="store_true", help="Update existing queries via manifest")
    parser.add_argument("--execute", action="store_true", help="Execute each query to warm cache")

    args = parser.parse_args()
    deploy(args)


if __name__ == "__main__":
    main()
