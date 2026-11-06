"""Track 1 corrections on a disposable fixture Brain, with the built UI.

The old seam tests assert the fixed desktop shell being replaced in this
request. These cases exercise the requested document scroll model instead.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get('MENTIS_QUIET_BROWSER') != '1',
    reason='build UI and set MENTIS_QUIET_BROWSER=1',
)


@pytest.fixture
def reading(world):
    cv, owner = world['cv'], world['who']['@brian']
    cid = cv.open_conversation('Quiet layout correction')
    cv.join(owner, cid)
    cv.open_topic(cid, 'Reading')
    for n in range(12):
        cv.say(cid, owner, [text(f'Post {n}. ' + 'A quiet conversation with room in its margins. ' * 16)])
    return cid


def open_reading(page, world, reading):
    page.goto(world['base'] + f'/quiet#/c/{reading}')
    page.get_by_role('heading', name='Quiet layout correction', exact=True).wait_for()
    page.locator('.qc-post').first.wait_for()
    page.get_by_label('Continue the conversation', exact=True).wait_for()
    page.get_by_role('button', name='Settings', exact=True).wait_for()


def screenshot(page, name):
    folder = os.environ.get('QUIET_LAYOUT_EVIDENCE')
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name))


@pytest.mark.parametrize('engine', ['chromium', 'webkit'])
@pytest.mark.parametrize('width', [1440, 901, 900, 390])
def test_document_scroll_alignment_and_optional_pins(world, reading, engine, width):
    pw = pytest.importorskip('playwright.sync_api')
    with pw.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={'width': width, 'height': 900})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            open_reading(page, world, reading)
            heading = page.locator('.qc-heading > div').bounding_box()
            stream = page.locator('#qc-stream').bounding_box()
            assert abs(heading['x'] - stream['x']) <= 1
            assert abs(heading['width'] - stream['width']) <= 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('.qc-background select').count() == 0
            composer = page.get_by_label('Continue the conversation', exact=True).bounding_box()
            assert 0 <= composer['y'] < 900
            assert composer['y'] + composer['height'] <= 900
            start = page.locator('.qc-cell-nav').bounding_box()['y']
            page.evaluate('window.scrollTo(0, 600)')
            page.wait_for_function('scrollY >= 599')
            assert page.locator('.qc-global').bounding_box()['y'] < 0
            assert page.locator('.qc-cell-nav').bounding_box()['y'] < start - 599
            assert page.locator('#qc-stream').evaluate('(el) => el.scrollTop') == 0
            composer = page.get_by_label('Continue the conversation', exact=True).bounding_box()
            assert 0 <= composer['y'] < 900
            assert composer['y'] + composer['height'] <= 900
            page.evaluate('window.scrollTo(0, 0)')
            page.get_by_role('button', name='Settings', exact=True).click()
            page.get_by_label('Pin header', exact=True).check()
            page.get_by_label('Pin margins', exact=True).check()
            page.get_by_role('button', name='Close settings').click()
            page.evaluate('window.scrollTo(0, 600)')
            page.wait_for_function('scrollY >= 599')
            header = page.locator('.qc-global').bounding_box()
            assert abs(header['y']) <= 1
            assert page.locator('.qc-heading').bounding_box()['y'] < 0
            if width > 900:
                margin = page.locator('.qc-cell-nav').bounding_box()
                assert abs(margin['y'] - header['height'] - 16) <= 1
            else:
                assert page.locator('.qc-cell-nav').evaluate('(el) => getComputedStyle(el).position') == 'static'
            assert page.locator('#qc-stream').evaluate('(el) => el.scrollTop') == 0
            page.reload()
            page.wait_for_selector('.qc[data-pin-header=true][data-pin-margins=true]')
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize('engine', ['chromium', 'webkit'])
@pytest.mark.parametrize('width', [1440, 390])
def test_settings_themes_opacity_blur_and_reload(world, reading, engine, width):
    pw = pytest.importorskip('playwright.sync_api')
    with pw.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={'width': width, 'height': 900})
            open_reading(page, world, reading)
            screenshot(page, f'{engine}-{width}-layout.png')
            page.get_by_role('button', name='Settings', exact=True).click()
            panel = page.get_by_role('region', name='Appearance settings')
            box = panel.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= width
            background = page.get_by_label('Background', exact=True)
            expected = ['default', 'saltmarsh', 'research', 'development', 'mist', 'tidewater',
                        'nightfall', 'shoal', 'downland', 'monolith', 'hailmary']
            assert background.locator('option').evaluate_all('(els) => els.map(el => el.value)') == expected
            for atmosphere in expected:
                background.select_option(atmosphere)
                page.wait_for_function('(at) => (document.documentElement.dataset.atmosphere || "default") === at', arg=atmosphere)
            for theme in ['dark', 'light', 'system']:
                page.get_by_label('Theme', exact=True).select_option(theme)
                page.wait_for_function('(t) => (document.documentElement.dataset.theme || "system") === t', arg=theme)
            background.select_option('tidewater')
            page.get_by_role('radio', name='Glass', exact=True).check()
            opacity = page.get_by_role('slider', name=re.compile('Surface opacity'))
            opacity.press('End')
            page.wait_for_function('getComputedStyle(document.querySelector(".qc"), "::after").opacity === "1"')
            opacity.press('Home')
            page.wait_for_function('getComputedStyle(document.querySelector(".qc"), "::after").opacity === "0"')
            # Native keyboard input must update both the live paint and storage.
            opacity.press('ArrowRight')
            page.wait_for_function('getComputedStyle(document.querySelector(".qc"), "::after").opacity === "0.01"')
            blur = page.get_by_role('slider', name=re.compile('Glass blur'))
            blur.press('End')
            page.wait_for_function('getComputedStyle(document.querySelector(".qc"), "::before").filter.includes("32px")')
            page.get_by_role('radio', name='Solid', exact=True).check()
            assert page.get_by_role('slider', name=re.compile('Surface opacity')).input_value() == '86'
            page.get_by_role('radio', name='Glass', exact=True).check()
            assert page.get_by_role('slider', name=re.compile('Surface opacity')).input_value() == '1'
            page.reload()
            page.get_by_role('button', name='Settings', exact=True).click()
            assert page.get_by_role('radio', name='Glass', exact=True).is_checked()
            assert page.get_by_role('slider', name=re.compile('Surface opacity')).input_value() == '1'
            assert page.get_by_role('slider', name=re.compile('Glass blur')).input_value() == '32'
            screenshot(page, f'{engine}-{width}-settings.png')
            page.keyboard.press('Escape')
            assert page.get_by_role('button', name='Settings', exact=True).evaluate('(el) => el === document.activeElement')
            assert page.get_by_role('region', name='Appearance settings').count() == 0
            page.get_by_role('button', name='Settings', exact=True).click()
            page.locator('.qc-heading h1').click()
            assert page.get_by_role('region', name='Appearance settings').count() == 0
        finally:
            browser.close()
