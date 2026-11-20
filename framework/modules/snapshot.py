"""Snapshot renderer for the deck team: dashboard -> PNG (and PDF) with Playwright, headless.

    rbc-bi snapshot sales-overview            # snapshots/sales-overview.png + .pdf
    rbc-bi snapshot sales-overview --no-pdf

If the app isn't already running on the port, it is started for the duration of the snapshot.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from rbc_bi import paths

WIDTH, HEIGHT = 1920, 1080


def _up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def snapshot(dashboard_id: str, port: int = 8050, out_dir: Path | None = None, pdf: bool = True,
             full_page: bool = True) -> list[Path]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Playwright is not installed: pip install playwright && playwright install chromium") from exc

    out_dir = out_dir or paths.ROOT / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"http://localhost:{port}"
    server = None
    if not _up(base + "/"):
        server = subprocess.Popen([sys.executable, "-m", "rbc_bi", "run", "--no-reload", "--port", str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if _up(base + "/"):
                break
            time.sleep(0.5)
    written = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            page.goto(f"{base}/{dashboard_id}?snapshot=1", wait_until="networkidle")
            # Wait for every figure to finish loading.
            page.wait_for_function("document.querySelectorAll('[data-dash-is-loading=\"true\"]').length === 0",
                                   timeout=30_000)
            page.wait_for_timeout(1500)
            png = out_dir / f"{dashboard_id}.png"
            page.screenshot(path=str(png), full_page=full_page)
            written.append(png)
            if pdf:
                pdf_path = out_dir / f"{dashboard_id}.pdf"
                page.emulate_media(media="screen")
                page.pdf(path=str(pdf_path), width=f"{WIDTH}px", height=f"{page.evaluate('document.body.scrollHeight')}px",
                         print_background=True)
                written.append(pdf_path)
            browser.close()
    finally:
        if server:
            server.terminate()
    return written
