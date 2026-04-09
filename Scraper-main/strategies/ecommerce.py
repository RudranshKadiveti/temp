from __future__ import annotations

import json
import urllib.parse
from typing import Any

from playwright.async_api import Page

from core.models import SiteType


class BaseStrategy:
    def __init__(self, page: Page):
        self.page = page

    async def apply_filters(self, url: str, filters: dict[str, Any]) -> str:
        return url

    async def apply_dom_filters(self, filters: dict[str, Any]) -> None:
        keyword = (filters.get("query") or "").strip().lower()
        if not keyword:
            return

        await self.page.evaluate(
            """
            (kw) => {
                            const blocks = Array.from(document.querySelectorAll('article, li, [class*=card], [class*=item], tr, .product, .listing'));
                            if (blocks.length < 6) return;

                            const matches = blocks.filter(block => ((block.innerText || '').toLowerCase()).includes(kw));

                            // Guardrail: if query is too narrow, keep page intact to avoid zero extraction.
                            if (matches.length < 3 || (matches.length / blocks.length) < 0.1) {
                                return;
                            }

                            for (const block of blocks) {
                                const text = (block.innerText || '').toLowerCase();
                                if (!text.includes(kw)) {
                                    block.style.display = 'none';
                                }
                            }
            }
            """,
            keyword,
        )

    def get_extraction_schema(self) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "name": "",
                        "value": "",
                        "url": "",
                    }
                ]
            }
        )


class EcommerceStrategy(BaseStrategy):
    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def get_extraction_schema(self) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "name": "",
                        "description": "",
                        "price": "",
                        "currency": "",
                        "discount": "",
                        "rating": "",
                        "reviews": "",
                        "brand": "",
                        "specs": "",
                        "availability": "",
                        "url": "",
                        "image_url": "",
                    }
                ]
            }
        )

    async def apply_filters(self, url: str, filters: dict[str, Any]) -> str:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        price_min = self._to_float_or_none(filters.get("price_min"))
        price_max = self._to_float_or_none(filters.get("price_max"))
        brand = (filters.get("brand") or "").strip()
        query = (filters.get("query") or "").strip()
        rating = self._to_float_or_none(filters.get("min_rating"))

        host = parsed.netloc.lower()
        if "amazon" in host:
            if price_min is not None:
                qs["low-price"] = [str(int(price_min))]
            if price_max is not None:
                qs["high-price"] = [str(int(price_max))]
            if query:
                qs["k"] = [str(query)]
            if brand:
                qs["rh"] = [f"p_89:{brand}"]
        else:
            if query:
                qs.setdefault("q", [str(query)])
            if price_min is not None:
                qs["min_price"] = [str(price_min)]
            if price_max is not None:
                qs["max_price"] = [str(price_max)]
            if brand:
                qs["brand"] = [str(brand)]
            if rating is not None:
                qs["rating_min"] = [str(rating)]

        new_query = urllib.parse.urlencode(qs, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))


class DirectoryStrategy(BaseStrategy):
    def get_extraction_schema(self) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "name": "",
                        "category": "",
                        "phone": "",
                        "email": "",
                        "address": "",
                        "website": "",
                        "rating": "",
                        "url": "",
                    }
                ]
            }
        )


class ArticleStrategy(BaseStrategy):
    def get_extraction_schema(self) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "title": "",
                        "author": "",
                        "published_at": "",
                        "summary": "",
                        "url": "",
                    }
                ]
            }
        )


class DashboardStrategy(BaseStrategy):
    def get_extraction_schema(self) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "metric": "",
                        "value": "",
                        "period": "",
                        "source": "",
                    }
                ]
            }
        )


class StrategyFactory:
    @classmethod
    def get_strategy(cls, site_type: SiteType, page: Page) -> BaseStrategy:
        if site_type == SiteType.ECOMMERCE:
            return EcommerceStrategy(page)
        if site_type == SiteType.DIRECTORY:
            return DirectoryStrategy(page)
        if site_type == SiteType.ARTICLE:
            return ArticleStrategy(page)
        if site_type == SiteType.DASHBOARD:
            return DashboardStrategy(page)
        return BaseStrategy(page)
