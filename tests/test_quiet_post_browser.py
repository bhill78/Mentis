"""Package E (posts, the reading column and Markdown) against real Mentis
HTTP routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

LONG_MARKDOWN = (
    "## A table that must not widen the column\n\n"
    "A paragraph with `inline code`, a [link](https://example.test/long) and a rule below.\n\n"
    "- one item\n- two items\n\n"
    "> a quoted passage worth keeping intact\n\n"
    "```\nfenced(code, block)\n```\n\n"
    "---\n\n"
    "| Column A | Column B | Column C | Column D | Column E | Column F |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| wide cell one | wide cell two | wide cell three | wide cell four | wide cell five | wide cell six |\n"
    "| another wide cell | another wide cell | another wide cell | another wide cell | another wide cell | another wide cell |\n\n"
    "The final line after the table."
)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_post_typography_and_prose(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner = world["cv"], world["who"]["@brian"]
    first = cv.open_conversation("Quiet post: reading", about="Where the post package is checked.")
    cv.join(owner, first)
    plain = cv.say(first, owner, [text("A short plain post, for a spacing baseline.")])
    marked = cv.say(first, owner, [text(LONG_MARKDOWN)])
    marked2 = cv.say(first, owner, [text("A second plain post, right after the long one.")])

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{first}")
            page.get_by_role("heading", name="Quiet post: reading", exact=True).wait_for()
            page.locator(f"#qc-post-{marked}").wait_for()

            # A WIDE PIPE TABLE SCROLLS INSIDE THE COLUMN, never widening #qc-stream.
            stream_box = page.locator("#qc-stream").bounding_box()
            table_wrap = page.locator(f"#qc-post-{marked} .pr-table-wrap")
            table_wrap.wait_for()
            assert page.evaluate(
                "(el) => getComputedStyle(el).overflowX", table_wrap.element_handle()
            ) == "auto"
            table_box = table_wrap.bounding_box()
            assert table_box["x"] + table_box["width"] <= stream_box["x"] + stream_box["width"] + 1, (
                "the table's own box must not reach past the stream's right edge")
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            # HEADINGS, LISTS, QUOTES, CODE, INLINE CODE, LINKS AND RULES each compute
            # differently from the UA default for their own tag, and none of it
            # depends on .turn-body.
            def style(selector, *props):
                return page.evaluate(
                    "(args) => { const el = document.querySelector(args[0]); "
                    "if (!el) return null; const s = getComputedStyle(el); "
                    "return args.slice(1).map((p) => s[p]) }",
                    [f"#qc-post-{marked} {selector}", *props],
                )

            h = style(".pr-h", "fontWeight")
            assert h is not None and int(h[0]) >= 600, "a heading carries weight the UA default p lacks"
            lst = style(".pr-list", "paddingLeft")
            assert lst is not None and lst[0] not in ("0px", "40px"), "a list's indent is Quiet's own, not the UA default"
            quote = style(".pr-quote", "borderLeftWidth")
            assert quote is not None and quote[0] not in ("0px", "medium"), "a quote carries a border the UA default blockquote lacks"
            code_block = style(".pr-code", "backgroundColor")
            assert code_block is not None and code_block[0] not in ("rgba(0, 0, 0, 0)", "transparent"), "a code block paints a ground, unlike a bare UA pre"
            inline_code = style(".qc-body > p code", "backgroundColor")
            assert inline_code is not None and inline_code[0] not in ("rgba(0, 0, 0, 0)", "transparent"), "inline code paints a ground too"
            rule = style(".pr-rule", "borderTopStyle")
            assert rule is not None and rule[0] == "solid", "the rule is drawn solid, not the UA default inset groove"
            link = style(".qc-body a", "color")
            heading_color = style(".pr-h", "color")
            assert link is not None and heading_color is not None and link[0] != heading_color[0], (
                "a link's ink is Quiet's accent, distinct from body text")
            assert page.evaluate(
                "() => !!document.querySelector('.turn-body')"
            ) is False, "no .turn-body element anywhere on /quiet"

            # §1'S ORDERING, COMPUTED IN THE BROWSER: author most prominent, the
            # post number and the timestamp least, body text larger than all six.
            def metrics(sel):
                return page.evaluate(
                    "(sel) => { const el = document.querySelector(sel); "
                    "const s = getComputedStyle(el); "
                    "return { size: parseFloat(s.fontSize), weight: parseFloat(s.fontWeight) } }",
                    sel,
                )

            author = metrics(f"#qc-post-{marked} > header strong")
            number = metrics(f"#qc-post-{marked} > header a")
            timestamp = metrics(f"#qc-post-{marked} > header time")
            reply = metrics(f"#qc-post-{marked} > footer .qc-post-reply")
            body_size = page.evaluate(
                "(sel) => parseFloat(getComputedStyle(document.querySelector(sel)).fontSize)",
                f"#qc-post-{marked} .qc-body",
            )

            def score(m):
                return m["size"] * m["weight"]

            assert score(author) > score(number)
            assert score(author) > score(timestamp)
            assert score(author) > score(reply)
            assert body_size > author["size"]
            assert body_size > number["size"]
            assert body_size > timestamp["size"]

            # CONTENT UNCHANGED: `untrusted` stays on and the extracted text is the
            # one written, with the table's own cells reachable in the column.
            post_text = page.locator(f"#qc-post-{marked}").inner_text()
            assert "A table that must not widen the column" in post_text
            assert "wide cell six" in post_text
            assert "The final line after the table." in post_text
            assert page.locator(f"#qc-post-{marked}").locator(".pr-html").count() == 0, (
                "untrusted: no html preview is ever offered")

            # COMFORTABLE SPACING IS PRESERVED between consecutive posts, including
            # across one that grew taller for its table.
            plain_box = page.locator(f"#qc-post-{plain}").bounding_box()
            marked2_box = page.locator(f"#qc-post-{marked2}").bounding_box()
            assert plain_box is not None and marked2_box is not None
            assert marked2_box["y"] > plain_box["y"] + plain_box["height"], (
                "posts remain comfortably separated, not overlapping")

            assert errors == []
        finally:
            browser.close()
