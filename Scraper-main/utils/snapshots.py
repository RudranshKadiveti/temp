from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.async_api import Page


async def save_debug_snapshot(page: Page, output_dir: str = "data/logs/snapshots") -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    html_path = root / f"{stamp}.html"
    png_path = root / f"{stamp}.png"

    html_path.write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(png_path), full_page=True)

    return {"html": str(html_path), "screenshot": str(png_path)}
