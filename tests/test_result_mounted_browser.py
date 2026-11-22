"""THE RESULT-FIRST PATH AS A READER ACTUALLY MEETS IT, mounted.

Every earlier check of this round was either source over fixtures or the
chooser alone in a harness, because nothing in `src/` called `mountResults`
and nothing drew the chooser: both parts said so in their own limits. This
candidate wires `quiet2/Quiet2.tsx`, so the path can be driven where the
owner reads it -- the built interface, served by a real Mentis server over a
DISPOSABLE fixture Brain, in headless Chrome.

The scenario is the owner's own (§8): a Magnet-shaped design conversation
where the deliverables are NOT in the latest reply chain -- twenty-five
generations of returned mockups, each with a mapped carrier update, buried
under fifty later replies about routing, review and status.

What is checked:

  * the Work's actual results are offered on the exact post the record maps
    them to, with the files' own references, and a post the record maps
    nothing to carries nothing;
  * opening one reaches the deliverable itself, not an activity log;
  * closing it OFFERS the explicit way back, and that way back returns the
    reader to the conversation they pressed it from;
  * the whole path works at 360px with no horizontal overflow.

Opt in with ``MENTIS_QUIET_BROWSER=1``; it needs Playwright, installed
Chrome, and ``apps/fluid-web`` built (``npm run build``). No live Brain, no
MARS, no dispatch: `world` captures dispatches and builds its own corpus
under pytest's tmp_path.
"""
from __future__ import annotations

import os

import pytest

from mentis.conversation import text
from mentis.operational import current_work as cw
from tests._loop import get, world  # noqa: F401
from tests.test_result_destinations import ask, result

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 to run the mounted browser checks",
)

#: the phone width the owner's narrow checks use
NARROW = {"width": 360, "height": 780}
WIDE = {"width": 1440, "height": 900}


@pytest.fixture(autouse=True)
def fresh_models():
    cw.forget()
    yield
    cw.forget()


@pytest.fixture()
def magnet(world):  # noqa: F811
    """A design conversation shaped like the Magnet one: the mockups are
    generations back, under a long tail of agent chatter."""
    exp = ask(world, "Make mockups of the yellow Quiet Magnet")
    cv, who = world["cv"], world["who"]["@brian"]
    cid = world["results_cid"]
    rounds = []
    for generation in range(25):
        cv.say(cid, who, [text("routing review and status")])
        rounds.append(result(world, exp, 6, generation=generation))
        cv.say(cid, who, [text("not a mapped update")])
    # the chatter the owner complained about: the latest post is about
    # delegation and review routing, never the deliverable
    chatter = [cv.say(cid, who, [text(f"delegating the next review round {n}")])
               for n in range(50)]
    return {"exp": exp, "cid": cid, "rounds": rounds, "chatter": chatter}


@pytest.fixture()
def chrome():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=os.environ.get("MENTIS_BROWSER_CHANNEL", "chrome"))
        yield browser
        browser.close()


def open_quiet(browser, world, cid, viewport):  # noqa: F811
    """Quiet Chat on that conversation, with the flow read."""
    page = browser.new_page(viewport=viewport)
    page.goto(f"{world['base']}/?c={cid}", wait_until="domcontentloaded")
    # never `networkidle`: the page keeps a live pulse open for ever
    page.wait_for_selector(".q2-conv", timeout=30_000)
    page.wait_for_selector("[data-post]", timeout=30_000)
    return page


def results_section(page, post):
    return page.locator(f'[data-post="{post}"] .q2r-post-results')


def reach(page, post):
    """The mapped post, reached the way a reader reaches it: the deliverable
    is generations back, so the conversation is read backwards until the post
    carrying it is drawn. This is the owner's own complaint, as a navigation."""
    for _ in range(40):
        if page.locator(f'[data-post="{post}"]').count():
            return results_section(page, post)
        earlier = page.get_by_role("button", name="Read earlier posts")
        if not earlier.count():
            break
        earlier.first.click()
        page.wait_for_timeout(300)
    raise AssertionError(f"the mapped post {post} was never drawn")


def gen_names(generation, count=6):
    """The names the fixture's returned files are held under."""
    return [f"gen-{generation}-{n}.md" for n in range(count)]


