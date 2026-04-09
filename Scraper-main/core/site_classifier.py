from __future__ import annotations

from playwright.async_api import Page

from core.models import SiteType


class SiteClassifier:
    @staticmethod
    async def classify(url: str, page: Page | None = None) -> SiteType:
        u = url.lower()
        if any(x in u for x in ["amazon", "flipkart", "ebay", "shop", "store", "product"]):
            return SiteType.ECOMMERCE
        if any(x in u for x in ["directory", "listing", "catalog", "yellowpages", "yelp"]):
            return SiteType.DIRECTORY
        if any(x in u for x in ["blog", "article", "news", "medium", "post"]):
            return SiteType.ARTICLE
        if any(x in u for x in ["dashboard", "analytics", "admin", "app."]):
            return SiteType.DASHBOARD

        if page is None:
            return SiteType.UNKNOWN

        signals = await page.evaluate(
            """
            () => {
              const body = document.body?.innerText || '';
              const cards = document.querySelectorAll('article, [class*=card], [class*=item], li').length;
              const tables = document.querySelectorAll('table').length;
              const forms = document.querySelectorAll('form, input, [role=grid]').length;
              return {
                hasPrice: /[$€£₹]|price|add to cart|buy now/i.test(body),
                hasArticle: /author|published|read more|newsletter/i.test(body),
                cards,
                tables,
                forms,
              };
            }
            """
        )

        if signals.get("hasPrice"):
            return SiteType.ECOMMERCE
        if signals.get("hasArticle"):
            return SiteType.ARTICLE
        if signals.get("tables", 0) > 2 or signals.get("forms", 0) > 8:
            return SiteType.DASHBOARD
        if signals.get("cards", 0) > 12:
            return SiteType.DIRECTORY
        return SiteType.UNKNOWN
