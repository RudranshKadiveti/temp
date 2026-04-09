from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page


@dataclass
class PaginationResult:
    moved: bool
    method: str = "none"


class SmartPaginator:
    NEXT_SELECTORS = [
        "a[aria-label='Next']",
        "a[rel='next']",
        "button[aria-label='Next']",
        "a:has-text('Next')",
        "a:has-text('>')",
        ".pagination-next",
        ".next a",
    ]

    async def next_page(self, page: Page) -> PaginationResult:
        before = page.url

        for selector in self.NEXT_SELECTORS:
            element = await page.query_selector(selector)
            if not element:
                continue
            if not await element.is_visible():
                continue
            await element.click()
            await page.wait_for_load_state("domcontentloaded")
            if page.url != before:
                return PaginationResult(True, f"next_button:{selector}")

        # Infinite scroll fallback
        prev_height = await page.evaluate("() => document.body.scrollHeight")
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.0)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height > prev_height:
            return PaginationResult(True, "infinite_scroll")

        return PaginationResult(False, "none")
