"""The narrow (phone/tablet) atmosphere treatment, reachable in both apps.

The owner's discovered-work item (ent-b965c587db4a): atmosphere.css's narrow
overrides were keyed on `.workspace.phone` / `.workspace.tablet`, which no
live component in either Fluid or /quiet renders, so every narrow-viewport
treatment was dead. The fix (atmosphere.css, picture/store.ts) replaces that
with a plain `max-width` media query that needs no component to write any
class or attribute. This proves it reaches both apps and that the faintest
ink painted at a narrow viewport still clears 4.5:1.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

NARROW_PROPS = ("--reading-veil", "--canvas-image-position")

#: An atmosphere whose narrow (phone/tablet) treatment actually differs from
#: its wide one on both the properties above, so the comparison is real.
ATMOSPHERE = "tidewater"

#: Read the atmosphere's custom properties as the browser resolves them now.
READ = r"""
(props) => {
  const cs = getComputedStyle(document.documentElement)
  const out = {}
  for (const p of props) out[p] = cs.getPropertyValue(p).trim()
  return out
}
"""

#: The contrast an element's own ink actually reaches over the layers painted
#: behind it (WCAG 2.x relative luminance), the same measurement
#: test_quiet_chat_browser.py uses for its own ink checks.
CONTRAST = r"""
() => {
  // A custom property's raw value may be a hex literal ('#0e1518') rather
  // than the resolved rgb() a painted element's computed style would give,
  // so it is read through a probe element instead of parsed as text.
  const probe = document.createElement('span')
  probe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden'
  document.body.appendChild(probe)
  const resolve = (value) => { probe.style.color = value; return getComputedStyle(probe).color }
  const nums = (c) => (String(c).match(/[\d.]+/g) || [0, 0, 0]).map(Number)
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
  const cs = getComputedStyle(document.documentElement)
  const ground = nums(resolve(cs.getPropertyValue('--canvas')))
  const faint = nums(resolve(cs.getPropertyValue('--text-faint')))
  probe.remove()
  const pair = [lum(ground), lum(faint)].sort((a, b) => b - a)
  return (pair[0] + 0.05) / (pair[1] + 0.05)
}
"""


def _set_atmosphere(page, atmosphere: str) -> None:
    page.evaluate("(a) => document.documentElement.setAttribute('data-atmosphere', a)", atmosphere)


@pytest.mark.parametrize("atmosphere,width", [("mist", 390), ("hailmary", 390), ("hailmary", 820)])
def test_quiet_paints_narrow_canvas_veil(world, atmosphere, width):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 844})
            page.goto(world["base"] + "/quiet")
            page.wait_for_load_state("networkidle")
            _set_atmosphere(page, atmosphere)
            got = page.evaluate("""() => {
              const veil = getComputedStyle(document.querySelector('.qc'), '::after')
              const probe = document.createElement('div')
              probe.style.backgroundImage = getComputedStyle(document.documentElement).getPropertyValue('--canvas-veil')
              document.body.appendChild(probe)
              const expected = getComputedStyle(probe).backgroundImage
              probe.remove()
              return {content: veil.content, image: veil.backgroundImage, expected}
            }""")
            assert got["content"] == '""'
            assert got["expected"] != "none"
            assert got["image"] == got["expected"]
        finally:
            browser.close()


@pytest.mark.parametrize("path", ["/fluid", "/quiet"])
def test_narrow_atmosphere_reachable_in_both_apps(world, path):
    """Each app's narrow viewport gets the override; its wide one does not."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                page.goto(world["base"] + path)
                page.wait_for_load_state("networkidle")
                _set_atmosphere(page, ATMOSPHERE)
                wide = page.evaluate(READ, NARROW_PROPS)

                page.set_viewport_size({"width": 390, "height": 844})
                narrow = page.evaluate(READ, NARROW_PROPS)

                for prop in NARROW_PROPS:
                    assert narrow[prop] != wide[prop], (
                        f"{path}: {prop} did not change at a narrow viewport "
                        f"(wide={wide[prop]!r})"
                    )
            finally:
                page.close()
        finally:
            browser.close()


@pytest.mark.parametrize("path", ["/fluid", "/quiet"])
@pytest.mark.parametrize("atmosphere", [
    "tidewater", "nightfall", "shoal", "downland", "monolith", "hailmary",
])
def test_every_narrow_atmosphere_reaches_both_apps(world, path, atmosphere):
    """Every atmosphere the owner named as dead is reachable now, in both apps."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            try:
                page.goto(world["base"] + path)
                page.wait_for_load_state("networkidle")
                _set_atmosphere(page, atmosphere)
                got = page.evaluate(READ, NARROW_PROPS)
                assert any(v for v in got.values()), (
                    f"{path}/{atmosphere}: no narrow custom property resolved to anything"
                )
            finally:
                page.close()
        finally:
            browser.close()


@pytest.mark.parametrize("path", ["/fluid", "/quiet"])
def test_mist_is_phone_only_in_both_apps(world, path):
    """Mist's narrow treatment is scoped to phone (<=760px), not tablet."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                page.goto(world["base"] + path)
                page.wait_for_load_state("networkidle")
                _set_atmosphere(page, "mist")
                wide = page.evaluate(READ, ("--canvas-veil",))

                page.set_viewport_size({"width": 820, "height": 1180})  # tablet
                tablet = page.evaluate(READ, ("--canvas-veil",))
                assert tablet["--canvas-veil"] == wide["--canvas-veil"], (
                    f"{path}: mist's veil changed at tablet width, which it never did"
                )

                page.set_viewport_size({"width": 390, "height": 844})  # phone
                phone = page.evaluate(READ, ("--canvas-veil",))
                assert phone["--canvas-veil"] != wide["--canvas-veil"], (
                    f"{path}: mist's veil did not change at phone width"
                )
            finally:
                page.close()
        finally:
            browser.close()


@pytest.mark.parametrize("path", ["/fluid", "/quiet"])
def test_narrow_contrast_still_clears_aa(world, path):
    """The faintest ink over the canvas still clears 4.5:1 at a narrow width."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            try:
                page.goto(world["base"] + path)
                page.wait_for_load_state("networkidle")
                for atmosphere in ("tidewater", "nightfall", "shoal", "downland", "monolith", "hailmary", "mist"):
                    _set_atmosphere(page, atmosphere)
                    ratio = page.evaluate(CONTRAST)
                    assert ratio >= 4.5, f"{path}/{atmosphere}: faint ink over canvas reaches only {ratio:.2f}:1"
            finally:
                page.close()
        finally:
            browser.close()
