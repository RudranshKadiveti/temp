from __future__ import annotations

import json
import os
import re
from typing import Any

import tiktoken
from openai import AsyncOpenAI

from utils.cache import ContentHashCache
from utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMFallbackExtractor:
    """Layer 3 fallback extractor with aggressive caching and strict schema output."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", max_tokens: int = 800):
        self.model = model or os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

        # OpenRouter keys (sk-or-v1...) must use OpenRouter's OpenAI-compatible endpoint.
        base_url = os.getenv("OPENROUTER_BASE_URL")
        if not base_url and api_key.startswith("sk-or-v1"):
            base_url = "https://openrouter.ai/api/v1"

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)
        self.max_tokens = max_tokens
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        self.cache = ContentHashCache()

    def _truncate_with_token_awareness(self, text: str, limit: int = 5000) -> str:
        encoded = self.encoding.encode(text)
        if len(encoded) <= limit:
            return text
        logger.info("LLM fallback payload trimmed from %s to %s tokens", len(encoded), limit)
        return self.encoding.decode(encoded[:limit])

    @staticmethod
    def _extract_price_and_currency(text: str) -> tuple[float | None, str | None]:
        if not text:
            return None, None

        m = re.search(r"([$€£₹]|usd|eur|gbp|inr|rs\.?)(?:\s*)([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if not m:
            return None, None

        currency_token = m.group(1).upper().replace("RS.", "INR").replace("RS", "INR")
        if currency_token == "$":
            currency = "USD"
        elif currency_token == "€":
            currency = "EUR"
        elif currency_token == "£":
            currency = "GBP"
        elif currency_token == "₹":
            currency = "INR"
        else:
            currency = currency_token

        try:
            price = float(m.group(2).replace(",", ""))
        except ValueError:
            price = None
        return price, currency

    def _fallback_single_record(self, raw_html: str) -> list[dict[str, Any]]:
        # Fail-safe extraction from visible text hints when model output is empty.
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []

        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
        heading_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, flags=re.IGNORECASE | re.DOTALL)
        raw_name = ""
        if heading_match:
            raw_name = re.sub(r"<[^>]+>", " ", heading_match.group(1))
        elif title_match:
            raw_name = re.sub(r"<[^>]+>", " ", title_match.group(1))
        else:
            raw_name = text[:120]

        raw_name = re.sub(r"\s+", " ", raw_name).strip(" -|:")
        price, currency = self._extract_price_and_currency(text)

        row = {
            "name": raw_name,
            "description": None,
            "price": price,
            "currency": currency,
            "rating": None,
            "reviews_count": None,
            "availability": None,
            "url": None,
            "image_url": None,
        }
        fixed = self._normalize_product_record(row)
        return [fixed] if fixed.get("name") else []

    def _normalize_product_record(self, record: dict[str, Any]) -> dict[str, Any]:
        out = dict(record)
        out = self._enforce_name_description_split(out)

        # Enforce strict output keys and null semantics for missing data.
        def _to_float(value: Any) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(str(value).replace(",", "").strip())
            except ValueError:
                return None

        def _to_int(value: Any) -> int | None:
            f = _to_float(value)
            if f is None:
                return None
            return int(round(f))

        return {
            "name": (out.get("name") or "").strip(),
            "description": out.get("description"),
            "price": _to_float(out.get("price")),
            "currency": (str(out.get("currency")).strip().upper() if out.get("currency") not in (None, "") else None),
            "rating": _to_float(out.get("rating")),
            "reviews_count": _to_int(out.get("reviews_count")),
            "availability": (str(out.get("availability")).strip() if out.get("availability") not in (None, "") else None),
            "url": (str(out.get("url")).strip() if out.get("url") not in (None, "") else None),
            "image_url": (str(out.get("image_url")).strip() if out.get("image_url") not in (None, "") else None),
        }

    @staticmethod
    def _enforce_name_description_split(record: dict[str, Any]) -> dict[str, Any]:
        # Keep records deterministic even if the model drifts from instructions.
        out = dict(record)
        name = str(out.get("name") or "").strip()
        description = str(out.get("description") or "").strip()

        def _norm_text(value: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", value.lower())).strip()

        def _strip_name_prefix(name_text: str, desc_text: str) -> str:
            if not name_text or not desc_text:
                return desc_text

            n_norm = _norm_text(name_text)
            d_norm = _norm_text(desc_text)
            if not n_norm or not d_norm:
                return desc_text

            # Exact duplicate or prefixed duplicate.
            if d_norm == n_norm:
                return ""
            if d_norm.startswith(n_norm + " "):
                raw = re.sub(rf"^\s*{re.escape(name_text)}\s*[-:|,]*\s*", "", desc_text, flags=re.IGNORECASE)
                return raw.strip()

            # Token-overlap guard when description starts with mostly identical phrase.
            n_tokens = [t for t in n_norm.split() if t]
            d_tokens = [t for t in d_norm.split() if t]
            if not n_tokens or not d_tokens:
                return desc_text

            prefix = d_tokens[: len(n_tokens)]
            overlap = len(set(prefix) & set(n_tokens)) / max(1, len(set(n_tokens)))
            if overlap >= 0.75:
                # Drop the first sentence/chunk if it is mostly the product name repeated.
                trimmed = re.sub(r"^[^,.;:|\-]+[,.;:|\-]?\s*", "", desc_text).strip()
                return trimmed

            return desc_text

        if not name and description:
            # Fallback: derive a short name from the first words of description.
            name = " ".join(description.split()[:12]).strip()

        if name:
            words = name.split()
            if len(words) > 12:
                name = " ".join(words[:12]).strip()

        if description and name:
            description = _strip_name_prefix(name, description)
            if _norm_text(description) == _norm_text(name):
                description = ""

        out["name"] = name
        out["description"] = description or None
        return out

    def _build_prompts(self, site_type: str, schema: str, compact_input: str) -> tuple[str, str]:
        del schema  # Product fallback enforces a resilient fixed schema for cross-site consistency.
        system_prompt = (
            "You are a resilient cross-website product extraction engine. "
            "Return ONLY valid JSON array; no prose, no markdown."
        )
        user_prompt = (
            "Extract structured product records even from messy or unfamiliar HTML.\n\n"
            "Output must be a strict JSON array where each item contains exactly:\n"
            "name, description, price, currency, rating, reviews_count, availability, url, image_url.\n\n"
            "Rules:\n"
            "1) Never return empty array if any product-like item exists.\n"
            "2) Prioritize recall over precision; partial records allowed; missing fields must be null.\n"
            "3) Do not hallucinate; extract only visible HTML evidence.\n"
            "4) name must be short (8-12 words max) and product-identifying.\n"
            "5) description must contain remaining details and must not duplicate full name text.\n"
            "6) If only one product-like item is visible, return one record.\n"
            "7) If no clear list exists, extract any product-like entity from headings/anchors/text blocks.\n\n"
            f"SITE_TYPE={site_type}\n"
            "HTML:\n"
            f"{compact_input}"
        )
        return system_prompt, user_prompt

    async def extract_structured(self, raw_html: str, schema: str, site_type: str = "unknown") -> list[dict[str, Any]]:
        compact_input = self._truncate_with_token_awareness(raw_html)
        cache_key = ContentHashCache.digest(f"{site_type}|{schema}|{compact_input}")
        cached = self.cache.get("llm", cache_key)
        if cached is not None:
            return [row for row in cached if isinstance(row, dict)]

        system_prompt, user_prompt = self._build_prompts(site_type, schema, compact_input)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=0,
            )
            content = response.choices[0].message.content
            if not content:
                rows = self._fallback_single_record(raw_html)
                self.cache.set("llm", cache_key, rows)
                return rows

            parsed = json.loads(content)
            if isinstance(parsed, dict):
                records = parsed.get("records", [])
            elif isinstance(parsed, list):
                records = parsed
            else:
                records = []

            rows = [self._normalize_product_record(row) for row in records if isinstance(row, dict)]
            rows = [row for row in rows if row.get("name")]
            if not rows:
                rows = self._fallback_single_record(raw_html)
            self.cache.set("llm", cache_key, rows)
            return rows
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM fallback failed: %s", exc)
            return self._fallback_single_record(raw_html)