def test_the_record_s_own_mapping_offers_the_actual_results(chrome, world, magnet):  # noqa: F811
    """The results are on the mapped posts, with their own references, and
    nowhere else. The server's answer is read first, so a difference between
    what the record maps and what is drawn is this check's own failure."""
    overview = get(world, f"/api/work?conversation={magnet['cid']}")
    item = next(i for i in overview["items"] if i["expectation"] == magnet["exp"])
    mapped = {t["turn"] for t in item.get("update_turns") or []}
    assert item.get("result_summary"), "the server answers this Work's bounded result page"
    assert mapped, "and names the exact Turns its returns were mapped to"
    newest = magnet["rounds"][-1]
    assert newest["reply"] in mapped

    page = open_quiet(chrome, world, magnet["cid"], WIDE)
    try:
        here = reach(page, newest["reply"])
        here.first.wait_for(timeout=15_000)
        entry = here.first.locator("button.q2r-entry").first
        assert "Results" in entry.inner_text()
        assert (here.first.locator("[data-work]").first.get_attribute("data-work") or "") == magnet["exp"], \
            "the chooser names the Work the record maps, not a guess"
        entry.click()
        chooser = page.locator('.q2r-chooser[role="menu"]').first
        chooser.wait_for(timeout=15_000)
        rows = chooser.locator('[role="menuitem"]')
        assert rows.count() >= 2, "the chooser lists the group and its files"
        # THE EXACT FILES THIS GENERATION RETURNED, under the names the server
        # holds them by -- never a label parsed out of anything.
        shown = chooser.inner_text()
        names = gen_names(24)
        assert any(n in shown for n in names), (shown, names)
        page.keyboard.press("Escape")
        # and a post the record maps nothing to carries nothing
        plain = magnet["chatter"][-1]
        if page.locator(f'[data-post="{plain}"]').count():
            assert results_section(page, plain).count() == 0, "an unmapped post carries no chooser"
    finally:
        page.close()


def test_opening_a_result_reaches_the_deliverable_and_returns(chrome, world, magnet):  # noqa: F811
    """Press a result: the file itself opens, maximised over the conversation,
    and ONE history entry is made for it. Close it: the reader is put back in
    the conversation they pressed it from, at the post they pressed -- which
    is the request's "clear way to return", and `history.ts`'s own plan for a
    maximised result the reader is still standing on (the explicit pill is for
    the other case, a close whose entry navigation has since left).

    A phone width is used deliberately: with no working columns the result has
    nowhere but maximised to open, which is the path that walks the history.
    """
    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], NARROW)
    try:
        here = reach(page, newest["reply"])
        entries = page.evaluate("history.length")
        here.first.locator("button.q2r-entry").first.click()
        chooser = page.locator('.q2r-chooser[role="menu"]').first
        chooser.wait_for(timeout=15_000)
        item = chooser.locator("button.q2r-item").first
        item.wait_for(timeout=15_000)
        label = item.inner_text()
        item.click()
        # THE DELIVERABLE ITSELF, in the page's own viewer frame
        viewer = page.locator(".q2v").first
        viewer.wait_for(timeout=20_000)
        assert page.evaluate("history.length") == entries + 1, \
            "exactly one history entry for the displacement, never two"
        # its own close: the way back, taken by the control that claims it
        close = viewer.get_by_role("button", name="Close", exact=False).first
        close.click()
        page.wait_for_selector(".q2-conv [data-post]", timeout=15_000)
        assert page.locator(".q2v").count() == 0, f"the viewer is given up after {label!r}"
        # back where the press was made, with the post still there
        page.locator(f'[data-post="{newest["reply"]}"]').first.wait_for(timeout=15_000)
        assert results_section(page, newest["reply"]).count() == 1, \
            "and the results entry that was pressed is where it was"
    finally:
        page.close()


def test_the_result_path_fits_a_phone(chrome, world, magnet):  # noqa: F811
    """360px: the chooser is readable, its controls reachable, and nothing
    overflows sideways."""
    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], NARROW)
    try:
        here = reach(page, newest["reply"])
        here.first.wait_for(timeout=20_000)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), \
            "no horizontal overflow at 360px with the chooser closed"
        box = here.first.bounding_box()
        assert box and box["width"] <= NARROW["width"], box
        # THE CHOOSER ITSELF, OPENED BY KEYBOARD ALONE at a phone width
        entry = here.first.locator("button.q2r-entry").first
        entry.focus()
        page.keyboard.press("Enter")
        chooser = page.locator('.q2r-chooser[role="menu"]').first
        chooser.wait_for(timeout=15_000)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), \
            "nor with it open"
        open_box = chooser.bounding_box()
        assert open_box and open_box["x"] >= -1 and open_box["x"] + open_box["width"] <= NARROW["width"] + 1, open_box
        rows = chooser.locator('[role="menuitem"]')
        assert rows.count() >= 2
        for n in range(min(3, rows.count())):
            r = rows.nth(n).bounding_box()
            assert r and r["width"] > 0 and r["height"] > 0, (n, r)
    finally:
        page.close()
