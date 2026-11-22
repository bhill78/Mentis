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


def open_quiet(browser, world, cid, viewport, arr=None):  # noqa: F811
    """Quiet Chat on that conversation, with the flow read.

    `arr` is the page's own arrangement parameter, for the cases that need a
    working column beside the conversation: a result opened into a column and
    then maximised is the ordinary way the explicit return bar is reached.
    """
    page = browser.new_page(viewport=viewport)
    page.goto(f"{world['base']}/?c={cid}" + (f"&arr={arr}" if arr else ""), wait_until="domcontentloaded")
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


def open_chooser(page, post):
    """The chooser of that post, open."""
    here = reach(page, post)
    here.first.wait_for(timeout=20_000)
    here.first.locator("button.q2r-entry").first.click()
    menu = page.locator('.q2r-chooser[role="menu"]').first
    menu.wait_for(timeout=15_000)
    menu.locator("button.q2r-item").first.wait_for(timeout=15_000)
    return menu


def test_both_continuation_routes_read_the_detail_contract(chrome, world, magnet):  # noqa: F811
    """F1 (independent rendered review adm-d4c77f502b8c, blocking).

    The host read a work-detail answer as ``result_summary`` -- the OVERVIEW
    member. The detail route answers ``result_groups``, so BOTH continuation
    reads failed: the oldest generations and the omitted tails of each group
    could not be reached through the chooser at all, and reading older
    conversation posts was still the only way to the deliverables. Both routes
    are driven here against the real server, and the server's own answer is
    read first, so a difference between what it says and what the chooser does
    is this check's own failure.
    """
    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], NARROW)
    try:
        menu = open_chooser(page, newest["reply"])
        compact_items = menu.locator("button.q2r-item").count()
        compact_groups = page.locator(".q2r-group").count()
        assert compact_groups == 8 and compact_items == 32, \
            (compact_groups, compact_items, "the server's bounded overview is 8 groups x 4 items")

        # ONE GROUP'S REMAINING ITEMS, with the server's own cursor.
        wire = {}
        with page.expect_response(lambda r: f"/api/work/{magnet['exp']}?" in r.url) as answer:
            menu.locator("button.q2r-more:not(.q2r-all)").first.click()
        got = answer.value
        wire["status"], wire["keys"] = got.status, sorted(got.json())
        assert got.status == 200 and "result_groups" in wire["keys"], wire
        page.wait_for_function(
            "n => document.querySelectorAll('.q2r-chooser button.q2r-item').length === n",
            arg=compact_items + 2, timeout=10_000)
        assert page.locator(".q2r-failed").count() == 0, "and nothing is said to have failed"

        # EVERY OLDER GROUP, with the server's own `results_before`.
        menu.locator("button.q2r-more.q2r-all").first.click()
        page.wait_for_function("document.querySelectorAll('.q2r-group').length === 25", timeout=10_000)
        assert menu.locator("button.q2r-item", has_text="gen-0-5.md").count() == 1, \
            "the oldest generation's last file is reachable through the chooser"
    finally:
        page.close()


def test_a_refused_continuation_offers_the_first_page_again(chrome, world, magnet):  # noqa: F811
    """F1's other half: the server's 409 refresh condition is told apart from
    a failed read. The refusal is fulfilled locally by the browser (no real
    cursor moves and no write), and what is checked is the chooser's answer:
    the stale cursors are dropped, the first page stands, and it is said in
    words rather than drawn as an empty or appended list."""
    import json as _json

    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], NARROW)
    try:
        menu = open_chooser(page, newest["reply"])
        before = menu.locator("button.q2r-item").count()
        page.route(
            f"**/api/work/{magnet['exp']}?**",
            lambda route: route.fulfill(status=409, content_type="application/json",
                                        body=_json.dumps({"kind": "ResultsRefreshRequired",
                                                          "error": "those cursors moved"})),
        )
        menu.locator("button.q2r-more.q2r-all").first.click()
        page.locator(".q2r-stale").wait_for(timeout=10_000)
        assert "the older pages were dropped" in menu.inner_text()
        assert menu.locator("button.q2r-item").count() == before, \
            "a refusal appends nothing and drops nothing from the page in hand"
        assert page.locator(".q2r-failed").count() == 0, \
            "and it is not reported as a failed read"
    finally:
        page.close()


