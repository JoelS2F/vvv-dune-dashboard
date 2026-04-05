#!/usr/bin/env python3
"""
Phase 5: VVV Dune Dashboard - Browser-Based Query Deployment (Free Tier)
S2F Capital | April 2026

Deploys all .sql files from queries/ to Dune Analytics via Playwright browser
automation. Works on the FREE tier - no Analyst plan required.

Workflow:
    1. Logs into Dune with your credentials
    2. For each .sql file: creates a new query, pastes SQL, sets name/description
    3. Saves each query and captures the query ID from the URL
    4. Writes query_manifest.json mapping filenames -> Dune query IDs + URLs
    5. Optionally executes each query to warm the cache

Usage:
    1. Install deps:      pip install playwright python-dotenv
                          playwright install chromium
    2. Set credentials:   export DUNE_USERNAME="your-email"
                          export DUNE_PASSWORD="your-password"
       (or add to .env file in project root)
    3. Run:               python deploy_dune_browser.py
    4. Optional flags:
        --dry-run         Preview what would be deployed
        --headed          Run browser visibly (not headless) for debugging
        --slow-mo 500     Slow down actions by N ms for debugging
        --skip-login      Skip login if you have a saved session state
        --save-session    Save browser session for reuse with --skip-login
        --execute         Click "Run" on each query after creation
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
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None
    PWTimeout = Exception

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Query metadata - maps filename stem to display name + description
# ---------------------------------------------------------------------------
QUERY_METADATA = {
    # Panel 1: STH-NUPL (New Entrant Cost Basis)
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
    # Panel 2: CEX Netflows
    "panel_2a_cex_netflows_daily": {
        "name": "[S2F] VVV - CEX Netflows (Daily)",
        "description": "Panel 2A: Daily VVV inflow/outflow to labeled CEX wallets. Negative net = bullish accumulation.",
    },
    "panel_2b_cex_netflows_cumulative": {
        "name": "[S2F] VVV - CEX Netflows (Cumulative)",
        "description": "Panel 2B: 90-day running total of CEX net flow. Below zero = exchanges draining.",
    },
    # Panel 3: Holder Vintage
    "panel_3_holder_vintage_bands": {
        "name": "[S2F] VVV - Holder Vintage Bands",
        "description": "Panel 3: Current holders classified by first-receive age (<24h, 1-7d, 7-30d, 30-90d, 90d+). Stacked area.",
    },
    # Panel 4: sVVV Staking
    "panel_4_svvv_staking_flows": {
        "name": "[S2F] VVV - sVVV Staking Flows",
        "description": "Panel 4: Daily stake/unstake volume into sVVV contract. Conviction proxy + structural supply removal.",
    },
    # Panel 5: Whale Monitor
    "panel_5_whale_wallet_monitor": {
        "name": "[S2F] VVV - Whale Wallet Monitor",
        "description": "Panel 5: Top 30 non-CEX wallets (>1K VVV) with 7-day delta. ACCUMULATING/DISTRIBUTING/FLAT.",
    },
    # Panel 6: DIEM Minting
    "panel_6_diem_minting": {
        "name": "[S2F] VVV - DIEM Minting Activity",
        "description": "Panel 6: Daily DIEM mints (from 0x0) and burns (to 0x0). Venice ecosystem health signal.",
    },
    # Panel 7: DEX Buy/Sell
    "panel_7_dex_buy_sell_ratio": {
        "name": "[S2F] VVV - DEX Buy/Sell Ratio",
        "description": "Panel 7: 30-day DEX trade direction (Aerodrome + Uniswap V3 on Base). Buy/sell ratio + volumes.",
    },
    # Panel 8: Volume vs Price
    "panel_8_volume_vs_price": {
        "name": "[S2F] VVV - Transfer Volume vs Price",
        "description": "Panel 8: 90-day transfer volume, active addresses, and VVV price. Divergence detection.",
    },
    # Panel 9: Migration Stakers
    "panel_9a_new_stakers_daily": {
        "name": "[S2F] VVV - First-Time Stakers Daily",
        "description": "Panel 9A: Daily first-time VVV stakers since March 2026. Post-April 4 spike = OpenClaw migration.",
    },
    "panel_9b_pre_post_ban_comparison": {
        "name": "[S2F] VVV - Pre-Ban vs Post-Ban Stakers",
        "description": "Panel 9B: Staker acceleration factor across April 4 2026 19:00 UTC ban moment.",
    },
    # Panel 10: DIEM Acceleration
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

# ---------------------------------------------------------------------------
# Dune URL constants
# ---------------------------------------------------------------------------
DUNE_LOGIN_URL = "https://dune.com/auth/login"
DUNE_NEW_QUERY_URL = "https://dune.com/queries/new"
DUNE_HOME_URL = "https://dune.com"
SESSION_FILE = "dune_session.json"
MANIFEST_FILE = "query_manifest.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dune-browser-deploy")


# ---------------------------------------------------------------------------
# File discovery
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


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
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
# Browser automation
# ---------------------------------------------------------------------------
def login_to_dune(page, username: str, password: str):
    """Log into Dune Analytics."""
    log.info("Navigating to Dune login...")
    page.goto(DUNE_LOGIN_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    email_sel = 'input[name="email"], input[type="email"], input[placeholder*="email" i]'
    pass_sel = 'input[name="password"], input[type="password"]'

    try:
        page.wait_for_selector(email_sel, timeout=10000)
    except PWTimeout:
        if "dune.com" in page.url and "login" not in page.url:
            log.info("Already logged in!")
            return
        log.warning("Could not find email input - check if login page changed")
        page.screenshot(path="debug_login.png")
        raise

    page.fill(email_sel, username)
    time.sleep(0.5)
    page.fill(pass_sel, password)
    time.sleep(0.5)

    submit_sel = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")'
    page.click(submit_sel)

    log.info("Waiting for login to complete...")
    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30000)
    except PWTimeout:
        log.error("Login timed out - check credentials or 2FA requirements")
        page.screenshot(path="debug_login_timeout.png")
        raise

    time.sleep(2)
    log.info(f"Logged in successfully. Current URL: {page.url}")


def create_query_in_browser(page, name: str, sql: str, description: str, execute: bool = False):
    """
    Create a single query in the Dune UI.
    Returns the query ID extracted from the URL, or None on failure.
    """
    page.goto(DUNE_NEW_QUERY_URL, wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # --- Step 1: Set query title ---
    title_selectors = [
        'input[placeholder*="title" i]',
        'input[placeholder*="name" i]',
        'input[placeholder*="Untitled" i]',
        '[data-testid="query-title-input"]',
        '.query-title input',
        'h1[contenteditable="true"]',
        '[contenteditable="true"]',
    ]

    title_set = False
    for sel in title_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000)
            if el:
                el.click()
                time.sleep(0.3)
                page.keyboard.press("Control+a")
                page.keyboard.type(name, delay=20)
                title_set = True
                log.info(f"  Title set via: {sel}")
                break
        except (PWTimeout, Exception):
            continue

    if not title_set:
        log.warning("  Could not find title input - query will be 'Untitled'")

    # --- Step 2: Paste SQL into the editor ---
    editor_selectors = [
        '.cm-content',
        '.CodeMirror textarea',
        '.monaco-editor textarea',
        '[role="textbox"]',
        '.view-lines',
        'textarea.inputarea',
    ]

    sql_pasted = False
    for sel in editor_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000)
            if el:
                el.click()
                time.sleep(0.3)
                page.keyboard.press("Control+a")
                time.sleep(0.2)
                page.evaluate(f"navigator.clipboard.writeText({json.dumps(sql)})")
                page.keyboard.press("Control+v")
                time.sleep(0.5)
                sql_pasted = True
                log.info(f"  SQL pasted via: {sel}")
                break
        except (PWTimeout, Exception):
            continue

    if not sql_pasted:
        try:
            page.evaluate(f"""
                const cm = document.querySelector('.cm-content');
                if (cm) {{
                    cm.focus();
                    document.execCommand('selectAll');
                    document.execCommand('insertText', false, {json.dumps(sql)});
                }}
            """)
            sql_pasted = True
            log.info("  SQL pasted via DOM fallback")
        except Exception as e:
            log.error(f"  Failed to paste SQL: {e}")
            return None

    # --- Step 3: Save the query ---
    time.sleep(1)
    page.keyboard.press("Control+s")
    time.sleep(3)

    try:
        page.wait_for_url(
            lambda url: "/queries/" in url and "/new" not in url,
            timeout=15000,
        )
    except PWTimeout:
        save_selectors = [
            'button:has-text("Save")',
            '[data-testid="save-button"]',
            'button[aria-label="Save"]',
        ]
        for sel in save_selectors:
            try:
                page.click(sel, timeout=3000)
                time.sleep(3)
                break
            except (PWTimeout, Exception):
                continue

        try:
            page.wait_for_url(
                lambda url: "/queries/" in url and "/new" not in url,
                timeout=10000,
            )
        except PWTimeout:
            log.error("  Save failed - URL never updated with query ID")
            page.screenshot(path=f"debug_save_fail_{name[:30]}.png")
            return None

    # --- Step 4: Extract query ID from URL ---
    current_url = page.url
    query_id = None
    try:
        parts = current_url.split("/queries/")
        if len(parts) > 1:
            id_str = parts[1].split("/")[0].split("?")[0]
            query_id = int(id_str)
    except (ValueError, IndexError):
        log.error(f"  Could not parse query ID from URL: {current_url}")
        return None

    # --- Step 5: Optionally execute the query ---
    if execute and query_id:
        try:
            run_selectors = [
                'button:has-text("Run")',
                'button:has-text("Execute")',
                '[data-testid="run-button"]',
                'button[aria-label="Run query"]',
            ]
            for sel in run_selectors:
                try:
                    page.click(sel, timeout=3000)
                    log.info("  Execution triggered")
                    time.sleep(2)
                    break
                except (PWTimeout, Exception):
                    continue
        except Exception as e:
            log.warning(f"  Could not trigger execution: {e}")

    return query_id


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
        log.info("=== DRY RUN ===")
        for i, q in enumerate(queries, 1):
            lines = q["sql"].count("\n") + 1
            log.info(f"  [{i:2d}] {q['name']}")
            log.info(f"       {q['path']} ({lines} lines, {len(q['sql'])} chars)")
        log.info(f"\nTotal: {len(queries)} queries ready for deployment")
        return

    if not _PLAYWRIGHT_AVAILABLE:
        log.error("'playwright' package required for deployment.")
        log.error("  pip install playwright")
        log.error("  playwright install chromium")
        sys.exit(1)

    username = os.environ.get("DUNE_USERNAME", "")
    password = os.environ.get("DUNE_PASSWORD", "")
    if not args.skip_login and (not username or not password):
        log.error("Set DUNE_USERNAME and DUNE_PASSWORD env vars (or use .env file)")
        sys.exit(1)

    manifest = load_manifest(project_dir)
    results = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            slow_mo=args.slow_mo,
        )

        session_path = project_dir / SESSION_FILE
        if args.skip_login and session_path.exists():
            context = browser.new_context(storage_state=str(session_path))
            log.info("Loaded saved session state")
        else:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )

        page = context.new_page()

        if not args.skip_login:
            try:
                login_to_dune(page, username, password)
            except Exception as e:
                log.error(f"Login failed: {e}")
                browser.close()
                sys.exit(1)

            if args.save_session:
                context.storage_state(path=str(session_path))
                log.info(f"Session saved to {session_path}")

        for i, q in enumerate(queries, 1):
            stem = q["stem"]
            log.info(f"[{i:2d}/{len(queries)}] Creating: {q['name']}")

            try:
                query_id = create_query_in_browser(
                    page,
                    name=q["name"],
                    sql=q["sql"],
                    description=q["description"],
                    execute=args.execute,
                )

                if query_id:
                    url = f"https://dune.com/queries/{query_id}"
                    result_entry = {
                        "stem": stem,
                        "name": q["name"],
                        "query_id": query_id,
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
                    log.info(f"  CREATED -> ID: {query_id} | {url}")
                else:
                    errors.append({"stem": stem, "name": q["name"], "error": "No query ID returned"})
                    log.error("  FAILED - could not extract query ID")

                time.sleep(2)

            except Exception as e:
                log.error(f"  FAILED: {e}")
                errors.append({"stem": stem, "name": q["name"], "error": str(e)})
                page.screenshot(path=f"debug_error_{stem[:30]}.png")

        browser.close()

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
            log.info(f"  {r['name']}")
            log.info(f"    {r['url']}")

    if errors:
        log.info("")
        log.info("ERRORS:")
        for e in errors:
            log.info(f"  {e['name']}: {e['error']}")

    report_path = project_dir / f"deploy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "method": "browser_automation",
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
        description="Deploy VVV Dune Dashboard queries via browser automation (free tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deploy_dune_browser.py --dry-run                   # Preview
  python deploy_dune_browser.py --headed                    # Watch it work
  python deploy_dune_browser.py --headed --slow-mo 300      # Slow for debugging
  python deploy_dune_browser.py --save-session              # Save login for reuse
  python deploy_dune_browser.py --skip-login --execute      # Reuse session + run queries
  python deploy_dune_browser.py --project-dir ./vvv-dune-dashboard
        """,
    )
    parser.add_argument("--project-dir", default=".", help="Path to vvv-dune-dashboard/ root")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deploying")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--slow-mo", type=int, default=0, help="Slow down actions by N ms")
    parser.add_argument("--skip-login", action="store_true", help="Use saved session state")
    parser.add_argument("--save-session", action="store_true", help="Save session after login")
    parser.add_argument("--execute", action="store_true", help="Run each query after creation")

    args = parser.parse_args()
    deploy(args)


if __name__ == "__main__":
    main()
