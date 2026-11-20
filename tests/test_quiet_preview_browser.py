"""WHAT AN AGENT WOULD BE GIVEN, in a real browser.

The real built Quiet Chat (`/quiet2`) against a real HTTP server backed by a
disposable fixture Brain (`tests/_loop.py`'s `world`): a Persona that carries
a Discipline, rules placed on the whole Brain and on one conversation, a rule
nobody placed, an adopted lesson, and a proposal that must be left out.

What is checked is what the owner asked for (2026-11-20, issues C1 and C2):

  - the preview says what it is and why you would look, in plain words, and
    none of the old labels ("Name material for it", "Would receive", "What
    would compose now") or the word "material" is shown;
  - the first view is an outline: groups by why a piece is given, one line
    per piece, with counts;
  - a piece's whole text opens in place as prose, never as one long link;
    "Open record" opens that exact record, by its id;
  - nothing is lost: every text the server composed is reachable;
  - records can be added for one run and taken back, and describing the work
    brings the knowledge matched to it;
  - it only ever reads (no POST), works by keyboard, gives focus back, and
    fits a 390 px screen;
  - the legacy Fluid sheet at `/fluid` still opens, unchanged.

Build apps/fluid-web first, then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os

import pytest

from tests._loop import world, post, get  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

ENGINE = "chrome"
MS = 15000

LONG = ("A stage is claimed only when it is reached. Report only the stage an operation has actually reached "
        "and verified, in exact words: prepared, launched, running, completed and verified, failed or rolled back."
        "\n\nNever promise a later check unless something recorded will bring it about.")
HERE = "Answer in plain words in this conversation. Lead with what changed."
SPARE = "Merged means pushed. When work is merged into main, push main to origin as part of the same work."
CARRIED = "Work in a workspace of your own: one clone or branch per piece of work, removed when it is merged."
LESSON = "Zebra migrations must be rehearsed on a copy of the Brain before they are run for real."
PROPOSAL = "Proposed only: nobody has established this yet."


@pytest.fixture
def me_id(world):
    rows = get(world, "/api/participants?limit=1")["participants"]
    assert rows
    return rows[0]["participant"]


@pytest.fixture
def brain(world, me_id):
    """The records the preview is asked about, and where each one sits."""
    conv = post(world, "/api/conversations", {"name": "Release check"})["conversation"]

    def record(kind, body, establish=True, **more):
        made = post(world, "/api/entries", {"kind": kind, "body": body, "attributed_to": me_id, "establish": establish, **more})
        assert "entry" in made, made
        return made["entry"]

    def place(entry, where):
        to = {"whole_brain": True} if where is None else {"where": where}
        placed = post(world, f"/api/entries/{entry}/place", {"attributed_to": me_id, "because": "for the test", **to})
        assert "error" not in placed, placed

    long = record("rule", {"text": LONG})
    here = record("rule", {"text": HERE})
    spare = record("rule", {"text": SPARE})
    carried = record("discipline", {"name": "Own workspace", "about": "Where work is done", "text": CARRIED})
    lesson = record("lesson", {"text": LESSON}, basis=[long])
    proposal = record("rule", {"text": PROPOSAL}, establish=False)
    place(long, None)             # the whole Brain
    place(here, conv)
    place(proposal, conv)
    place(carried, world["persona"])
    return {"conv": conv, "long": long, "here": here, "spare": spare, "carried": carried, "lesson": lesson,
            "proposal": proposal, "persona": world["persona"]}


def _page(playwright, width=1440, height=1000):
    browser = playwright.chromium.launch(channel=ENGINE)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    writes: list[str] = []
    page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method != "GET" and "/api/" in r.url and "/owner/" not in r.url else None)
    return browser, page, errors, writes


def _open(page, world, conversation):
    page.context.set_extra_http_headers(owner_headers())
    page.goto(world["base"] + f"/quiet2?c={conversation}")
    page.get_by_role("button", name="Brain", exact=True).first.wait_for(timeout=MS)


def _brain_button(page):
    """The Brain button this width shows: the rail's, or the top line's on a phone."""
    return page.locator("button[aria-label='Brain']:visible").first


def _preview(page):
    _brain_button(page).click()
    page.get_by_role("button", name="Make, import, preview").click()
    page.get_by_role("menuitem", name="See what an agent will receive…").click()
    sheet = page.locator("[data-receive-preview]")
    sheet.wait_for(timeout=MS)
    sheet.locator("[data-rp-result]").wait_for(timeout=MS)
    return sheet


def _as_steward(sheet):
    sheet.get_by_label("Persona it is started as").select_option(label="Steward")
    sheet.locator('[data-rp-group="persona"]').wait_for(timeout=MS)


def _count(sheet, group):
    return sheet.locator(f'[data-rp-group="{group}"] [data-rp-item]').count()


def _no_sideways(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


# -- 1. what it says, and the outline ----------------------------------------

def test_the_preview_says_what_it_is_and_reads_as_an_outline(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p)
        _open(page, world, brain["conv"])
        sheet = _preview(page)
        _as_steward(sheet)

        said = sheet.inner_text()
        assert page.get_by_role("dialog", name="What an agent would be given").is_visible()
        assert "would be handed right now" in said and "Nothing runs and nothing is recorded." in said
        assert "Release check" in said and "as Steward" in said.replace("\n", " ")
        assert "How it has gone" in said          # where what a past run was really given is found
        # the old words are gone, and the engine's vocabulary is not shown
        low = said.lower()
        for gone in ("material", "would receive", "what would compose", "started as (persona)", "computed · not a record",
                     "invocation", "runtime: no control"):
            assert gone not in low, gone
        # each control says what it is for
        for label in ("Who would do the work", "Persona it is started as", "Also give it a record, for this one run",
                      "The work it would be asked to do"):
            assert sheet.get_by_label(label, exact=True).is_visible(), label
        for hint in ("The participant doing the work.", "The role it is started as.", "As if named for this one run.",
                     "Knowledge is matched to these words."):
            assert hint in said, hint

        # the outline: why it is given, then where it comes from, with counts
        assert sheet.locator("[data-rp-section]").evaluate_all("els => els.map(e => e.dataset.rpSection)") == \
            ["governing", "knowledge", "also", "left-out"]
        assert _count(sheet, "persona") == 2       # the Persona, and the Discipline it carries
        assert _count(sheet, "conversation") == 1
        assert _count(sheet, "brain") >= 1
        assert _count(sheet, "sent") >= 1          # the orientation every run is sent
        head = sheet.locator('[data-rp-group="persona"] h4').inner_text()
        assert head.startswith("From the Persona") and "2" in head
        items = sheet.locator("[data-rp-item]").count()
        assert f"{items} items would be given" in sheet.locator(".rp-sum").inner_text()
        assert "Describe the work above" in sheet.locator('[data-rp-section="knowledge"]').inner_text()

        # one line each: kind, a title, and why; nothing is open
        assert sheet.locator("[data-rp-body]").count() == 0
        row = sheet.locator(f'[data-entry="{brain["long"]}"] .rp-row')
        assert row.get_attribute("aria-expanded") == "false"
        assert row.locator(".rp-kind").inner_text().lower() == "rule"
        assert row.locator(".rp-title").inner_text() == "A stage is claimed only when it is reached."
        assert row.locator(".rp-because").inner_text() == "placed on the whole Brain"
        assert row.bounding_box()["height"] < 48
        assert sheet.locator(f'[data-entry="{brain["here"]}"] .rp-because').inner_text() == "placed on this conversation"
        carried = sheet.locator(f'[data-entry="{brain["carried"]}"]')
        assert carried.locator(".rp-title").inner_text() == "Own workspace"
        assert carried.locator(".rp-because").inner_text() == "carried by the Persona Steward"
        assert sheet.locator(f'[data-entry="{brain["persona"]}"] .rp-title').inner_text() == "Steward"
        assert "Never promise a later check" not in sheet.inner_text()

        assert not writes, writes                 # a preview only reads
        assert not errors, errors
        browser.close()


# -- 2. the whole text, in place; the record itself, by id -------------------

def test_a_piece_opens_in_place_as_prose_and_open_record_goes_to_that_record(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p)
        _open(page, world, brain["conv"])
        sheet = _preview(page)
        _as_steward(sheet)

        item = sheet.locator(f'[data-entry="{brain["long"]}"]')
        row = item.locator(".rp-row")
        row.focus()
        page.keyboard.press("Enter")              # a disclosure is a button
        assert row.get_attribute("aria-expanded") == "true"
        body = item.locator("[data-rp-body]")
        assert body.get_attribute("id") == row.get_attribute("aria-controls")
        text = body.locator("[data-rp-text]")
        assert [t.strip() for t in text.locator("p").all_inner_texts()] == LONG.split("\n\n")
        # prose, not a link: nothing around the words is pressable or underlined
        assert text.evaluate("el => !el.closest('button, a') && !el.querySelector('button, a')")
        assert text.locator("p").first.evaluate("el => getComputedStyle(el).textDecorationLine") == "none"
        opener = body.get_by_role("button", name="Open record")
        assert opener.get_attribute("data-open-record") == brain["long"]
        page.keyboard.press("Enter")              # and closes again
        assert row.get_attribute("aria-expanded") == "false" and item.locator("[data-rp-body]").count() == 0

        # everything is reachable: expand all shows every text the server composed
        composed = get(world, f"/api/context?conversation={brain['conv']}&persona={brain['persona']}"
                              f"&participant={get(world, '/api/participants?limit=1')['participants'][0]['participant']}")
        sheet.locator("[data-rp-all]").click()
        assert sheet.locator("[data-rp-body]").count() == sheet.locator("[data-rp-item]").count() == len(composed["components"])
        shown = " ".join(sheet.locator("[data-rp-result]").inner_text().split())
        for c in composed["components"]:
            for para in c["text"].split("\n\n"):
                assert " ".join(para.split()) in shown, (c["source_kind"], para[:60])
        assert sheet.locator("[data-rp-all]").inner_text() == "Collapse all"

        # what was left out, and why
        fold = sheet.get_by_role("button", name="Left out, and why")
        assert fold.get_attribute("aria-expanded") == "false"
        fold.click()
        out = sheet.locator('[data-rp-section="left-out"]')
        assert "proposed, not established yet" in out.inner_text()
        assert out.locator(f'[data-open-record="{brain["proposal"]}"]').count() == 1

        # Open record: that record, by its id, in Brain management
        sheet.locator(f'[data-entry="{brain["here"]}"] [data-open-record]').click()
        page.locator(f'[data-record="{brain["here"]}"]').wait_for(timeout=MS)
        assert page.locator("[data-receive-preview]").count() == 0
        assert "Answer in plain words in this conversation." in page.locator(f'[data-record="{brain["here"]}"]').inner_text()
        assert not writes, writes
        assert not errors, errors
        browser.close()


# -- 3. the controls: add a record for one run, describe the work ------------

def test_adding_a_record_and_describing_the_work_change_what_would_be_given(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p)
        _open(page, world, brain["conv"])
        sheet = _preview(page)
        assert sheet.locator(f'[data-entry="{brain["spare"]}"]').count() == 0    # placed nowhere: not given

        add = sheet.get_by_label("Also give it a record, for this one run")
        add.select_option(value=brain["spare"])
        named = sheet.locator('[data-rp-group="named"]')
        named.wait_for(timeout=MS)
        assert named.locator(f'[data-entry="{brain["spare"]}"] .rp-because').inner_text() == "named for this run"
        assert "Named for this run" in named.locator("h4").inner_text()
        chips = sheet.get_by_role("list", name="Records added for this one run")
        assert "Merged means pushed." in chips.inner_text()
        chips.get_by_role("button", name="Remove Merged means pushed.").click()
        named.wait_for(state="detached", timeout=MS)

        sheet.get_by_label("The work it would be asked to do").fill("rehearse the zebra migrations")
        lesson = sheet.locator(f'[data-rp-section="knowledge"] [data-entry="{brain["lesson"]}"]')
        lesson.wait_for(timeout=MS)
        assert lesson.locator(".rp-kind").inner_text().lower() == "lesson"
        assert "matches the work" in lesson.locator(".rp-because").inner_text()
        assert not writes, writes
        assert not errors, errors
        browser.close()


# -- 4. from a Persona's own page; Escape; focus ------------------------------

def test_previewing_a_persona_from_its_record_and_escape_gives_focus_back(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p)
        _open(page, world, brain["conv"])
        page.goto(world["base"] + f"/quiet2?c={brain['conv']}&record={brain['persona']}")
        rec = page.locator(f'[data-record="{brain["persona"]}"]')
        rec.wait_for(timeout=MS)
        rec.get_by_role("button", name="More on this record").click()
        page.get_by_role("menuitem", name="Preview persona").click()
        sheet = page.locator("[data-receive-preview]")
        sheet.locator('[data-rp-group="persona"]').wait_for(timeout=MS)
        assert sheet.get_by_label("Persona it is started as").evaluate("el => el.selectedOptions[0].textContent") == "Steward"
        # focus is inside, and Tab stays inside
        assert page.evaluate("document.activeElement.closest('[data-receive-preview]') !== null")
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.closest('[data-receive-preview]') !== null")
        outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        assert outline != "none", outline         # focus is visible
        page.keyboard.press("Escape")
        sheet.wait_for(state="detached", timeout=MS)
        rec.wait_for(timeout=MS)                   # the record is still there underneath
        assert page.evaluate("document.activeElement !== document.body && document.activeElement.offsetParent !== null")

        # from the Brain's menu: the entry is gone by then, so focus returns to the Brain button
        sheet = _preview(page)
        page.keyboard.press("Escape")
        sheet.wait_for(state="detached", timeout=MS)
        assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Brain"
        assert not writes, writes
        assert not errors, errors
        browser.close()


# -- 5. a phone ---------------------------------------------------------------

def test_the_preview_fits_a_phone(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p, 390, 844)
        _open(page, world, brain["conv"])
        sheet = _preview(page)
        _as_steward(sheet)
        assert _no_sideways(page)
        box = sheet.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 391 and box["y"] + box["height"] <= 845
        assert sheet.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        row = sheet.locator(f'[data-entry="{brain["long"]}"] .rp-row')
        row.scroll_into_view_if_needed()
        assert row.bounding_box()["height"] >= 44          # a finger can hit it
        row.click()
        text = sheet.locator(f'[data-entry="{brain["long"]}"] [data-rp-text]')
        tb = text.bounding_box()
        assert tb["x"] >= 0 and tb["x"] + tb["width"] <= 391
        assert _no_sideways(page) and sheet.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        sheet.get_by_role("button", name="Close", exact=True).click()
        sheet.wait_for(state="detached", timeout=MS)
        assert not writes, writes
        assert not errors, errors
        browser.close()


# -- 6. legacy Fluid keeps its own sheet --------------------------------------

def test_the_legacy_fluid_sheet_still_opens(world, brain):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors, writes = _page(p)
        page.context.set_extra_http_headers(owner_headers())
        page.goto(world["base"] + "/fluid?gov=1")
        page.get_by_role("button", name="See what an agent will receive").first.click(timeout=MS)
        sheet = page.locator('[data-testid="compose-preview"]')
        sheet.wait_for(timeout=MS)
        assert "What would compose now" in sheet.inner_text()      # Fluid's own words, untouched
        sheet.get_by_label("Started as (Persona)").select_option(label="Steward")
        sheet.locator(".fg-pv-item").first.wait_for(timeout=MS)
        assert "would receive" in sheet.inner_text().lower()
        assert page.locator("[data-receive-preview]").count() == 0
        assert not errors, errors
        browser.close()
