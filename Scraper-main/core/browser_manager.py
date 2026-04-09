from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import Browser, BrowserContext, Page, Request, Response, async_playwright

from utils.logger import setup_logger

logger = setup_logger(__name__)


class BrowserManager:
    """Playwright lifecycle manager with anti-bot controls and API discovery."""

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[Dict[str, str]] = None,
        persist_session: bool = True,
        dynamic_mode_enabled: bool = False,
        dynamic_wait_timeout_ms: int = 7000,
        dynamic_selector_timeout_ms: int = 3500,
        dynamic_scroll_steps: int = 4,
        enable_http2_fallback: bool = True,
        enable_stealth_headers: bool = True,
    ):
        self.headless = headless
        self.proxy = proxy
        self.persist_session = persist_session
        self.dynamic_mode_enabled = dynamic_mode_enabled
        self.dynamic_wait_timeout_ms = max(1000, dynamic_wait_timeout_ms)
        self.dynamic_selector_timeout_ms = max(500, dynamic_selector_timeout_ms)
        self.dynamic_scroll_steps = max(1, min(8, dynamic_scroll_steps))
        self.enable_http2_fallback = enable_http2_fallback
        self.enable_stealth_headers = enable_stealth_headers
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.intercepted_apis: list[dict[str, Any]] = []
        self._context_kwargs: dict[str, Any] = {}
        self._http2_fallback_mode = False

        self.navigation_failed = False
        self.blocked_detected = False
        self.http2_fallback_used = False
        self.navigation_attempts = 0
        self.final_url = ""

    async def __aenter__(self) -> "BrowserManager":
        self.playwright = await async_playwright().start()
        await self._launch_browser(http2_fallback=False)
        return self

    async def _launch_browser(self, http2_fallback: bool) -> None:
        if not self.playwright:
            raise RuntimeError("Playwright is not initialized")

        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--ignore-certificate-errors",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--blink-settings=imagesEnabled=false",
        ]

        if http2_fallback:
            args.extend(
                [
                    "--disable-http2",
                    "--disable-features=NetworkService",
                    "--ignore-certificate-errors",
                ]
            )

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            proxy=self.proxy,
            args=args,
        )
        self._http2_fallback_mode = http2_fallback

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def create_context(self) -> BrowserContext:
        if not self.browser:
            raise RuntimeError("Browser is not initialized")

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.208 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.208 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.208 Safari/537.36",
        ]
        viewports = [
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1920, "height": 1080},
        ]

        self._context_kwargs = {
            "user_agent": random.choice(user_agents),
            "viewport": random.choice(viewports),
            "locale": "en-US",
            "timezone_id": "Asia/Kolkata",
            "java_script_enabled": True,
            "bypass_csp": True,
            "service_workers": "allow",
            "device_scale_factor": 1,
        }
        context = await self.browser.new_context(**self._context_kwargs)

        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                            get: () => false
            });
            window.chrome = window.chrome || { runtime: {} };
            """
        )

        if self.persist_session:
            session_dir = Path("data/logs/sessions")
            session_dir.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(session_dir / "last_session.json"))

        self.context = context
        return context

    async def watch_network(self, page: Page) -> None:
        async def handle_request(request: Request) -> None:
            if request.resource_type not in {"fetch", "xhr"}:
                return
            self.intercepted_apis.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "type": "API_REQUEST",
                    "resource_type": request.resource_type,
                }
            )

        async def handle_response(response: Response) -> None:
            req = response.request
            if req.resource_type not in {"fetch", "xhr"}:
                return
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            lowered = response.url.lower()
            product_like_hint = any(token in lowered for token in ["product", "products", "catalog", "search", "listing", "item"])
            self.intercepted_apis.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "content_type": content_type,
                    "type": "JSON_API_FOUND",
                    "resource_type": req.resource_type,
                    "product_like_hint": product_like_hint,
                }
            )

        page.on("request", handle_request)
        page.on("response", handle_response)

    async def _recreate_context_and_page(self, old_page: Page) -> tuple[BrowserContext, Page]:
        old_context = old_page.context
        try:
            await old_context.close()
        except Exception:
            pass

        if not self.browser:
            raise RuntimeError("Browser is not initialized")

        kwargs = self._context_kwargs or {
            "locale": "en-US",
            "timezone_id": "Asia/Kolkata",
            "java_script_enabled": True,
            "bypass_csp": True,
            "service_workers": "allow",
            "device_scale_factor": 1,
        }
        self.context = await self.browser.new_context(**kwargs)
        await self.context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => false
            });
            window.chrome = window.chrome || { runtime: {} };
            """
        )
        new_page = await self.context.new_page()
        await self.watch_network(new_page)
        return self.context, new_page

    async def _apply_stealth_headers(self, page: Page) -> None:
        if not self.enable_stealth_headers:
            return
        await page.set_extra_http_headers(
            {
                "accept-language": "en-US,en;q=0.9",
                "upgrade-insecure-requests": "1",
                "sec-fetch-site": "none",
                "sec-fetch-mode": "navigate",
                "sec-fetch-user": "?1",
                "sec-fetch-dest": "document",
            }
        )

    @staticmethod
    def _is_transport_error(exc: Exception, current_url: str) -> bool:
        msg = str(exc).lower()
        return any(
            token in msg
            for token in [
                "err_http2_protocol_error",
                "err_connection_closed",
                "net::err_http2_protocol_error",
                "net::err_connection_closed",
                "chrome-error://chromewebdata",
            ]
        ) or current_url.startswith("chrome-error://")

    async def _navigate_legacy(self, page: Page, url: str, max_retries: int) -> tuple[bool, Page]:
        for attempt in range(max_retries):
            self.navigation_attempts = attempt + 1
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(0.2, 0.9))
                self.final_url = page.url
                return True, page
            except Exception as exc:  # noqa: BLE001
                logger.warning("Navigation attempt %s failed for %s: %s", attempt + 1, url, exc)
                if attempt == max_retries - 1:
                    return False, page
                await asyncio.sleep(min(4.0, 0.5 * (2**attempt)))
        return False, page

    async def navigate_with_retry(self, page: Page, url: str, max_retries: int = 3) -> tuple[bool, Page]:
        self.navigation_failed = False
        self.blocked_detected = False
        self.http2_fallback_used = False
        self.navigation_attempts = 0
        self.final_url = ""

        if not self.enable_http2_fallback and not self.enable_stealth_headers:
            ok, current_page = await self._navigate_legacy(page, url, max(1, max_retries))
            self.navigation_failed = not ok
            return ok, current_page

        current_page = page
        fallback_attempts = 0
        current_max_retries = max(1, max_retries)

        for attempt in range(current_max_retries):
            self.navigation_attempts += 1
            try:
                await self._apply_stealth_headers(current_page)
                await current_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await current_page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                self.final_url = current_page.url
                if self.final_url.startswith("chrome-error://"):
                    raise RuntimeError("chrome-error://chromewebdata/")

                await asyncio.sleep(random.uniform(0.2, 0.9))
                return True, current_page
            except Exception as exc:  # noqa: BLE001
                logger.warning("Navigation attempt %s failed for %s: %s", attempt + 1, url, exc)

                # Secondary strategy: full load event + manual settling window.
                try:
                    await self._apply_stealth_headers(current_page)
                    await current_page.goto(url, wait_until="load", timeout=30000)
                    await current_page.wait_for_timeout(random.randint(3000, 5000))
                    self.final_url = current_page.url
                    if self.final_url.startswith("chrome-error://"):
                        raise RuntimeError("chrome-error://chromewebdata/")
                    return True, current_page
                except Exception as retry_exc:  # noqa: BLE001
                    logger.warning("Navigation secondary strategy failed for %s: %s", url, retry_exc)

                self.final_url = current_page.url
                is_transport = self._is_transport_error(exc, self.final_url)
                if is_transport:
                    self.blocked_detected = True

                if self.enable_http2_fallback and is_transport and not self._http2_fallback_mode and fallback_attempts < 2:
                    fallback_attempts += 1
                    self.http2_fallback_used = True
                    try:
                        await self._launch_browser(http2_fallback=True)
                        _, current_page = await self._recreate_context_and_page(current_page)
                    except Exception as relaunch_exc:  # noqa: BLE001
                        logger.warning("HTTP2 fallback relaunch failed for %s: %s", url, relaunch_exc)

                    current_max_retries = max(current_max_retries, self.navigation_attempts + 1)

                if attempt == current_max_retries - 1:
                    self.navigation_failed = True
                    return False, current_page

                await asyncio.sleep(min(4.0, 0.5 * (2**attempt)))

        self.navigation_failed = True
        return False, current_page

    async def detect_dynamic_mode(self, page: Page) -> dict[str, Any]:
        if not self.dynamic_mode_enabled:
            return {
                "dynamic_mode": False,
                "has_next_data": False,
                "has_initial_state": False,
                "large_empty_grid": False,
            }

        js = """
        () => {
          const hasNextData = !!document.querySelector('script#__NEXT_DATA__') || typeof window.__NEXT_DATA__ !== 'undefined';
          const hasInitialState = typeof window.__INITIAL_STATE__ !== 'undefined';

          const candidates = Array.from(document.querySelectorAll('[class*=grid], [class*=list], main, section, ul, ol'));
          let largeEmptyGrid = false;
          for (const el of candidates) {
            const childCount = el.children ? el.children.length : 0;
            const textLen = ((el.innerText || '').trim()).length;
            if (childCount >= 8 && textLen < 120) {
              largeEmptyGrid = true;
              break;
            }
          }

          return {
            has_next_data: hasNextData,
            has_initial_state: hasInitialState,
            large_empty_grid: largeEmptyGrid,
            dynamic_mode: !!(hasNextData || hasInitialState || largeEmptyGrid),
          };
        }
        """
        try:
            result = await page.evaluate(js)
        except Exception:
            result = {}

        return {
            "dynamic_mode": bool(result.get("dynamic_mode")),
            "has_next_data": bool(result.get("has_next_data")),
            "has_initial_state": bool(result.get("has_initial_state")),
            "large_empty_grid": bool(result.get("large_empty_grid")),
        }

    async def _wait_dynamic_quiet_window(self, page: Page) -> None:
        # Keep timeout bounded so static flows do not slow down.
        try:
            await page.wait_for_load_state("networkidle", timeout=min(self.dynamic_wait_timeout_ms, 5000))
        except Exception:
            pass
        await page.wait_for_timeout(2000)

    async def _wait_product_container(self, page: Page) -> None:
        selectors = (
            "[data-testid*=product], [class*=product], [class*=Product], "
            "[class*=listing], [class*=grid] [class*=item], article, li"
        )
        try:
            await page.wait_for_selector(selectors, timeout=self.dynamic_selector_timeout_ms)
        except Exception:
            pass

    async def _auto_scroll(self, page: Page) -> int:
        attempts = 0
        for _ in range(self.dynamic_scroll_steps):
            attempts += 1
            try:
                reached_bottom = await page.evaluate(
                    """
                    () => {
                      const before = window.scrollY;
                      window.scrollBy(0, Math.max(480, Math.floor(window.innerHeight * 0.9)));
                      const maxY = Math.max(0, document.body.scrollHeight - window.innerHeight - 4);
                      return window.scrollY >= maxY || window.scrollY === before;
                    }
                    """
                )
            except Exception:
                break
            await page.wait_for_timeout(random.randint(320, 760))
            if reached_bottom:
                break
        return attempts

    async def render_dynamic_page(self, page: Page) -> dict[str, Any]:
        if not self.dynamic_mode_enabled:
            return {"scroll_attempts": 0, "dom_nodes_after_render": 0}

        await self._wait_dynamic_quiet_window(page)
        await self._wait_product_container(page)
        scroll_attempts = await self._auto_scroll(page)
        dom_nodes_after_render = 0
        try:
            dom_nodes_after_render = int(await page.evaluate("() => document.querySelectorAll('*').length"))
        except Exception:
            dom_nodes_after_render = 0
        return {
            "scroll_attempts": scroll_attempts,
            "dom_nodes_after_render": dom_nodes_after_render,
        }

    async def fetch_api_payload(self, page: Page, url: str) -> list[dict[str, Any]]:
        try:
            response = await page.context.request.get(url, timeout=12000)
            if response.status != 200:
                return []
            payload = await response.json()
        except Exception:
            return []

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            # Flatten common response envelopes.
            for key in ("data", "items", "results", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []
