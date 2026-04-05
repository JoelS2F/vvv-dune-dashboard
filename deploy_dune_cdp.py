#!/usr/bin/env python3
"""
VVV Dune Dashboard - CDP-based Query Deployment
S2F Capital | April 2026

Attaches Playwright to a real already-running Chrome/Edge instance via the
Chrome DevTools Protocol (CDP), bypassing Cloudflare bot detection by using
your actual authenticated browser session.

PREREQUISITE: Chrome/Edge must be launched with --remote-debugging-port=9223
              and you must be signed into dune.com already.

Usage:
    1. Run launch_chrome_cdp.bat (or .ps1)
    2. Verify you're signed into dune.com in the opened window
    3. python deploy_dune_cdp.py [--execute]

Requires: pip install playwright python-dotenv
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
except ImportError:
    print("ERROR: 'playwright' package required.")
    print("  pip install playwright")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CDP_ENDPOINT = os.environ.get("CDP_ENDPOINT", "http://localhost:9223")
DUNE_NEW_QUERY_URL = "https://dune.com/queries/new"
MANIFEST_FILE = "query_manifest.json"

# Same metadata as deploy_dune_queries.py / deploy_dune_browser.py
QUERY_METADATA = {
    "panel_1a_sth_nupl_cost_basis": {
        "name": "[S2F] VVV - STH-NUPL Cost Basis Distribution",
        "description": "Panel 1A: Per-wallet unrealized PnL for 72hr new entrants.",
    },
    "panel_1b_sth_nupl_gauge": {
        "name": "[S2F] VVV - STH-NUPL Aggregate Gauge",
        "description": "Panel 1B: Headline STH-NUPL gauge with regime classification.",
    },
    "panel_1c_sth_nupl_time_series": {
        "name": "[S2F] VVV - STH-NUPL Time Series (30d)",
        "description": "Panel 1C: Daily rolling 72hr STH-NUPL over 30 days.",
    },
    "panel_2a_cex_netflows_daily": {
        "name": "[S2F] VVV - CEX Netflows (Daily)",
        "description": "Panel 2A: Daily VVV inflow/outflow to labeled CEX wallets.",
    },
    "panel_2b_cex_netflows_cumulative": {
        "name": "[S2F] VVV - CEX Netflows (Cumulative)",
        "description": "Panel 2B: 90-day running total of CEX net flow.",
    },
    "panel_3_holder_vintage_bands": {
        "name": "[S2F] VVV - Holder Vintage Bands",
        "description": "Panel 3: Current holders classified by first-receive age.",
    },
    "panel_4_svvv_staking_flows": {
        "name": "[S2F] VVV - sVVV Staking Flows",
        "description": "Panel 4: Daily stake/unstake volume into sVVV contract.",
    },
    "panel_5_whale_wallet_monitor": {
        "name": "[S2F] VVV - Whale Wallet Monitor",
        "description": "Panel 5: Top 30 non-CEX wallets (>1K VVV) with 7-day delta.",
    },
    "panel_6_diem_minting": {
        "name": "[S2F] VVV - DIEM Minting Activity",
        "description": "Panel 6: Daily DIEM mints and burns. Venice ecosystem health.",
    },
    "panel_7_dex_buy_sell_ratio": {
        "name": "[S2F] VVV - DEX Buy/Sell Ratio",
        "description": "Panel 7: 30-day DEX trade direction. Buy/sell ratio + volumes.",
    },
    "panel_8_volume_vs_price": {
        "name": "[S2F] VVV - Transfer Volume vs Price",
        "description": "Panel 8: 90-day transfer volume vs price. Divergence detection.",
    },
    "panel_9a_new_stakers_daily": {
        "name": "[S2F] VVV - First-Time Stakers Daily",
        "description": "Panel 9A: Daily first-time VVV stakers since March 2026.",
    },
    "panel_9b_pre_post_ban_comparison": {
        "name": "[S2F] VVV - Pre-Ban vs Post-Ban Stakers",
        "description": "Panel 9B: Staker acceleration across April 4 2026 19:00 UTC.",
    },
    "panel_10a_diem_mint_acceleration": {
        "name": "[S2F] VVV - DIEM Mint Acceleration Ratio",
        "description": "Panel 10A: Daily DIEM mint volume / trailing 7-day avg.",
    },
    "panel_10b_new_diem_minters": {
        "name": "[S2F] VVV - New DIEM Minter Wallets",
        "description": "Panel 10B: First-time DIEM minters per day = new compute consumers.",
    },
    "panel_10c_conversion_funnel": {
        "name": "[S2F] VVV - Conversion Funnel (Post-Ban)",
        "description": "Panel 10C: VVV buyers -> stakers -> DIEM minters funnel.",
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dune-cdp-deploy")


def discover_queries(queries_dir: Path) -> list:
    sql_files = sorted(queries_dir.glob("*.sql"))
    if not sql_files:
        log.error(f"No .sql files in {queries_dir}")
        sys.exit(1)
    out = []
    for f in sql_files:
        stem = f.stem
        meta = QUERY_METADATA.get(stem, {})
        out.append({
            "stem": stem,
            "path": str(f),
            "name": meta.get("name", f"[S2F] VVV - {stem}"),
            "description": meta.get("description", f"Auto-deployed from {f.name}"),
            "sql": f.read_text(encoding="utf-8").strip(),
        })
    return out


def load_manifest(project_dir: Path) -> dict:
    p = project_dir / MANIFEST_FILE
    return json.loads(p.read_text()) if p.exists() else {}


def save_manifest(project_dir: Path, manifest: dict):
    p = project_dir / MANIFEST_FILE
    p.write_text(json.dumps(manifest, indent=2) + "\n")
    log.info(f"Manifest saved: {p}")


def verify_signed_in(page) -> bool:
    """Quick check: navigate to Dune and look for signed-in UI markers."""
    log.info("Verifying signed-in status on Dune...")
    page.goto("https://dune.com/home", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    url = page.url
    content = page.content()[:3000].lower()
    if "you have been blocked" in content or "cloudflare" in content and "challenge" in content:
        log.error("Cloudflare is blocking even CDP session! Browser may have been flagged.")
        return False
    if "/auth/login" in url or "/login" in url or "sign in" in content and "sign up" in content:
        log.error(f"Not signed in to Dune. Current URL: {url}")
        log.error("Please sign in manually in the CDP-attached browser, then re-run.")
        return False
    log.info(f"Signed in OK (URL: {url})")
    return True


def create_query_via_ui(page, name: str, sql: str, description: str, execute: bool = False):
    """Create a single query by driving the Dune /queries/new UI."""
    page.goto(DUNE_NEW_QUERY_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # Set title
    title_selectors = [
        'input[placeholder*="title" i]',
        'input[placeholder*="Untitled" i]',
        '[data-testid="query-title-input"]',
        'h1[contenteditable="true"]',
    ]
    title_set = False
    for sel in title_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000)
            if el:
                el.click()
                time.sleep(0.3)
                page.keyboard.press("Control+a")
                page.keyboard.type(name, delay=15)
                title_set = True
                break
        except Exception:
            continue
    if not title_set:
        log.warning("  Title input not found - query will be 'Untitled'")

    # Paste SQL into editor
    editor_selectors = ['.cm-content', 'textarea.inputarea', '.monaco-editor textarea', '[role="textbox"]']
    pasted = False
    for sel in editor_selectors:
        try:
            el = page.wait_for_selector(sel, timeout=3000)
            if el:
                el.click()
                time.sleep(0.3)
                page.keyboard.press("Control+a")
                time.sleep(0.2)
                # Clipboard-free approach: use page.evaluate to insert directly
                page.evaluate(
                    """([selector, text]) => {
                        const el = document.querySelector(selector);
                        if (el) { el.focus(); document.execCommand('selectAll'); document.execCommand('insertText', false, text); }
                    }""",
                    [sel, sql],
                )
                time.sleep(0.5)
                pasted = True
                break
        except Exception:
            continue
    if not pasted:
        log.error("  Could not paste SQL into editor")
        return None

    # Save with Ctrl+S
    time.sleep(1)
    page.keyboard.press("Control+s")
    time.sleep(3)

    try:
        page.wait_for_url(lambda url: "/queries/" in url and "/new" not in url, timeout=15000)
    except PWTimeout:
        for sel in ['button:has-text("Save")', '[data-testid="save-button"]']:
            try:
                page.click(sel, timeout=3000)
                time.sleep(3)
                break
            except Exception:
                continue
        try:
            page.wait_for_url(lambda url: "/queries/" in url and "/new" not in url, timeout=10000)
        except PWTimeout:
            log.error(f"  Save failed - URL: {page.url}")
            return None

    # Parse query ID
    url = page.url
    try:
        id_str = url.split("/queries/")[1].split("/")[0].split("?")[0]
        query_id = int(id_str)
    except (ValueError, IndexError):
        log.error(f"  Couldn't parse query ID from URL: {url}")
        return None

    if execute:
        for sel in ['button:has-text("Run")', '[data-testid="run-button"]']:
            try:
                page.click(sel, timeout=3000)
                log.info("  Execution triggered")
                time.sleep(2)
                break
            except Exception:
                continue

    return query_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--cdp", default=CDP_ENDPOINT, help="CDP endpoint (default http://localhost:9223)")
    parser.add_argument("--execute", action="store_true", help="Execute each query after creation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    queries = discover_queries(project_dir / "queries")
    log.info(f"Discovered {len(queries)} SQL files")

    if args.dry_run:
        for i, q in enumerate(queries, 1):
            log.info(f"  [{i:2d}] {q['name']} ({len(q['sql'])} chars)")
        return

    manifest = load_manifest(project_dir)
    results, errors = [], []

    with sync_playwright() as p:
        log.info(f"Connecting to Chrome via CDP at {args.cdp}...")
        try:
            browser = p.chromium.connect_over_cdp(args.cdp)
        except Exception as e:
            log.error(f"Could not connect to CDP endpoint: {e}")
            log.error("Make sure Chrome is running with --remote-debugging-port=9223")
            log.error("Run launch_chrome_cdp.bat first.")
            sys.exit(1)

        # Use existing context (your real signed-in session)
        contexts = browser.contexts
        if not contexts:
            log.error("No browser contexts found")
            browser.close()
            sys.exit(1)
        context = contexts[0]
        log.info(f"Connected. Using existing context with {len(context.pages)} page(s)")

        # Open a new tab for our work
        page = context.new_page()

        if not verify_signed_in(page):
            page.close()
            browser.close()
            sys.exit(1)

        for i, q in enumerate(queries, 1):
            log.info(f"[{i:2d}/{len(queries)}] Creating: {q['name']}")
            try:
                query_id = create_query_via_ui(page, q["name"], q["sql"], q["description"], args.execute)
                if query_id:
                    url = f"https://dune.com/queries/{query_id}"
                    results.append({"stem": q["stem"], "name": q["name"], "query_id": query_id, "url": url})
                    manifest[q["stem"]] = {
                        "query_id": query_id,
                        "name": q["name"],
                        "url": url,
                        "last_deployed": datetime.now(timezone.utc).isoformat(),
                    }
                    log.info(f"  CREATED -> ID: {query_id} | {url}")
                else:
                    errors.append({"stem": q["stem"], "name": q["name"], "error": "Save failed"})
                time.sleep(2)
            except Exception as e:
                log.error(f"  FAILED: {e}")
                errors.append({"stem": q["stem"], "name": q["name"], "error": str(e)})

        page.close()
        # Don't browser.close() — that would close the user's browser

    save_manifest(project_dir, manifest)

    log.info("")
    log.info("=" * 60)
    log.info(f"SUMMARY: {len(results)}/{len(queries)} succeeded, {len(errors)} failed")
    log.info("=" * 60)
    for r in results:
        log.info(f"  {r['name']}\n    {r['url']}")
    if errors:
        log.info("ERRORS:")
        for e in errors:
            log.info(f"  {e['name']}: {e['error']}")

    report_path = project_dir / f"deploy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps({
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "method": "cdp",
        "total": len(queries),
        "succeeded": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }, indent=2) + "\n")
    log.info(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
