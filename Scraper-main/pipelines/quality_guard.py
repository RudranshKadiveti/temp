from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, ValidationError


CANONICAL_COLUMNS = [
    "name",
    "description",
    "price",
    "currency",
    "rating",
    "reviews_count",
    "availability",
    "url",
    "image_url",
    "source",
    "scraped_at",
    "confidence",
]


class CanonicalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    availability: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    scraped_at: Optional[datetime] = None
    confidence: Optional[float] = None


class QualityGuard:
    """Strict validation + normalization + quality metrics for canonical output."""

    def __init__(self, output_dir: Path, min_confidence: float = 0.45):
        self.output_dir = output_dir
        self.min_confidence = min_confidence
        self.failed_rows_path = self.output_dir / "failed_rows.json"
        self.report_path = self.output_dir / "extraction_report.json"
        self.sample_path = self.output_dir / "clean_sample.json"

        self.total_seen = 0
        self.total_valid = 0
        self.total_dropped = 0
        self.total_duplicates = 0
        self.confidence_sum = 0.0
        self.null_field_counts: dict[str, int] = {k: 0 for k in CANONICAL_COLUMNS if k != "confidence"}

    def _clean_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value)
        replacements = {
            "\u00a0": " ",
            "â‚¹": "₹",
            "â€": "-",
            "â€“": "-",
            "â€”": "-",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        text = " ".join(text.split()).strip()
        return text or None

    def _to_float(self, value: Any) -> Optional[float]:
        text = self._clean_text(value)
        if not text:
            return None
        buf = ""
        saw_digit = False
        for ch in text:
            if ch.isdigit() or ch in {".", ","}:
                buf += ch
                if ch.isdigit():
                    saw_digit = True
        if not saw_digit:
            return None
        buf = buf.replace(",", "")
        try:
            return float(buf)
        except ValueError:
            return None

    def _to_int(self, value: Any) -> Optional[int]:
        f = self._to_float(value)
        if f is None:
            return None
        return int(round(f))

    def _normalize_currency(self, value: Any, raw_text: str = "") -> Optional[str]:
        v = (self._clean_text(value) or "").upper()
        t = raw_text.upper()
        if v in {"INR", "USD", "EUR", "GBP"}:
            return v
        if "₹" in raw_text or "INR" in t or " RS" in f" {t} ":
            return "INR"
        if "$" in raw_text or "USD" in t:
            return "USD"
        if "€" in raw_text or "EUR" in t:
            return "EUR"
        if "£" in raw_text or "GBP" in t:
            return "GBP"
        return None

    def _normalize_availability(self, value: Any) -> Optional[str]:
        t = (self._clean_text(value) or "").lower()
        if not t:
            return None

        # Evaluate negative phrases first so "unavailable" is never treated as "available".
        if any(
            x in t
            for x in [
                "out of stock",
                "outofstock",
                "unavailable",
                "currently unavailable",
                "temporarily unavailable",
                "not available",
                "sold out",
            ]
        ):
            return "Out of Stock"

        if any(
            x in t
            for x in [
                "in stock",
                "instock",
                "available now",
                "available for delivery",
                "ready to ship",
                "available",
            ]
        ):
            return "In Stock"
        return None

    def _clean_name(self, name: Any) -> Optional[str]:
        t = self._clean_text(name)
        if not t:
            return None

        # Strip common marketplace noise from mixed title/price/rating strings.
        t = re.sub(r"(?i)^\s*sponsored\s+", "", t)
        t = re.sub(r"(?i)\b\d(?:\.\d)?\s*out of 5 stars.*$", "", t)
        t = re.sub(r"(?i)\bm\.r\.p\s*:\s*[₹$€£]?\s*\d[\d,]*(?:\.\d+)?", "", t)
        t = re.sub(r"[₹$€£]\s*\d[\d,]*(?:\.\d+)?", "", t)
        t = " ".join(t.split()).strip(" -|:;")

        junk = [
            "sponsored",
            "limited time deal",
            "related searches",
            "need help",
            "results",
            "about amazon",
            "conditions of use",
        ]
        low = t.lower()
        if any(j in low for j in junk):
            return None
        digit_ratio = sum(1 for c in t if c.isdigit()) / max(1, len(t))
        if digit_ratio > 0.65:
            return None
        if t.startswith(("₹", "$", "EUR", "USD", "INR")):
            return None
        token_count = len([x for x in t.split(" ") if x])
        if token_count < 1:
            return None
        if len(t) < 3:
            return None
        return t

    def _record_key(self, row: dict[str, Any]) -> str:
        url = (row.get("url") or "").strip().lower()
        if url:
            material = f"url:{url}"
        else:
            material = f"np:{(row.get('name') or '').strip().lower()}|{row.get('price')}"
        return hashlib.sha256(material.encode("utf-8", errors="ignore")).hexdigest()

    def _normalize_row(self, raw: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        price_raw = raw.get("price") or raw.get("discount")
        rating_raw = raw.get("rating")
        reviews_raw = raw.get("reviews_count") or raw.get("reviews")

        name = self._clean_name(raw.get("name") or raw.get("title") or raw.get("product_name"))
        price = self._to_float(price_raw)
        rating = self._to_float(rating_raw)
        reviews_count = self._to_int(reviews_raw)
        url = self._clean_text(raw.get("url") or raw.get("link"))

        confidence = self._to_float(raw.get("confidence"))
        if confidence is None:
            # Legacy extractors often omit confidence; infer a baseline from core fields.
            if name and (price is not None or url):
                confidence = 0.75
            elif name:
                confidence = 0.5
            else:
                confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        description = self._clean_text(raw.get("description") or raw.get("specs"))
        if name and description:
            name_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", name.lower())).strip()
            desc_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", description.lower())).strip()
            if desc_norm == name_norm:
                description = None
            elif desc_norm.startswith(name_norm + " "):
                description = re.sub(rf"^\s*{re.escape(name)}\s*[-:|,]*\s*", "", description, flags=re.IGNORECASE).strip() or None

        row = {
            "name": name,
            "description": description,
            "price": price,
            "currency": self._normalize_currency(raw.get("currency"), raw_text=self._clean_text(raw.get("full_text")) or ""),
            "rating": rating,
            "reviews_count": reviews_count,
            "availability": self._normalize_availability(raw.get("availability")),
            "url": url,
            "image_url": self._clean_text(raw.get("image_url") or raw.get("image")),
            "source": self._clean_text(raw.get("source")) or "unknown",
            "scraped_at": self._clean_text(raw.get("scraped_at")) or datetime.now(timezone.utc).isoformat(),
            "confidence": confidence,
        }

        if row["name"] is None:
            return None, "missing_or_invalid_name"
        if row["price"] is None and row["url"] is None:
            return None, "missing_price_and_url"
        if row["confidence"] < self.min_confidence:
            return None, "low_confidence"

        try:
            model = CanonicalRecord(**row)
        except ValidationError as exc:
            return None, f"schema_validation_failed: {exc.errors()[0].get('msg', 'invalid')}"

        normalized = model.model_dump(mode="json")
        return {col: normalized.get(col) for col in CANONICAL_COLUMNS}, None

    def process(self, records: list[dict[str, Any]], seen_hashes: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for raw in records:
            self.total_seen += 1
            norm, reason = self._normalize_row(raw)
            if norm is None:
                self.total_dropped += 1
                failed.append({"reason": reason, "raw": raw})
                continue

            key = self._record_key(norm)
            if key in seen_hashes:
                self.total_duplicates += 1
                continue
            seen_hashes.add(key)

            valid.append(norm)
            self.total_valid += 1
            self.confidence_sum += float(norm.get("confidence") or 0.0)
            for field in self.null_field_counts:
                if norm.get(field) is None:
                    self.null_field_counts[field] += 1

        if failed:
            self._append_failed_rows(failed)

        self._write_sample(valid)
        report = self.current_report()
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        batch_stats = {
            "seen": len(records),
            "valid": len(valid),
            "dropped": len(failed),
            "duplicates": max(0, len(records) - len(valid) - len(failed)),
        }
        return valid, failed, batch_stats

    def _append_failed_rows(self, failed: list[dict[str, Any]]) -> None:
        existing: list[dict[str, Any]] = []
        if self.failed_rows_path.exists():
            try:
                existing = json.loads(self.failed_rows_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.extend(failed)
        # Keep file bounded for operational safety.
        existing = existing[-2000:]
        self.failed_rows_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_sample(self, new_rows: list[dict[str, Any]]) -> None:
        sample: list[dict[str, Any]] = []
        if self.sample_path.exists():
            try:
                loaded = json.loads(self.sample_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    sample = [r for r in loaded if isinstance(r, dict)]
            except Exception:
                sample = []

        for row in new_rows:
            if len(sample) >= 10:
                break
            sample.append(row)

        self.sample_path.write_text(json.dumps(sample[:10], indent=2, ensure_ascii=False), encoding="utf-8")

    def current_report(self) -> dict[str, Any]:
        valid_non_zero = max(1, self.total_valid)
        avg_confidence = round(self.confidence_sum / valid_non_zero, 4)
        null_field_percentage = {
            field: round((count / valid_non_zero) * 100.0, 2) for field, count in self.null_field_counts.items()
        }
        extraction_success_rate = round((self.total_valid / max(1, self.total_seen)) * 100.0, 2)
        duplicate_rate = round((self.total_duplicates / max(1, self.total_seen)) * 100.0, 2)
        return {
            "total_rows_seen": self.total_seen,
            "valid_rows": self.total_valid,
            "dropped_rows": self.total_dropped,
            "duplicate_rows": self.total_duplicates,
            "extraction_success_rate": extraction_success_rate,
            "avg_confidence_score": avg_confidence,
            "duplicate_rate": duplicate_rate,
            "null_field_percentage": null_field_percentage,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