def test_the_special_return_restores_the_flow_its_draft_and_keeps_both(chrome, world, magnet):  # noqa: F811
    """F3 (blocking). The return bar restored a thread only when the launch
    had one, so a reader who entered a thread after opening the result was
    left in that thread -- its composer, its draft place and its "Back to
    conversation" bar -- by the control that promised to put them back. Both
    directions are driven here, and both drafts must survive: restoring is
    CHOOSING a place, never discarding what was typed in the other one."""
    newest = magnet["rounds"][-1]
    world["cv"].say(magnet["cid"], world["who"]["@brian"],
                    [text("a reviewer replies to this generation")], replies_to=newest["reply"])
    page = open_quiet(chrome, world, magnet["cid"], WIDE, arr="two")
    try:
        page.locator("textarea").first.fill("Origin conversation draft")
        menu = open_chooser(page, newest["reply"])
        menu.locator("button.q2r-item").first.click()
        page.locator(".q2v").first.wait_for(timeout=20_000)
        page.get_by_role("button", name="Maximise", exact=True).click()
        page.get_by_role("button", name="Close viewer", exact=True).click()
        page.locator('[data-control="result-return"]').wait_for(timeout=15_000)
        # into the result post's own thread, with a draft of its own
        page.locator(f'[data-post="{newest["reply"]}"] button[title="Read the whole thread"]').first.click()
        page.wait_for_timeout(300)
        page.locator("textarea").first.fill("Separate thread draft")
        where_in_thread = page.locator(".fx-composer").first.get_attribute("data-where")
        assert where_in_thread and where_in_thread.startswith("thread:"), where_in_thread
        # the way back: the FLOW it was opened from, and the flow's own draft
        page.locator('[data-control="result-return"]').click()
        page.wait_for_selector('[data-control="result-return"]', state="detached", timeout=10_000)
        page.wait_for_timeout(300)
        assert page.get_by_role("button", name="Back to conversation").count() == 0, \
            "the reader is in the conversation flow, not still in the later thread"
        where_back = page.locator(".fx-composer").first.get_attribute("data-where")
        assert where_back == f"conversation:{magnet['cid']}", where_back
        assert page.locator("textarea").first.input_value() == "Origin conversation draft", \
            "the composer is on the launch's own place, with the draft that was there"
        # AND THE OTHER DRAFT IS STILL THERE: a place was chosen, not emptied
        page.locator(f'[data-post="{newest["reply"]}"] button[title="Read the whole thread"]').first.click()
        page.wait_for_timeout(300)
        assert page.locator("textarea").first.input_value() == "Separate thread draft", \
            "the thread's own draft was kept while the flow's was selected"
    finally:
        page.close()


def test_the_special_return_is_gated_by_the_serving_identity(chrome, world, magnet):  # noqa: F811
    """F2 (blocking). The bar's press applied the launch's plan with no check
    of which Brain the server serves, so a page that had already been told
    another Brain answered still restored the old one's conversation, centre,
    thread, reading position and reply target -- and consumed the offer.

    The 409 `BrainChanged` is fulfilled locally by the browser for one
    request: no Brain is switched, no write is made and no POST reaches the
    server. What is checked is the page's own refusal once its binding has
    moved, and that the way back is still offered afterwards."""
    import json as _json

    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], WIDE, arr="two")
    try:
        menu = open_chooser(page, newest["reply"])
        menu.locator("button.q2r-item").first.click()
        page.locator(".q2v").first.wait_for(timeout=20_000)
        page.get_by_role("button", name="Maximise", exact=True).click()
        page.get_by_role("button", name="Close viewer", exact=True).click()
        bar = page.locator('[data-control="result-return"]')
        bar.wait_for(timeout=15_000)
        page.route("**/api/mounted-check-brain-changed",
                   lambda route: route.fulfill(status=409, content_type="application/json",
                                               body=_json.dumps({"kind": "BrainChanged",
                                                                 "error": "controlled local refusal"})))
        page.evaluate("fetch('/api/mounted-check-brain-changed',{method:'POST',headers:{'X-Mentis-Client':'1'}})")
        page.wait_for_timeout(250)
        bar.click()
        page.wait_for_timeout(250)
        assert bar.count() == 1, "a refused return keeps the way back it was offered"
        said = page.locator("body").inner_text()
        assert "another Brain" in said or "serves" in said, said[:400]
    finally:
        page.close()


def test_narrow_result_rows_keep_their_own_content(chrome, world, magnet):  # noqa: F811
    """F4 (blocking). The chooser is a bounded flex column, and its rows kept
    the default `flex-shrink: 1`: with 32 real rows at 360px every row was
    squeezed towards its 40px minimum while a wrapped file name plus its
    provenance needs about 75px, so the text printed over the rows below it and
    the list could not be read. Long names, provenance, the paging rows and a
    focused row are all measured here."""
    newest = magnet["rounds"][-1]
    page = open_quiet(chrome, world, magnet["cid"], NARROW)
    try:
        menu = open_chooser(page, newest["reply"])
        menu.locator("button.q2r-item").first.focus()
        rows = menu.locator("button.q2r-item, button.q2r-more, .q2r-group-head")
        spill = rows.evaluate_all(
            """es => es.map(e => {
                 const box = e.getBoundingClientRect()
                 const inner = [...e.querySelectorAll('span')].map(s => s.getBoundingClientRect().bottom)
                 return { bottom: box.bottom, height: box.height, textBottom: Math.max(box.top, ...inner) }
               })""")
        assert spill, "there are rows to measure"
        worst = max(s["textBottom"] - s["bottom"] for s in spill)
        assert worst <= 1, (worst, [s for s in spill if s["textBottom"] - s["bottom"] > 1][:4])
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), \
            "and the horizontal fit the candidate already had is kept"
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
