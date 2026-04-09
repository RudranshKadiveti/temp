from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SiteType(str, Enum):
    ECOMMERCE = "ecommerce"
    DIRECTORY = "directory"
    ARTICLE = "article"
    DASHBOARD = "dashboard"
    UNKNOWN = "unknown"


@dataclass
class FilterConfig:
    query: str = ""
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    brand: Optional[str] = None
    min_rating: Optional[float] = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class RuntimeConfig:
    url: str
    max_pages: int = 10
    concurrency: int = 4
    output_format: str = "csv"
    output_dir: Path = Path("data/output")
    llm_enabled: bool = True
    max_retries: int = 3
    headless: bool = True
    persist_session: bool = True
    debug_snapshots: bool = False
    filters: FilterConfig = field(default_factory=FilterConfig)


@dataclass
class MetricsSnapshot:
    pages_visited: int = 0
    records_emitted: int = 0
    llm_calls: int = 0
    dom_batches: int = 0
    fallback_batches: int = 0
    api_batches: int = 0
    errors: int = 0


Record = Dict[str, Any]
Schema = Dict[str, Any]
