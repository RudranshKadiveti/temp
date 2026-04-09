from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse


SOURCE_WEIGHTS: dict[str, float] = {
    "json_ld": 0.98,
    "microdata": 0.9,
    "meta": 0.8,
    "dom": 0.72,
    "regex": 0.58,
}

FIELD_WEIGHTS: dict[str, float] = {
    "name": 0.25,
    "price": 0.22,
    "currency": 0.08,
    "rating": 0.12,
    "reviews_count": 0.1,
    "availability": 0.08,
    "url": 0.1,
    "image_url": 0.05,
}


@dataclass
class FieldResult:
    value: Any
    confidence: float
    source: str


class FieldExtractionEngine:
    """Deterministic field-level extraction with per-field confidence and source trace."""

    def _clean_text(self, value: Any) -> str:
        text = "" if value is None else str(value)
        text = unescape(text)
        text = text.replace("\u00a0", " ").replace("\r", " ").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _normalize_availability(self, value: Any) -> str | None:
        t = self._clean_text(value).lower()
        if not t:
            return None

        # Prioritize negative patterns to avoid false positives from words like "unavailable".
        if re.search(
            r"\b(out\s+of\s+stock|outofstock|sold\s+out|unavailable|currently\s+unavailable|temporarily\s+unavailable|not\s+available)\b",
            t,
        ):
            return "Out of Stock"

        if re.search(
            r"\b(in\s+stock|instock|available\s+now|available\s+for\s+delivery|ready\s+to\s+ship|available)\b",
            t,
        ):
            return "In Stock"

        return None

    def _extract_json_ld_blocks(self, html: str) -> list[dict[str, Any]]:
        blocks = re.findall(
            r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        out: list[dict[str, Any]] = []
        for block in blocks:
            raw = block.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            out.extend(self._flatten_json_ld(parsed))
        return out

    def _flatten_json_ld(self, node: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if isinstance(node, list):
            for item in node:
                items.extend(self._flatten_json_ld(item))
            return items

        if not isinstance(node, dict):
            return items

        if "@graph" in node and isinstance(node.get("@graph"), list):
            items.extend(self._flatten_json_ld(node["@graph"]))

        items.append(node)
        return items

    def _meta_map(self, html: str) -> dict[str, str]:
        pairs = re.findall(
            r"<meta[^>]+(?:property|name)=[\"']([^\"']+)[\"'][^>]+content=[\"']([^\"']*)[\"'][^>]*>",
            html,
            flags=re.IGNORECASE,
        )
        result: dict[str, str] = {}
        for k, v in pairs:
            key = self._clean_text(k).lower()
            if key and key not in result:
                result[key] = self._clean_text(v)
        return result

    def _currency_from_text(self, text: str) -> str | None:
        t = text.lower()
        if "₹" in text or " inr" in f" {t} " or " rs" in f" {t} ":
            return "INR"
        if "$" in text or " usd" in f" {t} ":
            return "USD"
        if "€" in text or " eur" in f" {t} ":
            return "EUR"
        if "£" in text or " gbp" in f" {t} ":
            return "GBP"
        return None

    def _to_float(self, value: Any) -> float | None:
        text = self._clean_text(value)
        if not text:
            return None
        m = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    def _to_int(self, value: Any) -> int | None:
        f = self._to_float(value)
        if f is None:
            return None
        return int(round(f))

    def _pick_best(self, field: str, candidates: list[FieldResult]) -> FieldResult:
        if not candidates:
            return FieldResult(value=None, confidence=0.0, source="missing")

        # Consistency bonus for repeated values across different sources.
        occurrences: dict[str, int] = {}
        for c in candidates:
            key = self._clean_text(c.value)
            if key:
                occurrences[key] = occurrences.get(key, 0) + 1

        scored: list[tuple[float, FieldResult]] = []
        for c in candidates:
            key = self._clean_text(c.value)
            consistency = 0.04 * max(0, occurrences.get(key, 1) - 1)
            score = min(1.0, max(0.0, c.confidence + consistency))
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        return FieldResult(value=best.value, confidence=best_score, source=best.source)

    def extract_name(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []
        for key, source in [
            ("name", "json_ld"),
            ("title", "json_ld"),
            ("headline", "json_ld"),
            ("name_hint", "dom"),
        ]:
            value = self._clean_text(payload.get(key))
            if value and len(value) >= 4:
                conf = SOURCE_WEIGHTS.get(source, 0.6)
                if len(value) > 140:
                    conf -= 0.12
                candidates.append(FieldResult(value=value, confidence=conf, source=source))

        if not candidates and text:
            lines = [self._clean_text(x) for x in re.split(r"[\n\r]+", text) if self._clean_text(x)]
            if lines:
                candidates.append(FieldResult(value=lines[0][:180], confidence=SOURCE_WEIGHTS["regex"], source="regex"))

        return self._pick_best("name", candidates)

    def extract_price(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []

        offers = payload.get("offers")
        if isinstance(offers, dict):
            for key in ("price", "lowPrice", "highPrice"):
                value = self._to_float(offers.get(key))
                if value is not None and value > 0:
                    candidates.append(FieldResult(value=value, confidence=SOURCE_WEIGHTS["json_ld"], source="json_ld"))

        for key, source in [("price", "json_ld"), ("discount", "dom")]:
            value = self._to_float(payload.get(key))
            if value is not None and value > 0:
                candidates.append(FieldResult(value=value, confidence=SOURCE_WEIGHTS.get(source, 0.6), source=source))

        if text:
            m = re.search(
                r"(?:₹|rs\.?|inr|\$|usd|eur|price|m\.r\.p)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                try:
                    value = float(m.group(1).replace(",", ""))
                    if value > 0:
                        candidates.append(FieldResult(value=value, confidence=SOURCE_WEIGHTS["regex"], source="regex"))
                except ValueError:
                    pass

        return self._pick_best("price", candidates)

    def extract_currency(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []
        offers = payload.get("offers")
        if isinstance(offers, dict):
            cur = self._clean_text(offers.get("priceCurrency"))
            if cur:
                candidates.append(FieldResult(value=cur.upper(), confidence=SOURCE_WEIGHTS["json_ld"], source="json_ld"))

        for key, source in [("currency", "dom")]:
            cur = self._clean_text(payload.get(key))
            if cur:
                candidates.append(FieldResult(value=cur.upper(), confidence=SOURCE_WEIGHTS[source], source=source))

        from_text = self._currency_from_text(text)
        if from_text:
            candidates.append(FieldResult(value=from_text, confidence=SOURCE_WEIGHTS["regex"], source="regex"))

        return self._pick_best("currency", candidates)

    def extract_rating(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []
        agg = payload.get("aggregateRating")
        if isinstance(agg, dict):
            v = self._to_float(agg.get("ratingValue"))
            if v is not None:
                candidates.append(FieldResult(value=v, confidence=SOURCE_WEIGHTS["json_ld"], source="json_ld"))

        v_dom = self._to_float(payload.get("rating") or payload.get("stars"))
        if v_dom is not None:
            candidates.append(FieldResult(value=v_dom, confidence=SOURCE_WEIGHTS["dom"], source="dom"))

        m = re.search(r"([0-5](?:\.[0-9])?)\s*(?:out of 5|stars?)", text, flags=re.IGNORECASE)
        if m:
            try:
                v_regex = float(m.group(1))
                candidates.append(FieldResult(value=v_regex, confidence=SOURCE_WEIGHTS["regex"], source="regex"))
            except ValueError:
                pass

        return self._pick_best("rating", candidates)

    def extract_reviews(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []
        agg = payload.get("aggregateRating")
        if isinstance(agg, dict):
            v = self._to_int(agg.get("reviewCount") or agg.get("ratingCount"))
            if v is not None:
                candidates.append(FieldResult(value=v, confidence=SOURCE_WEIGHTS["json_ld"], source="json_ld"))

        v_dom = self._to_int(payload.get("reviews") or payload.get("reviews_count"))
        if v_dom is not None:
            # Avoid treating copied rating values as review counts.
            rating_val = self._to_float(payload.get("rating"))
            if rating_val is None or abs(float(v_dom) - rating_val) > 1:
                candidates.append(FieldResult(value=v_dom, confidence=SOURCE_WEIGHTS["dom"], source="dom"))

        m = re.search(r"\((\d[\d,\.Kk]+)\)", text)
        if m:
            token = m.group(1).upper().replace(",", "")
            if token.endswith("K"):
                try:
                    candidates.append(
                        FieldResult(value=int(float(token[:-1]) * 1000), confidence=SOURCE_WEIGHTS["regex"], source="regex")
                    )
                except ValueError:
                    pass
            else:
                v = self._to_int(token)
                if v is not None:
                    candidates.append(FieldResult(value=v, confidence=SOURCE_WEIGHTS["regex"], source="regex"))

        return self._pick_best("reviews_count", candidates)

    def extract_availability(self, payload: dict[str, Any], text: str) -> FieldResult:
        candidates: list[FieldResult] = []
        offers = payload.get("offers")
        if isinstance(offers, dict):
            avail = self._normalize_availability(offers.get("availability"))
            if avail:
                candidates.append(FieldResult(value=avail, confidence=SOURCE_WEIGHTS["json_ld"], source="json_ld"))

        dom_avail = self._normalize_availability(payload.get("availability") or payload.get("in_stock"))
        if dom_avail:
            candidates.append(FieldResult(value=dom_avail, confidence=SOURCE_WEIGHTS["dom"], source="dom"))

        text_avail = self._normalize_availability(text)
        if text_avail:
            candidates.append(FieldResult(value=text_avail, confidence=SOURCE_WEIGHTS["regex"], source="regex"))

        return self._pick_best("availability", candidates)

    def _row_confidence(self, fields: dict[str, FieldResult]) -> float:
        weighted = 0.0
        total = 0.0
        for field, weight in FIELD_WEIGHTS.items():
            total += weight
            weighted += weight * fields.get(field, FieldResult(None, 0.0, "missing")).confidence
        if total <= 0:
            return 0.0
        return round(weighted / total, 4)

    def _build_row(self, payload: dict[str, Any], page_url: str, fallback_text: str, source_tag: str) -> dict[str, Any]:
        text = self._clean_text(payload.get("full_text") or fallback_text)

        name = self.extract_name(payload, text)
        price = self.extract_price(payload, text)
        currency = self.extract_currency(payload, text)
        rating = self.extract_rating(payload, text)
        reviews = self.extract_reviews(payload, text)
        availability = self.extract_availability(payload, text)

        url = self._clean_text(payload.get("url") or payload.get("link") or page_url)
        image_url = self._clean_text(payload.get("image_url") or payload.get("image"))

        field_trace = {
            "name": name.source,
            "price": price.source,
            "currency": currency.source,
            "rating": rating.source,
            "reviews_count": reviews.source,
            "availability": availability.source,
            "url": "dom" if payload.get("url") else "page",
            "image_url": "dom" if image_url else "missing",
        }

        fields: dict[str, FieldResult] = {
            "name": name,
            "price": price,
            "currency": currency,
            "rating": rating,
            "reviews_count": reviews,
            "availability": availability,
            "url": FieldResult(url, SOURCE_WEIGHTS.get("dom", 0.72), "dom"),
            "image_url": FieldResult(image_url, SOURCE_WEIGHTS.get("dom", 0.72) if image_url else 0.0, "dom"),
        }

        confidence = self._row_confidence(fields)
        return {
            "name": name.value,
            "price": price.value,
            "currency": currency.value,
            "rating": rating.value,
            "reviews_count": reviews.value,
            "availability": availability.value,
            "url": url,
            "image_url": image_url,
            "source": source_tag,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "confidence": confidence,
            "_field_sources": field_trace,
        }

    def extract_from_html(self, html: str, page_url: str, site_type: str) -> list[dict[str, Any]]:
        if site_type != "ecommerce":
            return []

        text_only = self._clean_text(re.sub(r"<[^>]+>", " ", html))
        meta = self._meta_map(html)
        json_ld_nodes = self._extract_json_ld_blocks(html)

        rows: list[dict[str, Any]] = []
        for node in json_ld_nodes:
            node_type = self._clean_text(node.get("@type")).lower()
            if node_type and "product" not in node_type:
                continue
            rows.append(self._build_row(node, page_url, text_only, "json_ld"))

        # Use metadata fallback only when structured data is missing.
        if not rows and meta:
            meta_payload = {
                "name": meta.get("og:title") or meta.get("twitter:title") or meta.get("title"),
                "image_url": meta.get("og:image") or meta.get("twitter:image"),
                "price": meta.get("product:price:amount") or meta.get("og:price:amount"),
                "currency": meta.get("product:price:currency") or meta.get("og:price:currency"),
                "url": meta.get("og:url") or page_url,
            }
            rows.append(self._build_row(meta_payload, page_url, text_only, "meta"))

        # Deterministic order keeps exports stable.
        rows.sort(key=lambda r: (self._clean_text(r.get("name")), self._clean_text(r.get("url"))))
        return rows

    def refine_dom_records(self, records: list[dict[str, Any]], page_url: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for record in records:
            out.append(self._build_row(record, page_url, self._clean_text(record.get("full_text")), "dom"))
        return out

    def domain_name(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return "unknown"
