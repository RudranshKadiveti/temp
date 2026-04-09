from __future__ import annotations

from typing import Any


class HeuristicRuleEngine:
    """Layer 2: group candidate elements into list, cards, grids, or table records."""

    def detect_layout(self, candidates: list[dict[str, Any]]) -> str:
        if not candidates:
            return "unknown"

        table_like = sum(1 for c in candidates if c.get("table_cells"))
        image_like = sum(1 for c in candidates if c.get("images"))
        link_like = sum(1 for c in candidates if c.get("links"))

        if table_like > len(candidates) * 0.4:
            return "table"
        if image_like > len(candidates) * 0.5 and link_like > len(candidates) * 0.4:
            return "cards"
        if link_like > len(candidates) * 0.6:
            return "list"
        return "mixed"

    def score_record(self, record: dict[str, Any]) -> float:
        text = (record.get("full_text") or "").lower()
        score = 0.0
        if any(token in text for token in ["$", "₹", "price", "in stock", "rating"]):
            score += 1.5
        if record.get("name_hint"):
            score += 0.7
        if record.get("links"):
            score += 0.6
        if record.get("images"):
            score += 0.4
        return score

    def select_top_records(self, candidates: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
        ranked = sorted(candidates, key=self.score_record, reverse=True)
        return ranked[:limit]
