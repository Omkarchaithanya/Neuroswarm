"""Browser MCP server — REAL implementation (FastMCP + Playwright async).

Replaces the fake stub that only echoed its own tool description back.
Auth: none (local headless Chromium). After pip install, run:
  playwright install chromium

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

mcp = FastMCP("browser")

_TEXT_LIMIT = 8000


def _map_playwright_error(exc: Exception, *, action: str) -> ValueError:
    msg = str(exc)
    lower = msg.lower()
    if isinstance(exc, PlaywrightTimeoutError) or "timeout" in lower:
        return ValueError(
            f"Browser {action} timed out. Check the URL/selector and network; try a simpler page."
        )
    if "net::err" in lower or "navigation" in lower:
        return ValueError(
            f"Browser navigation failed during {action}: {msg}. Check the URL is reachable."
        )
    if "executable doesn't exist" in lower or "browserType.launch" in lower:
        return ValueError(
            "Chromium not installed for Playwright. Run: playwright install chromium"
        )
    if "strict mode violation" in lower or "resolved to" in lower:
        return ValueError(
            f"Selector matched multiple elements during {action}. Use a more specific CSS selector."
        )
    if "not found" in lower or "no node" in lower or "waiting for selector" in lower:
        return ValueError(
            f"Element not found during {action}. Check the CSS selector against the page DOM."
        )
    return ValueError(f"Browser {action} failed: {msg}")


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def open_page(url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    """Navigate to a URL in headless Chromium and return title/url/text excerpt.

    Args:
        url: absolute http(s) URL
        wait_until: load state — load | domcontentloaded | networkidle | commit
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError('url must be an absolute http(s) URL, e.g. "https://example.com"')
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until=wait_until, timeout=30000)
                title = await page.title()
                final_url = page.url
                text = await page.inner_text("body")
                if len(text) > _TEXT_LIMIT:
                    text = text[:_TEXT_LIMIT] + "\n…[truncated]"
                return {"url": final_url, "title": title, "text": text}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="open_page") from None


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def click(url: str, selector: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    """Open a page, click a CSS selector, return resulting title/url.

    Args:
        url: page to open first
        selector: CSS selector to click
        wait_until: initial navigation wait state
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError('url must be an absolute http(s) URL')
    if not selector:
        raise ValueError("selector is required")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until=wait_until, timeout=30000)
                await page.click(selector, timeout=15000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                return {"url": page.url, "title": await page.title(), "clicked": selector}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="click") from None


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def extract(url: str, selector: str, attribute: str | None = None) -> dict[str, Any]:
    """Open a page and extract text (or an attribute) from a CSS selector.

    Args:
        url: page URL
        selector: CSS selector
        attribute: optional attribute name (e.g. href); default is inner text
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError('url must be an absolute http(s) URL')
    if not selector:
        raise ValueError("selector is required")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                loc = page.locator(selector).first
                await loc.wait_for(state="attached", timeout=15000)
                if attribute:
                    value = await loc.get_attribute(attribute)
                else:
                    value = await loc.inner_text()
                if isinstance(value, str) and len(value) > _TEXT_LIMIT:
                    value = value[:_TEXT_LIMIT] + "\n…[truncated]"
                return {
                    "url": page.url,
                    "selector": selector,
                    "attribute": attribute,
                    "value": value,
                }
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="extract") from None


if __name__ == "__main__":
    mcp.run()
