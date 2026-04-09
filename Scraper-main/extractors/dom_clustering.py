from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page


class DOMClusteringExtractor:
    """Layer 1: fast repeated-pattern extraction with zero LLM cost."""

    def __init__(self, page: Page):
        self.page = page

    def _parse_availability(self, text: str) -> str:
      t = (text or "").strip().lower()
      if not t:
        return ""

      # Check negative intent first so phrases like "not available" are not treated as available.
      if re.search(
        r"\b(out\s+of\s+stock|outofstock|sold\s+out|unavailable|currently\s+unavailable|temporarily\s+unavailable|not\s+available)\b",
        t,
        re.IGNORECASE,
      ):
        return "out of stock"

      if re.search(
        r"\b(in\s+stock|instock|available\s+now|available\s+for\s+delivery|ready\s+to\s+ship|available)\b",
        t,
        re.IGNORECASE,
      ):
        return "in stock"

      # Unknown should remain empty instead of defaulting to out of stock.
      return ""

    async def extract_patterns(self, site_type: str = "unknown") -> list[dict[str, Any]]:
        js_code = """
        () => {
          const EXCLUDE = new Set(['SCRIPT','STYLE','HEADER','FOOTER','NAV','NOSCRIPT','SVG','HEAD','META','LINK','IFRAME']);
          const containers = Array.from(document.querySelectorAll('main, section, div, ul, ol, table, tbody'));

          function cleanText(t) {
            return (t || '').replace(/\\s+/g, ' ').trim();
          }

          function getNodeScore(el) {
            const text = cleanText(el.innerText || '');
            const links = el.querySelectorAll('a').length;
            const images = el.querySelectorAll('img').length;
            const priceHints = (text.match(/[$€£₹]|price|sale|discount/gi) || []).length;
            return (links * 2) + (images * 2) + (priceHints * 3) + Math.min(text.length / 120, 12);
          }

          const groups = [];
          for (const parent of containers) {
            const children = Array.from(parent.children).filter(c => {
              if (EXCLUDE.has(c.tagName)) return false;
              const st = window.getComputedStyle(c);
              if (st.display === 'none' || st.visibility === 'hidden') return false;
              return cleanText(c.innerText || '').length > 24;
            });

            if (children.length < 3) continue;
            const score = children.reduce((acc, c) => acc + getNodeScore(c), 0) / children.length;
            if (score < 2.0) continue;

            groups.push({ parent, children, score });
          }

          groups.sort((a, b) => b.score - a.score);
          const selected = groups.slice(0, 4);
          const rows = [];

          for (const group of selected) {
            for (const child of group.children) {
              const text = cleanText(child.innerText || '');
              const anchors = Array.from(child.querySelectorAll('a')).map(a => a.href).filter(Boolean).slice(0, 6);
              const images = Array.from(child.querySelectorAll('img')).map(i => i.currentSrc || i.src || i.dataset?.src).filter(Boolean).slice(0, 4);
              const tableCells = Array.from(child.querySelectorAll('td, th')).map(c => cleanText(c.innerText || '')).filter(Boolean);
              const nameHint = cleanText((child.querySelector('h1,h2,h3,h4,strong,[class*=title],[data-testid*=title],a') || {}).innerText || '');

              rows.push({
                name_hint: nameHint,
                full_text: text,
                links: anchors,
                images,
                table_cells: tableCells,
              });
            }
          }

          return rows;
        }
        """
        result = await self.page.evaluate(js_code)
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    def parse_item(self, raw_item: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        text = str(raw_item.get("full_text", ""))
        lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]

        output: dict[str, Any] = {}
        for field in schema.keys():
            key = field.lower()
            if key == "name":
                hint = str(raw_item.get("name_hint") or "").strip()
                output[field] = hint or (lines[0][:220] if lines else "")
            elif key in {"price", "discount"}:
                m = re.search(r"(?:[$€£₹]|usd|eur|inr|rs\.?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.IGNORECASE)
                output[field] = m.group(1).replace(",", "") if m else ""
            elif key == "currency":
                m = re.search(r"([$€£₹]|usd|eur|inr)", text, re.IGNORECASE)
                output[field] = (m.group(1).upper() if m else "")
            elif key in {"rating", "reviews"}:
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:out of 5|stars?|ratings?|reviews?)", text, re.IGNORECASE)
                output[field] = m.group(1) if m else ""
            elif key in {"availability", "in_stock"}:
              output[field] = self._parse_availability(text)
            elif key in {"url", "link"}:
                links = raw_item.get("links") or []
                output[field] = links[0] if links else ""
            elif key in {"image", "image_url"}:
                images = raw_item.get("images") or []
                output[field] = images[0] if images else ""
            else:
                output[field] = ""

        return output
