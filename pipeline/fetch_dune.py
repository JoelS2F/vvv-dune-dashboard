"""
VVV Signal Intelligence — Dune Analytics data fetcher
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import DUNE_API_BASE, PANELS, PanelConfig

log = logging.getLogger(__name__)

CACHE_MAX_AGE_SECONDS = 6 * 3600  # 6 hours


# ── Environment ────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Load DUNE_API_KEY from environment, local .env, or bd-briefing config."""
    key = os.environ.get("DUNE_API_KEY")
    if key:
        return key

    # Try local .env first
    for env_path in [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path.home() / ".config" / "bd-briefing" / ".env",
    ]:
        if env_path.is_file():
            log.debug("Scanning %s for DUNE_API_KEY", env_path)
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'\"")
                if k == "DUNE_API_KEY" and v:
                    os.environ["DUNE_API_KEY"] = v
                    return v

    raise EnvironmentError(
        "DUNE_API_KEY not found in env, .env, or ~/.config/bd-briefing/.env"
    )


# ── Single query fetch ─────────────────────────────────────────────────────

def fetch_query_results(
    api_key: str,
    query_id: int,
    limit: int = 10_000,
) -> dict[str, Any]:
    """
    Fetch latest results for a Dune query.
    Returns the full JSON response (with metadata + rows).
    """
    url = f"{DUNE_API_BASE}/query/{query_id}/results"
    headers = {"X-DUNE-API-KEY": api_key}
    params = {"limit": limit}

    log.info("Fetching Dune query %d (limit=%d)", query_id, limit)
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    row_count = len(data.get("result", {}).get("rows", []))
    log.info("  -> %d rows returned for query %d", row_count, query_id)
    return data


# ── Cache helpers ──────────────────────────────────────────────────────────

def _cache_path(output_dir: Path, panel_id: str) -> Path:
    return output_dir / f"{panel_id}_raw.json"


def _is_cache_fresh(path: Path) -> bool:
    """Return True if cached file exists and is younger than CACHE_MAX_AGE_SECONDS."""
    if not path.is_file():
        return False
    mtime = path.stat().st_mtime
    age = time.time() - mtime
    return age < CACHE_MAX_AGE_SECONDS


# ── Bulk export ────────────────────────────────────────────────────────────

def export_all_panels(
    panels: dict[str, PanelConfig] | None = None,
    api_key: str | None = None,
    output_dir: str | Path | None = None,
    no_cache: bool = False,
) -> dict[str, Path]:
    """
    Iterate all panels, fetch from Dune, save to exports/{panel_id}_raw.json.
    Returns dict of panel_id -> saved file path.
    Sleeps 2s between API calls to respect rate limits.
    """
    panels = panels or PANELS
    api_key = api_key or _load_api_key()

    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "exports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: dict[str, Path] = {}
    errors: list[str] = []

    for i, (panel_id, cfg) in enumerate(panels.items()):
        dest = _cache_path(output_dir, panel_id)

        # Cache check
        if not no_cache and _is_cache_fresh(dest):
            log.info("Cache fresh for %s — skipping fetch", panel_id)
            saved[panel_id] = dest
            continue

        try:
            data = fetch_query_results(api_key, cfg.query_id)
            dest.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            saved[panel_id] = dest
            log.info("Saved %s -> %s", panel_id, dest)
        except Exception as exc:
            log.error("FAILED %s (query %d): %s", panel_id, cfg.query_id, exc)
            errors.append(panel_id)

        # Rate-limit sleep (skip after last item)
        if i < len(panels) - 1:
            time.sleep(2)

    if errors:
        log.warning("Failed panels: %s", ", ".join(errors))

    return saved


def load_panel_data(panel_id: str, export_dir: str | Path) -> list[dict]:
    """Load raw rows from a cached export file."""
    path = _cache_path(Path(export_dir), panel_id)
    if not path.is_file():
        log.warning("No export file for %s at %s", panel_id, path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("result", {}).get("rows", [])
