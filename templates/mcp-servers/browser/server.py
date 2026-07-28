"""Browser MCP server — FastMCP + Playwright async.

Tool names match templates/mcp-servers/browser/tools/*.tool.yaml IDs.
Requires: playwright install chromium
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

# Import shared SSRF helper from repo package
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from neuroswarm_arm.runtime.router.mcp_ssrf import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    SsrfError,
    validate_url_ssrf,
)

mcp = FastMCP("browser")

_TEXT_LIMIT = 8000
_SCREENSHOT_MAX_BYTES = int(os.environ.get("NSA_MCP_BROWSER_MAX_BYTES", str(DEFAULT_MAX_BYTES * 5)))
_MAX_REDIRECTS = int(os.environ.get("NSA_MCP_BROWSER_MAX_REDIRECTS", str(DEFAULT_MAX_REDIRECTS)))


def _tenant_id() -> str | None:
    tid = (os.environ.get("NSA_MCP_TENANT_ID") or "").strip()
    return tid or None


def _map_playwright_error(exc: Exception, *, action: str) -> ValueError:
    msg = str(exc)
    lower = msg.lower()
    if isinstance(exc, SsrfError) or isinstance(exc, ValueError) and "blocked" in lower:
        return ValueError(str(exc))
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


def _require_url(url: str) -> str:
    try:
        return validate_url_ssrf(url, tenant_id=_tenant_id())
    except SsrfError as exc:
        raise ValueError(str(exc)) from None


def _cap_text(text: str, limit: int = _TEXT_LIMIT) -> str:
    if len(text) > limit:
        return text[:limit] + "\n…[truncated]"
    return text


async def _attach_ssrf_route(page: Any) -> None:
    """Block navigations/requests to private/metadata targets; enforce redirect hop budget."""
    hops = {"n": 0}
    tid = _tenant_id()

    async def _on_route(route: Any) -> None:
        req = route.request
        req_url = req.url
        # Count document navigations / redirects toward hop budget
        if req.is_navigation_request():
            hops["n"] += 1
            if hops["n"] > _MAX_REDIRECTS + 1:  # initial + redirects
                await route.abort("blockedbyclient")
                return
        try:
            validate_url_ssrf(req_url, tenant_id=tid)
        except SsrfError:
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    await page.route("**/*", _on_route)


async def _new_secure_page(browser: Any) -> Any:
    page = await browser.new_page()
    await _attach_ssrf_route(page)
    return page


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def navigate(url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    """Navigate to a URL in headless Chromium and return title/url/text excerpt."""
    _require_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until=wait_until, timeout=30000)
                title = await page.title()
                final_url = page.url
                text = _cap_text(await page.inner_text("body"))
                return {"url": final_url, "title": title, "text": text}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="navigate") from None


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def open_page(url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    """Legacy alias for navigate."""
    return await navigate(url=url, wait_until=wait_until)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def click(url: str, selector: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    """Open a page, click a CSS selector, return resulting title/url."""
    _require_url(url)
    if not selector:
        raise ValueError("selector is required")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
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
async def extract_links(url: str, selector: str = "a[href]", attribute: str = "href") -> dict[str, Any]:
    """Open a page and extract link hrefs (or another attribute) from a CSS selector."""
    _require_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                locs = page.locator(selector)
                count = await locs.count()
                values: list[str] = []
                for i in range(min(count, 200)):
                    val = await locs.nth(i).get_attribute(attribute)
                    if val:
                        values.append(val)
                return {"url": page.url, "selector": selector, "attribute": attribute, "links": values}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="extract_links") from None


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def extract(url: str, selector: str, attribute: str | None = None) -> dict[str, Any]:
    """Legacy single-element extract; prefer extract_links for link lists."""
    _require_url(url)
    if not selector:
        raise ValueError("selector is required")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                loc = page.locator(selector).first
                await loc.wait_for(state="attached", timeout=15000)
                if attribute:
                    value = await loc.get_attribute(attribute)
                else:
                    value = await loc.inner_text()
                if isinstance(value, str):
                    value = _cap_text(value)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def screenshot(url: str, full_page: bool = False) -> dict[str, Any]:
    """Navigate and return a PNG screenshot (base64)."""
    _require_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                png = await page.screenshot(full_page=full_page, type="png")
                truncated = len(png) > _SCREENSHOT_MAX_BYTES
                if truncated:
                    png = png[:_SCREENSHOT_MAX_BYTES]
                return {
                    "url": page.url,
                    "title": await page.title(),
                    "encoding": "base64",
                    "content_type": "image/png",
                    "truncated": truncated,
                    "bytes": len(png),
                    "body": base64.b64encode(png).decode("ascii"),
                }
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="screenshot") from None


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snapshot(url: str) -> dict[str, Any]:
    """Navigate and return an accessibility/tree-ish text snapshot of the page."""
    _require_url(url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                snap = await page.accessibility.snapshot()
                text = _cap_text(await page.inner_text("body"))
                return {"url": page.url, "title": await page.title(), "accessibility": snap, "text": text}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="snapshot") from None


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def type_text(
    url: str,
    selector: str,
    text: str,
    wait_until: str = "domcontentloaded",
) -> dict[str, Any]:
    """Open a page and type text into a CSS selector."""
    _require_url(url)
    if not selector:
        raise ValueError("selector is required")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await _new_secure_page(browser)
                await page.goto(url, wait_until=wait_until, timeout=30000)
                await page.fill(selector, text or "", timeout=15000)
                return {"url": page.url, "selector": selector, "typed_chars": len(text or "")}
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        raise _map_playwright_error(exc, action="type_text") from None


if __name__ == "__main__":
    mcp.run()
