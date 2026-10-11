import logging
import asyncio
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from nexus_app.security.ssrf import validate_url, is_ip_blocked
from nexus_app.config import settings

logger = logging.getLogger("nexus.engine.browser")

class BrowserWorker:
    """
    Playwright-based browser renderer for authorized JavaScript-rendered web pages.
    Applies strict route filtering to prevent internal network SSRF within browser contexts.
    """

    def __init__(self, timeout_seconds: Optional[int] = None):
        self.timeout = (timeout_seconds or settings.PLAYWRIGHT_TIMEOUT_SECONDS) * 1000

    def render_page(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        wait_timeout_ms: int = 5000
    ) -> str:
        """
        Loads the page in a headless Chromium browser, executes JavaScript,
        and returns the fully rendered DOM HTML string.
        """
        # Step 1: Pre-validation of starting URL
        validate_url(url)

        try:
            from playwright.sync_api import sync_playwright, Route, Request
        except ImportError:
            raise RuntimeError("Playwright is not installed in the environment.")

        with sync_playwright() as p:
            # Launch isolated browser with security flags
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            context = browser.new_context(
                user_agent=settings.USER_AGENT,
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=False,
            )

            # SSRF route interceptor: block any sub-request to forbidden IPs
            def route_interceptor(route: Route, request: Request):
                req_url = request.url
                try:
                    validate_url(req_url)
                    route.continue_()
                except Exception as exc:
                    logger.warning(f"Browser worker blocked sub-request to {req_url}: {exc}")
                    route.abort("blockedbyclient")

            page = context.new_page()
            page.route("**/*", route_interceptor)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=wait_timeout_ms)
                    except Exception:
                        logger.debug(f"Timeout waiting for selector '{wait_selector}' on {url}")
                else:
                    # Give dynamic scripts 1-2 seconds to hydrate
                    page.wait_for_timeout(1500)

                html_content = page.content()
                return html_content
            finally:
                context.close()
                browser.close()
