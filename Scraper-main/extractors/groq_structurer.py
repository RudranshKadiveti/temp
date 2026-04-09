from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from utils.cache import ContentHashCache
from utils.logger import setup_logger

logger = setup_logger(__name__)


class GroqNameStructurer:
    """Batch product-name structuring via Groq's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.cache = ContentHashCache()

    async def structure_product_names(self, names: list[str]) -> list[dict[str, Any]]:
        cleaned = [name.strip() for name in names if isinstance(name, str) and name.strip()]
        if not cleaned:
            return []

        # Keep order while deduplicating.
        deduped = list(dict.fromkeys(cleaned))
        cache_key = ContentHashCache.digest("|".join(deduped))
        cached = self.cache.get("groq_names", cache_key)
        if isinstance(cached, list):
            return [row for row in cached if isinstance(row, dict)]

        system_prompt = (
            "You are a product catalog normalizer. "
            "Return JSON only with key 'records'. "
            "Each record must contain: source_name, normalized_name, brand, product_type."
        )
        user_prompt = (
            "Normalize and structure this product-name list. "
            "Preserve one output record per input item.\n"
            f"INPUT_NAMES={json.dumps(deduped, ensure_ascii=False)}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=1200,
            )
            content = response.choices[0].message.content
            if not content:
                return []

            payload = json.loads(content)
            records = payload.get("records", []) if isinstance(payload, dict) else []
            output = [row for row in records if isinstance(row, dict)]
            self.cache.set("groq_names", cache_key, output)
            return output
        except Exception as exc:  # noqa: BLE001
            logger.error("Groq structuring failed: %s", exc)
            return []
