import asyncio
import argparse
import sys
import os
from typing import Optional
from dotenv import load_dotenv

from agents.universal_agent import UniversalScraperAgent
from core.config_loader import load_runtime_config
from utils.logger import setup_logger

# Fix Windows charmap error for special characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logger = setup_logger("UNIVERSAL_SCRAPER")
load_dotenv()

async def run_platform(
    url: str,
    request: str,
    pages: int,
    format: str,
    min_price: Optional[str],
    max_price: Optional[str],
    brand: Optional[str],
    min_rating: Optional[str],
    headless: bool,
    debug_snapshots: bool,
):
    """CLI entrypoint for universal extraction."""
    def _clean_api_key(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.lower().startswith("your_") or "your_api_key" in trimmed.lower():
            return None
        return trimmed

    api_key = _clean_api_key(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
    groq_api_key = _clean_api_key(os.getenv("GROQ_API_KEY"))
    if not api_key:
        logger.warning("OPENROUTER_API_KEY/OPENAI_API_KEY not found. LLM fallback will be disabled.")
    if not groq_api_key:
        logger.warning("GROQ_API_KEY not found. Groq name structuring will be disabled.")

    agent = UniversalScraperAgent(
        llm_api_key=api_key,
        groq_api_key=groq_api_key,
        llm_model=os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
        groq_model=os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
    )

    filters = {
        "price_min": min_price,
        "price_max": max_price,
        "brand": brand,
        "min_rating": min_rating,
        "query": request,
    }

    logger.info("Initializing extraction for %s with query '%s'", url, request)

    try:
        result = await agent.run_task(
            start_url=url,
            filters=filters,
            max_pages=pages,
            format=format,
            headless=headless,
            debug_snapshots=debug_snapshots,
        )

        logger.info("Extraction complete")
        logger.info("Total records: %s", result["total_records"])
        logger.info("Pages scraped: %s", result["pages_visited"])
        logger.info("Site type: %s", result.get("site_type"))
        logger.info("Output: %s", result.get("output_path"))

        metrics = result.get("metrics", {})
        if metrics:
            logger.info("Records/sec: %s | LLM calls: %s", metrics.get("records_per_sec"), metrics.get("llm_calls"))

        if result.get("api_discovery_log"):
            apis = [api.get("url") for api in result["api_discovery_log"] if api.get("type") == "JSON_API_FOUND"]
            if apis:
                logger.info("Discovered %s hidden JSON APIs", len(apis))

    except Exception as e:  # noqa: BLE001
        import traceback

        logger.error("Critical failure: %s\n%s", e, traceback.format_exc())


async def run_with_config(config_path: str) -> None:
    cfg = load_runtime_config(config_path)
    await run_platform(
        url=cfg.url,
        request=cfg.filters.query,
        pages=cfg.max_pages,
        format=cfg.output_format,
        min_price=str(cfg.filters.price_min) if cfg.filters.price_min is not None else None,
        max_price=str(cfg.filters.price_max) if cfg.filters.price_max is not None else None,
        brand=cfg.filters.brand,
        min_rating=str(cfg.filters.min_rating) if cfg.filters.min_rating is not None else None,
        headless=cfg.headless,
        debug_snapshots=cfg.debug_snapshots,
    )


async def run_schedule(interval_seconds: int, **kwargs) -> None:
    while True:
        await run_platform(**kwargs)
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal AI Data Extraction Platform")

    parser.add_argument("url", nargs="?", help="Target URL")
    parser.add_argument("request", nargs="?", default="", help="What to extract")
    parser.add_argument("--pages", type=int, default=5, help="Max pages to scrape (default: 5)")
    parser.add_argument("--format", choices=["csv", "json", "jsonl", "xlsx", "parquet"], default="csv", help="Output format (default: csv)")
    parser.add_argument("--min-price", help="Minimum price filter (if applicable)")
    parser.add_argument("--max-price", help="Maximum price filter (if applicable)")
    parser.add_argument("--brand", help="Brand filter")
    parser.add_argument("--min-rating", help="Minimum rating filter")
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode")
    parser.add_argument("--debug-snapshots", action="store_true", help="Save HTML and screenshot on failures")
    parser.add_argument("--config", help="Path to YAML or JSON config file")
    parser.add_argument("--schedule", type=int, default=0, help="Repeat run every N seconds (cron-like loop)")
    parser.add_argument("--api", action="store_true", help="Start FastAPI server (http://localhost:8000)")
    parser.add_argument("--api-host", default="0.0.0.0", help="API server host (default: 0.0.0.0)")
    parser.add_argument("--api-port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--reload-api", action="store_true", help="Enable auto-reload for API development")

    args = parser.parse_args()

    # Start API server if --api flag is used
    if args.api:
        import uvicorn
        logger.info(f"Starting FastAPI server on {args.api_host}:{args.api_port}")
        logger.info("Dashboard available at http://localhost:8000")
        uvicorn.run("api:app", host=args.api_host, port=args.api_port, reload=args.reload_api)
        sys.exit(0)

    if args.config:
        asyncio.run(run_with_config(args.config))
    else:
        if not args.url:
            raise SystemExit("url is required when --config is not provided (or use --api to start the API server)")

        payload = {
            "url": args.url,
            "request": args.request,
            "pages": args.pages,
            "format": args.format,
            "min_price": args.min_price,
            "max_price": args.max_price,
            "brand": args.brand,
            "min_rating": args.min_rating,
            "headless": not args.headful,
            "debug_snapshots": args.debug_snapshots,
        }

        if args.schedule > 0:
            asyncio.run(run_schedule(args.schedule, **payload))
        else:
            asyncio.run(run_platform(**payload))