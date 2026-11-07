"""PACKAGE G against real Mentis HTTP routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.

Three claims, each one a check that can refuse the build:

* EACH OF THE 11 ATMOSPHERES PAINTS THROUGH ``useLook``, switched and
  persisted from the control in the header's right cell -- without an edit
  to ``atmosphere.css`` (asserted structurally in
  ``tests/quiet_surface_unit.mjs``; here it is asserted live, by reading
  ``data-atmosphere`` back off the document after each choice).
* SOLID AND GLASS ARE BOTH AVAILABLE, switched from the same control, and
  the choice is visibly distinct (``.qc``'s computed background differs).
* IN EACH -- solid and glass -- AND IN LIGHT, SYSTEM DARK AND CHOSEN DARK,
  THE FAINTEST INK QUIET WRITES IN STILL CLEARS 4.5:1, measured by the
  shared helper every package that paints a ground measures with
  (``tests/quiet_contrast.py``), so this suite and the reconciled-findings
  suite cannot disagree about what 4.5:1 means here.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import get, world  # noqa: F401
from tests.quiet_contrast import QUIET_INK, legible, reads_in, rendered_legible


def _open_settings(page):
    """The Appearance panel starts closed behind the header's Settings button."""
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("region", name="Appearance settings", exact=True).wait_for()

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

ATMOSPHERES = [
    "default", "saltmarsh", "research", "development", "mist", "tidewater",
    "nightfall", "shoal", "downland", "monolith", "hailmary",
]

#: One light built-in and one dark built-in, beside the plain default --
#: enough to show the contrast guarantee holds across the ground's own
#: palette, without every test running all 11 atmospheres through all three
#: schemes and both treatments (33 combinations each already).
REPRESENTATIVE = ATMOSPHERES


def _a_conversation_to_read(world):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet surface", about="The room G paints.")
    cv.join(owner, cid)
    # A topic, so the margin's nav holds a link with aria-current and one
    # without -- QUIET_INK measures both, and a conversation with none of its
    # own would leave the second unmeasurable rather than legible.
    cv.open_topic(cid, "Reading", about="What the margin lists.")
    cv.say(cid, owner, [text("A post, so the stream and the margin both draw something.")])
    return cid


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_each_of_the_eleven_atmospheres_paints_through_use_look(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conversation = _a_conversation_to_read(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            reads_in(page, world["base"], conversation, "Quiet surface")
            _open_settings(page)

            picker = page.get_by_label("Background", exact=True)
            for atmosphere in ATMOSPHERES:
                picker.select_option(atmosphere)
                want = None if atmosphere == "default" else atmosphere
                page.wait_for_function(
                    "(want) => (document.documentElement.dataset.atmosphere || null) === want",
                    arg=want,
                )

            # The choice is persisted: a reload of the same conversation keeps
            # the last one picked rather than reverting to the default.
            page.reload()
            reads_in(page, world["base"], conversation, "Quiet surface")
            page.wait_for_function(
                "() => document.documentElement.dataset.atmosphere === 'hailmary'")
            _open_settings(page)
            page.wait_for_function(
                "() => document.querySelector('[aria-label=\"Background\"]')?.value === 'hailmary'")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_solid_and_glass_are_both_available_and_visibly_distinct(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation_to_read(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            reads_in(page, world["base"], conversation, "Quiet surface")
            _open_settings(page)

            # Glass treats the backdrop image, not .qc's own colour -- every
            # ink colour sits directly on that colour with no wrapper of its
            # own, so it is the one property glass must leave exactly as
            # solid left it. An atmosphere with a backdrop (saltmarsh) is
            # what shows the two treatments actually differ.
            page.get_by_label("Background", exact=True).select_option("saltmarsh")
            page.wait_for_function(
                "() => document.documentElement.dataset.atmosphere === 'saltmarsh'")

            assert page.evaluate("document.querySelector('.qc').dataset.surface") == "solid"
            solid_bg = page.evaluate("getComputedStyle(document.querySelector('.qc')).backgroundColor")
            solid_before = page.evaluate(
                "getComputedStyle(document.querySelector('.qc'), '::before').filter")

            page.get_by_role("radio", name="Glass", exact=True).click()
            page.wait_for_function(
                "() => document.querySelector('.qc').dataset.surface === 'glass'")
            glass_bg = page.evaluate("getComputedStyle(document.querySelector('.qc')).backgroundColor")
            glass_before = page.evaluate(
                "getComputedStyle(document.querySelector('.qc'), '::before').filter")
            assert glass_bg == solid_bg, (
                "glass must leave .qc's own measured background exactly as solid left it")
            assert glass_before != solid_before, "glass must treat the backdrop image differently"

            # Persisted the same way the atmosphere is: this browser, every page.
            page.reload()
            reads_in(page, world["base"], conversation, "Quiet surface")
            assert page.evaluate("document.querySelector('.qc').dataset.surface") == "glass"
            _open_settings(page)
            assert page.get_by_role("radio", name="Glass", exact=True).is_checked()
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("treatment", ["solid", "glass"])
def test_the_faintest_ink_clears_aa_in_every_scheme_under_both_treatments(world, engine, treatment):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation_to_read(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            for atmosphere in REPRESENTATIVE:
                for scheme, chosen, dark in (("dark", None, True),
                                              ("light", "dark", True),
                                              ("light", None, False)):
                    page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                             color_scheme=scheme)
                    try:
                        # The origin must exist before localStorage can be set,
                        # and the treatment (like the theme) is read once at
                        # load -- a hash-only move does not reload the page,
                        # so a reload is what makes either one take effect.
                        page.goto(world["base"] + "/quiet")
                        if chosen:
                            page.evaluate("(t) => localStorage.setItem('mentis:theme', t)", chosen)
                        page.evaluate(
                            "(t) => localStorage.setItem('mentis:quiet-surface', t)", treatment)
                        page.reload()
                        page.goto(world["base"] + f"/quiet#/c/{conversation}")
                        reads_in(page, world["base"], conversation, "Quiet surface")
                        _open_settings(page)
                        picker = page.get_by_label("Background", exact=True)
                        picker.select_option(atmosphere)
                        want = None if atmosphere == "default" else atmosphere
                        page.wait_for_function(
                            "(want) => (document.documentElement.dataset.atmosphere || null) === want",
                            arg=want,
                        )
                        assert page.evaluate(
                            "document.querySelector('.qc').dataset.surface") == treatment

                        page.evaluate(r'''async () => {
                            const bg = getComputedStyle(document.querySelector('.qc'), '::before').backgroundImage;
                            for (const m of bg.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
                                const image = new Image(); image.src = m[1]; await image.decode();
                            }
                            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        }''')
                        pixels = rendered_legible(page, QUIET_INK + (
                            '.qc-background-pick', '.qc-surface-pick label:has(input:checked)',
                            '.qc-surface-pick label:has(input:not(:checked))',))
                        assert pixels, 'no visible text measured'
                        for pixel in pixels:
                            assert pixel['ratio'] >= 4.5, f"{treatment}/{atmosphere}/{scheme}/{chosen}: {pixel}"
                        measured = legible(page, QUIET_INK)
                        for selector, got in measured.items():
                            assert got["ratio"] >= 4.5, (
                                f"{treatment}/{atmosphere}/{scheme}/{chosen}: "
                                f"{selector} reaches only {got['ratio']:.2f}:1")
                    finally:
                        page.close()
        finally:
            browser.close()
