from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml

from core.models import FilterConfig, RuntimeConfig


def _to_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_runtime_config(raw: Dict[str, Any]) -> RuntimeConfig:
    filters_raw = raw.get("filters", {})
    filters = FilterConfig(
        query=str(filters_raw.get("query", raw.get("query", ""))),
        price_min=_to_float(filters_raw.get("price_min", raw.get("min_price"))),
        price_max=_to_float(filters_raw.get("price_max", raw.get("max_price"))),
        brand=filters_raw.get("brand"),
        min_rating=_to_float(filters_raw.get("min_rating")),
        keywords=list(filters_raw.get("keywords", [])),
    )
    return RuntimeConfig(
        url=str(raw["url"]),
        max_pages=int(raw.get("max_pages", raw.get("pages", 10))),
        concurrency=int(raw.get("concurrency", 4)),
        output_format=str(raw.get("output_format", raw.get("format", "csv"))).lower(),
        llm_enabled=bool(raw.get("llm_enabled", True)),
        max_retries=int(raw.get("max_retries", 3)),
        headless=bool(raw.get("headless", True)),
        persist_session=bool(raw.get("persist_session", True)),
        debug_snapshots=bool(raw.get("debug_snapshots", False)),
        filters=filters,
    )


def load_runtime_config(config_path: str) -> RuntimeConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Config file must be .yaml, .yml, or .json")

    if "url" not in raw:
        raise ValueError("Config must include 'url'")

    return _build_runtime_config(raw)
