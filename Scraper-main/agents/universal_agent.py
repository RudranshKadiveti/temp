from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

from core.browser_manager import BrowserManager
from core.models import MetricsSnapshot
from core.pagination import SmartPaginator
from core.rate_control import AdaptiveRateController
from core.site_classifier import SiteClassifier
from extractors.dom_clustering import DOMClusteringExtractor
from extractors.field_engine import FieldExtractionEngine
from extractors.groq_structurer import GroqNameStructurer
from extractors.llm_fallback import LLMFallbackExtractor
from extractors.rule_engine import HeuristicRuleEngine
from pipelines.data_stream import DataPipeline
from pipelines.quality_guard import CANONICAL_COLUMNS
from strategies.ecommerce import StrategyFactory
from utils.logger import setup_logger
from utils.snapshots import save_debug_snapshot

logger = setup_logger(__name__)


class UniversalScraperAgent:
    """Universal extraction orchestrator with layered extraction and enterprise controls."""

    def __init__(
        self,
        output_dir: str = "data/output",
        llm_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        groq_model: Optional[str] = None,
    ):
        self.pipeline = DataPipeline(output_dir)
        self.llm_extractor = (
            LLMFallbackExtractor(api_key=llm_api_key, model=llm_model or "gpt-4o-mini") if llm_api_key else None
        )
        self.groq_structurer = (
            GroqNameStructurer(api_key=groq_api_key, model=groq_model or "llama-3.3-70b-versatile")
            if groq_api_key
            else None
        )
        self.metrics = MetricsSnapshot()
        self.rule_engine = HeuristicRuleEngine()
        self.paginator = SmartPaginator()
        self.rate_controller = AdaptiveRateController()
        self.field_engine = FieldExtractionEngine()
        self.domain_pattern_cache: dict[str, dict[str, Any]] = {}

        dynamic_flag = os.getenv("ENABLE_DYNAMIC_MODE", os.getenv("SCRAPER_DYNAMIC_MODE_ENABLED", "1"))
        self.dynamic_mode_enabled = str(dynamic_flag).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        http2_flag = os.getenv("ENABLE_HTTP2_FALLBACK", "1")
        stealth_flag = os.getenv("ENABLE_STEALTH_HEADERS", "1")
        self.http2_fallback_enabled = str(http2_flag).strip().lower() in {"1", "true", "yes", "on"}
        self.stealth_headers_enabled = str(stealth_flag).strip().lower() in {"1", "true", "yes", "on"}
        self.dynamic_wait_timeout_ms = int(os.getenv("SCRAPER_DYNAMIC_MAX_WAIT_MS", "7000"))
        self.dynamic_selector_timeout_ms = int(os.getenv("SCRAPER_DYNAMIC_SELECTOR_TIMEOUT_MS", "3500"))
        self.dynamic_scroll_steps = int(os.getenv("SCRAPER_DYNAMIC_SCROLL_STEPS", "4"))

    async def _structure_names_with_groq(
        self,
        records: list[dict[str, Any]],
        site_type_value: str,
    ) -> list[dict[str, Any]]:
        if site_type_value != "ecommerce" or not self.groq_structurer:
            return records

        names = [str(r.get("name", "")).strip() for r in records]
        names = [n for n in names if n]
        if not names:
            return records

        structured = await self.groq_structurer.structure_product_names(names)
        if not structured:
            return records

        by_source: dict[str, dict[str, Any]] = {}
        for item in structured:
            source_name = str(item.get("source_name", "")).strip().lower()
            if source_name and source_name not in by_source:
                by_source[source_name] = item

        enriched: list[dict[str, Any]] = []
        for record in records:
            key = str(record.get("name", "")).strip().lower()
            groq = by_source.get(key)
            if not groq:
                enriched.append(record)
                continue

            merged = dict(record)
            merged["groq_normalized_name"] = groq.get("normalized_name", "")
            merged["groq_brand"] = groq.get("brand", "")
            merged["groq_product_type"] = groq.get("product_type", "")
            if not merged.get("brand") and merged.get("groq_brand"):
                merged["brand"] = merged["groq_brand"]
            enriched.append(merged)
        return enriched

    async def _extract_via_api_discovery(
        self,
        bm: BrowserManager,
        page,
        schema: dict[str, Any],
        site_type_value: str,
        output_format: str,
        domain_profile: dict[str, Any],
    ) -> int:
        def _is_product_like_record(record: dict[str, Any]) -> bool:
            keys = {str(k).lower() for k in record.keys()}
            has_name = any(k in keys for k in {"name", "title", "product_name", "producttitle"})
            has_price = any(k in keys for k in {"price", "selling_price", "final_price", "mrp", "amount"})
            return has_name or has_price

        def _is_product_like_payload(records: list[dict[str, Any]]) -> bool:
            return any(_is_product_like_record(rec) for rec in records)

        preferred_patterns = set(domain_profile.get("api_patterns", []))

        def _priority(api: dict[str, Any]) -> tuple[int, int]:
            url = str(api.get("url", "")).lower()
            preferred = 0 if any(p and p in url for p in preferred_patterns) else 1
            hinted = 0 if bool(api.get("product_like_hint")) else 1
            return (preferred, hinted)

        processed = 0
        json_apis = [api for api in bm.intercepted_apis if api.get("type") == "JSON_API_FOUND"]
        for api in sorted(json_apis, key=_priority):
            if api.get("type") != "JSON_API_FOUND":
                continue
            records = await bm.fetch_api_payload(page, api.get("url", ""))
            if not records:
                continue
            if site_type_value == "ecommerce" and not _is_product_like_payload(records):
                continue
            constrained = self._constrain_to_schema(records, schema, site_type_value)
            if not constrained:
                continue
            processed += await self.pipeline.process_batch(constrained, format=output_format)
            self.metrics.api_batches += 1
            if processed > 0:
                try:
                    parsed = urlparse(str(api.get("url", "")))
                    path_head = "/".join([seg for seg in parsed.path.split("/") if seg][:2])
                    if path_head:
                        pattern = path_head.lower()
                        existing = list(dict.fromkeys([*domain_profile.get("api_patterns", []), pattern]))
                        domain_profile["api_patterns"] = existing[:8]
                except Exception:
                    pass
                break
        return processed

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = "" if value is None else str(value)
        text = text.replace("\u00a0", " ").replace("\r", " ").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        replacements = {
            "â‚¹": "₹",
            "â€": "-",
            "â€“": "-",
            "â€”": "-",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    @staticmethod
    def _extract_price_number(value: str) -> float | None:
        if not value:
            return None
        m = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", value)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    def _is_valid_ecommerce_record(self, row: dict[str, Any]) -> bool:
        name = self._clean_text(row.get("name", ""))
        price_text = self._clean_text(row.get("price", ""))
        url = self._clean_text(row.get("url", ""))

        if len(name) < 6:
            return False

        junk_tokens = ["limited time deal", "sponsored", "results", "delivery by", "free delivery"]
        lowered = name.lower()
        if any(token in lowered for token in junk_tokens):
            return False

        has_price = self._extract_price_number(price_text) is not None
        has_product_url = url.startswith("http") and ("/dp/" in url or "/gp/" in url or "/product" in url or "/p/" in url)
        return has_price or has_product_url

    def _constrain_to_schema(self, records: list[dict[str, Any]], schema: dict[str, Any], site_type_value: str) -> list[dict[str, Any]]:
        schema_keys = list(dict.fromkeys([*schema.keys(), *CANONICAL_COLUMNS]))
        constrained: list[dict[str, Any]] = []

        for record in records:
            row = {k: self._clean_text(record.get(k, "")) for k in schema_keys}

            # Recover likely key variants.
            if not row.get("name"):
                row["name"] = self._clean_text(record.get("title") or record.get("product_name") or "")
            if "reviews" in row and not row.get("reviews"):
                row["reviews"] = self._clean_text(record.get("reviews_count") or "")
            if "image_url" in row and not row.get("image_url"):
                row["image_url"] = self._clean_text(record.get("image") or "")

            if site_type_value == "ecommerce" and not self._is_valid_ecommerce_record(row):
                continue

            constrained.append(row)

        return constrained

    async def run_task(
        self,
        start_url: str,
        filters: dict[str, Any],
        max_pages: int = 20,
        concurrency: int = 3,
        format: str = "parquet",
        headless: bool = True,
        persist_session: bool = True,
        debug_snapshots: bool = False,
    ) -> dict[str, Any]:
        del concurrency  # Current implementation is page-sequential; interface kept for compatibility.

        async with BrowserManager(
            headless=headless,
            persist_session=persist_session,
            dynamic_mode_enabled=self.dynamic_mode_enabled,
            dynamic_wait_timeout_ms=self.dynamic_wait_timeout_ms,
            dynamic_selector_timeout_ms=self.dynamic_selector_timeout_ms,
            dynamic_scroll_steps=self.dynamic_scroll_steps,
            enable_http2_fallback=self.http2_fallback_enabled,
            enable_stealth_headers=self.stealth_headers_enabled,
        ) as bm:
            context = await bm.create_context()
            page = await context.new_page()
            await bm.watch_network(page)

            boot_start = time.perf_counter()
            nav_ok, page = await bm.navigate_with_retry(page, start_url)
            context = page.context
            logger.info(
                "http2_fallback_used=%s navigation_attempts=%s final_url=%s blocked_detected=%s",
                bm.http2_fallback_used,
                bm.navigation_attempts,
                bm.final_url,
                bm.blocked_detected,
            )
            if not nav_ok or bm.navigation_failed:
                try:
                    await context.close()
                except Exception:
                    pass
                return {
                    "total_records": 0,
                    "pages_visited": 0,
                    "api_discovery_log": bm.intercepted_apis,
                    "metrics": {
                        "records_per_sec": 0,
                        "llm_calls": 0,
                        "dom_batches": 0,
                        "fallback_batches": 0,
                        "api_batches": 0,
                        "errors": 1,
                        "extraction_success_rate": 0,
                        "avg_confidence_score": 0,
                        "duplicate_rate": 0,
                    },
                    "site_type": "unknown",
                    "quality_report": self.pipeline.get_quality_report(),
                    "output_path": "",
                    "error_type": "navigation_blocked",
                    "hint": "likely anti-bot or HTTP2 issue",
                }

            site_type = await SiteClassifier.classify(start_url, page)
            strategy = StrategyFactory.get_strategy(site_type, page)

            filtered_url = await strategy.apply_filters(start_url, filters)
            if filtered_url != start_url:
                nav_ok, page = await bm.navigate_with_retry(page, filtered_url)
                context = page.context
                logger.info(
                    "http2_fallback_used=%s navigation_attempts=%s final_url=%s blocked_detected=%s",
                    bm.http2_fallback_used,
                    bm.navigation_attempts,
                    bm.final_url,
                    bm.blocked_detected,
                )
                if not nav_ok or bm.navigation_failed:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    return {
                        "total_records": 0,
                        "pages_visited": 0,
                        "api_discovery_log": bm.intercepted_apis,
                        "metrics": {
                            "records_per_sec": 0,
                            "llm_calls": 0,
                            "dom_batches": 0,
                            "fallback_batches": 0,
                            "api_batches": 0,
                            "errors": 1,
                            "extraction_success_rate": 0,
                            "avg_confidence_score": 0,
                            "duplicate_rate": 0,
                        },
                        "site_type": "unknown",
                        "quality_report": self.pipeline.get_quality_report(),
                        "output_path": "",
                        "error_type": "navigation_blocked",
                        "hint": "likely anti-bot or HTTP2 issue",
                    }

            await strategy.apply_dom_filters(filters)
            logger.info("Classified site=%s and started extraction at %s", site_type.value, page.url)

            schema_json = strategy.get_extraction_schema()
            schema = json.loads(schema_json)["records"][0]
            extractor = DOMClusteringExtractor(page)
            domain = self.field_engine.domain_name(page.url)
            domain_profile = self.domain_pattern_cache.get(domain, {})
            dynamic_mode = False

            if self.dynamic_mode_enabled and site_type.value == "ecommerce":
                dynamic_signals = await bm.detect_dynamic_mode(page)
                dynamic_mode = bool(dynamic_signals.get("dynamic_mode"))
                logger.info(
                    "dynamic_probe domain=%s dynamic_mode=%s has_next_data=%s has_initial_state=%s large_empty_grid=%s",
                    domain,
                    dynamic_mode,
                    dynamic_signals.get("has_next_data"),
                    dynamic_signals.get("has_initial_state"),
                    dynamic_signals.get("large_empty_grid"),
                )

            pages_visited = 0
            while pages_visited < max_pages:
                tick = time.perf_counter()
                emitted = 0
                bot_signal = False
                extraction_source_used = "none"
                scroll_attempts = 0
                dom_nodes_after_render = 0

                if dynamic_mode:
                    try:
                        render_stats = await bm.render_dynamic_page(page)
                        scroll_attempts = int(render_stats.get("scroll_attempts", 0))
                        dom_nodes_after_render = int(render_stats.get("dom_nodes_after_render", 0))
                    except Exception as exc:  # noqa: BLE001
                        # Safe fallback to legacy pipeline if dynamic rendering fails.
                        logger.warning("dynamic_mode render failed; reverting to legacy flow: %s", exc)
                        dynamic_mode = False

                html = await page.content()

                # Layer 1: structured extraction (JSON-LD / metadata) with highest confidence.
                layer1_records = self.field_engine.extract_from_html(html, page.url, site_type.value)
                if layer1_records:
                    emitted += await self.pipeline.process_batch(layer1_records, format=format)
                    domain_profile["preferred_layer"] = "layer1"
                    extraction_source_used = "layer1"

                # API discovery first when possible.
                if emitted == 0:
                    emitted += await self._extract_via_api_discovery(
                        bm=bm,
                        page=page,
                        schema=schema,
                        site_type_value=site_type.value,
                        output_format=format,
                        domain_profile=domain_profile,
                    )
                    if emitted > 0:
                        domain_profile["preferred_layer"] = "api_discovery"
                        extraction_source_used = "api_discovery"

                # Layer 2: DOM selectors / heuristics.
                if emitted == 0:
                    candidates = await extractor.extract_patterns(site_type.value)
                    layout = self.rule_engine.detect_layout(candidates)
                    best = self.rule_engine.select_top_records(candidates)
                    parsed_records = []
                    for row in best:
                        seeded = extractor.parse_item(row, schema)
                        seeded["full_text"] = row.get("full_text", "")
                        seeded["name_hint"] = row.get("name_hint", "")
                        links = row.get("links") or []
                        images = row.get("images") or []
                        if not seeded.get("url") and links:
                            seeded["url"] = links[0]
                        if not seeded.get("image_url") and images:
                            seeded["image_url"] = images[0]
                        parsed_records.append(seeded)
                    parsed_records = self.field_engine.refine_dom_records(parsed_records, page.url)
                    parsed_records = await self._structure_names_with_groq(parsed_records, site_type.value)
                    parsed_records = self._constrain_to_schema(parsed_records, schema, site_type.value)
                    emitted += await self.pipeline.process_batch(parsed_records, format=format)
                    self.metrics.dom_batches += 1
                    if emitted > 0:
                        domain_profile["preferred_layer"] = "dynamic_dom" if dynamic_mode else "dom"
                        extraction_source_used = "dynamic_dom" if dynamic_mode else "dom"
                    logger.info("DOM extraction layout=%s candidates=%s emitted=%s", layout, len(candidates), emitted)

                # Layer 3 fallback only on ambiguity/failure.
                if emitted == 0 and self.llm_extractor:
                    self.metrics.llm_calls += 1
                    llm_records = await self.llm_extractor.extract_structured(html, schema_json, site_type.value)
                    llm_records = self.field_engine.refine_dom_records(llm_records, page.url)
                    llm_records = self._constrain_to_schema(llm_records, schema, site_type.value)
                    emitted += await self.pipeline.process_batch(llm_records, format=format)
                    self.metrics.fallback_batches += 1
                    if emitted > 0:
                        domain_profile["preferred_layer"] = "llm"
                        extraction_source_used = "llm"

                if emitted == 0:
                    self.metrics.errors += 1
                    bot_signal = await self._has_bot_signal(page)
                    if debug_snapshots:
                        await save_debug_snapshot(page)

                self.metrics.records_emitted = self.pipeline.total_processed
                self.metrics.pages_visited += 1
                pages_visited += 1

                elapsed = max(0.01, time.perf_counter() - tick)
                self.rate_controller.record(response_time=elapsed, bot_signal=bot_signal)

                api_calls_captured = sum(1 for e in bm.intercepted_apis if e.get("type") == "JSON_API_FOUND")
                if not dom_nodes_after_render:
                    try:
                        dom_nodes_after_render = int(await page.evaluate("() => document.querySelectorAll('*').length"))
                    except Exception:
                        dom_nodes_after_render = 0
                logger.info(
                    "dynamic_mode=%s api_calls_captured=%s dom_nodes_after_render=%s scroll_attempts=%s extraction_source_used=%s",
                    dynamic_mode,
                    api_calls_captured,
                    dom_nodes_after_render,
                    scroll_attempts,
                    extraction_source_used,
                )

                page_move = await self.paginator.next_page(page)
                if not page_move.moved:
                    break
                await asyncio.sleep(self.rate_controller.jitter())

            if domain_profile:
                self.domain_pattern_cache[domain] = domain_profile

            total_elapsed = max(0.01, time.perf_counter() - boot_start)
            rec_per_sec = self.pipeline.total_processed / total_elapsed
            quality_report = self.pipeline.get_quality_report()

            await context.close()
            return {
                "total_records": self.pipeline.total_processed,
                "pages_visited": pages_visited,
                "api_discovery_log": bm.intercepted_apis,
                "metrics": {
                    "records_per_sec": round(rec_per_sec, 2),
                    "llm_calls": self.metrics.llm_calls,
                    "dom_batches": self.metrics.dom_batches,
                    "fallback_batches": self.metrics.fallback_batches,
                    "api_batches": self.metrics.api_batches,
                    "errors": self.metrics.errors,
                    "extraction_success_rate": quality_report.get("extraction_success_rate", 0),
                    "avg_confidence_score": quality_report.get("avg_confidence_score", 0),
                    "duplicate_rate": quality_report.get("duplicate_rate", 0),
                },
                "site_type": site_type.value,
                "quality_report": quality_report,
                "output_path": str(self.pipeline.latest_output_path) if self.pipeline.latest_output_path else "",
            }

    async def _has_bot_signal(self, page) -> bool:
        text = (await page.content()).lower()
        return any(token in text for token in ["captcha", "verify you are human", "access denied", "unusual traffic"])
