"""Playwright browser client lifecycle management with bounded concurrency and resource hardening."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from app.core.exceptions import BrowserUnavailableError

logger = logging.getLogger(__name__)

# Enforce bounded concurrency for laptop resources (16 GB RAM / no dedicated GPU)
MAX_CONCURRENT_BROWSERS = 1
_CONCURRENCY_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)

# Hardened Chromium launch arguments
# Note: Native OS sandboxing is kept enabled on Windows by omitting '--no-sandbox'.
CHROMIUM_LAUNCH_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--mute-audio",
    "--no-first-run",
    "--disable-features=AudioServiceOutOfProcess",
]

DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
BROWSER_USER_AGENT = "UniversalSEOPlatform-Browser/0.1.0 (+http://localhost/bot-info)"


@asynccontextmanager
async def browser_session() -> AsyncGenerator:
    """Async context manager that provisions an isolated Chromium browser and context.

    Enforces:
    - Bounded concurrency via Semaphore to prevent RAM exhaustion.
    - Chromium process cleanup in finally block under all outcomes (success, error, cancellation).
    - Downloads and dangerous permissions disabled.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as err:
        raise BrowserUnavailableError(
            "Playwright package is not installed. Install with 'pip install playwright'."
        ) from err

    async with _CONCURRENCY_SEMAPHORE:
        pw = None
        browser = None
        context = None
        try:
            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=CHROMIUM_LAUNCH_ARGS,
                )
            except Exception as err:
                error_msg = str(err)
                if "Executable doesn't exist" in error_msg or "install" in error_msg.lower():
                    raise BrowserUnavailableError(
                        "Chromium executable is not installed. Run 'python -m playwright install chromium' to install."
                    ) from err
                raise BrowserUnavailableError(f"Failed to launch Chromium browser: {err}") from err

            context = await browser.new_context(
                accept_downloads=False,
                permissions=[],
                ignore_https_errors=False,
                service_workers="block",
                viewport=DEFAULT_VIEWPORT,
                user_agent=BROWSER_USER_AGENT,
            )

            yield context

        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception as err:
                    logger.debug("Error closing browser context: %s", err)

            if browser is not None:
                try:
                    await browser.close()
                except Exception as err:
                    logger.debug("Error closing browser: %s", err)

            if pw is not None:
                try:
                    await pw.stop()
                except Exception as err:
                    logger.debug("Error stopping Playwright runtime: %s", err)
