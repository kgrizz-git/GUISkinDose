"""Write the third-party notices compiled into a Chromium build to an HTML file.

Chromium ships its third-party licence texts inside the binary, shown at
``chrome://credits``; the release zips carry no credits file. The Full portable
build ships this dump beside the browser so the notices match the exact binary.

Usage (build machine, unfrozen)::

    python packaging/portable/dump_chromium_credits.py <chrome.exe> <CREDITS.html>

The command line ``--dump-dom chrome://credits`` opens a New Tab page instead,
so this drives the browser over DevTools with choreographer (a Kaleido dependency).
Prints the byte count and the number of credited products; exits 1 if the page
looks empty.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_MIN_BYTES = 100_000
_EXPR = "document.documentElement.outerHTML"
_COUNT = "document.querySelectorAll('.product').length"


async def _evaluate(tab, expression: str):
    response = await tab.send_command("Runtime.evaluate", params={"expression": expression, "returnByValue": True})
    return response["result"]["result"]["value"]


async def dump(browser_path: str, out_path: Path) -> tuple[int, int]:
    import choreographer

    async with choreographer.Browser(path=browser_path, headless=True) as browser:
        tab = await browser.create_tab("about:blank")
        await tab.send_command("Page.navigate", params={"url": "chrome://credits/"})
        html, products = "", 0
        for _ in range(30):  # the page fills in after load; wait up to ~15 s
            await asyncio.sleep(0.5)
            products = await _evaluate(tab, _COUNT)
            if products:
                await asyncio.sleep(1)
                products = await _evaluate(tab, _COUNT)
                html = await _evaluate(tab, _EXPR)
                break
        else:
            html = await _evaluate(tab, _EXPR)
    out_path.write_text("<!DOCTYPE html>\n" + html, encoding="utf-8")
    return out_path.stat().st_size, products


def main(argv: list[str]) -> int:
    size, products = asyncio.run(dump(argv[0], Path(argv[1])))
    # Builds made without generate_about_credits=true serve a placeholder page.
    placeholder = "sample credits page" in Path(argv[1]).read_text(encoding="utf-8")
    print(f"CREDITS.html bytes={size} product_entries={products} placeholder={placeholder}")
    return 0 if size >= _MIN_BYTES and products > 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
