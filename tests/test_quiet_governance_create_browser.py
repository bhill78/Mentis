"""THE REAL QUIET GOVERNANCE CREATION JOURNEY, in a real browser.

Builder fixture/harness tests for the Quiet governance creation form added at
a0ecc98bb0e8f3d804a8e2e09f3f69e3aa8b134f (`R2Forms.tsx`'s `quiet` variant,
hosted by `quiet2/brain/BrainPages.tsx`'s `NewRecord`). This exercises the
ACTUAL components -- no recreated mock form, no source-text assertion -- by
driving the real built Quiet Chat (`/quiet2`) against a real HTTP server
backed by a disposable fixture Brain (`tests/_loop.py`'s `world`, the same
infrastructure `test_quiet_refresh_browser.py` uses). No live Brain, no MARS.

Reached the way a reader reaches it: the rail's Brain icon, its "Make,
import, preview" menu, a Kind's own creation choice -- never a shortcut URL
into the form, so BrainPages' `useUnfinished`/`leaving.ts` seam is exercised
exactly as Quiet Chat wires it.

Scope (per the bounded request this answers): dynamic Kind fields/widgets and
unchanged generic/persona/instruction status defaults; the real
create -> cite -> establish -> place ordering; failed citation, failed
establishment and failed placement each retrying the original identity with
no duplicate writes and a truthful remaining-acts readout; the Quiet-only
Cancel/Close/Escape/kind-change guard (one question, every field kept,
cleared only on a deliberate discard, never offered again after creation);
the busy guard blocking a background Escape; the default (non-Quiet) host
left unchanged; and a compact-rendering check at a normal and a narrow
width. Chrome only, per the owner's own browser -- no other engine, no full
suite.

Build apps/fluid-web first (`npm ci && npm run build` under apps/fluid-web),
then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import mentis.api as mapi
from mentis.web import _Handler, _State
from tests._loop import world, post, get  # noqa: F401
from tests.conftest import OWNER_PASSPHRASE  # the suite's real owner passphrase

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

ENGINE = "chrome"  # the owner's own browser; no other engine here
APPEARS_MS = 15000


@pytest.fixture
def world_no_owner(tmp_path):
    """A real fixture Brain with no Participant at all, so `MeProvider`
    (`identity.tsx`) resolves `me` to null exactly as it would for an
    unadopted or freshly created Brain -- not a mock, the same server and
    `_State`/`_Handler` the `world` fixture uses, just without
    `fixture.build`'s demo participants."""
    root = tmp_path / "corpus_no_owner"
    mapi.create_corpus(str(root))
    state = _State(str(root))
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}", "state": state}
    finally:
        httpd.shutdown()


# -- real fixture state, never a mock form -----------------------------------

@pytest.fixture
def me_id(world):
    """The participant Quiet Chat's `useMe()` will actually resolve to, by
    the same route it calls (`/api/participants?limit=1`)."""
    rows = get(world, "/api/participants?limit=1")["participants"]
    assert rows, "the fixture Brain must hold at least one participant"
    return rows[0]["participant"]


@pytest.fixture
def conv(world):
    return post(world, "/api/conversations", {"name": "Governance creation browser"})["conversation"]


@pytest.fixture
def basis_note(world, me_id):
    """A held entry to cite as supporting material."""
    r = post(world, "/api/entries", {
        "kind": "note", "body": {"text": "A note held to be cited."},
        "attributed_to": me_id, "establish": False,
    })
    return r["entry"]


def _page(playwright, width=1440, height=1000):
    browser = playwright.chromium.launch(channel=ENGINE)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return browser, page, errors


def _log_in_as_owner(page, world):
    """The real owner login door (`/api/owner/login`), from the browser
    itself: the Quiet Chat form's writes are OWNER operations and the real
    server refuses every one of them without a live owner session -- a
    bearer token minted for the Python test process (`tests/conftest.py`)
    never reaches a browser request, so the browser logs in for itself,
    exactly as a reader would."""
    import json as _json
    r = page.request.post(world["base"] + "/api/owner/login",
                           headers={"X-Mentis-Client": "1", "Content-Type": "application/json"},
                           data=_json.dumps({"passphrase": OWNER_PASSPHRASE}))
    assert r.ok, (r.status, r.text())


def _open_quiet2(page, world):
    _log_in_as_owner(page, world)
    page.goto(world["base"] + "/quiet2")
    page.get_by_role("button", name="Brain", exact=True).wait_for(timeout=APPEARS_MS)


def _open_new(page, section_label):
    """The real path to the creation form: Brain icon -> menu -> a Kind's
    own creation choice. Never a shortcut into `R2Create`."""
    page.get_by_role("button", name="Brain", exact=True).click()
    page.get_by_role("button", name="Make, import, preview").click()
    page.get_by_role("menuitem", name=re.compile(section_label)).click()
    page.locator(".r2-form").wait_for(timeout=APPEARS_MS)


def _dialog(page):
    """The creation form itself, scoped against BrainBrowser's own unrelated
    `aria-label="Kind"` filter (its card stays mounted, hidden, behind it)."""
    return page.locator(".r2-form")


def _field(page, key):
    return _dialog(page).get_by_label(key, exact=True)


def _kind_select(page):
    return _dialog(page).get_by_label("Kind", exact=True)


def _continue(page):
    _dialog(page).get_by_role("button", name="Continue").click()


def _submit(page):
    page.locator(".r2-actions .r2-primary").last.click()


def _guard(page):
    g = page.locator(".r2-create-guard")
    g.wait_for(timeout=APPEARS_MS)
    return g


def _created_id_from_error(page) -> str:
    err = page.locator(".r2-error").inner_text()
    m = re.search(r"Created (ent-[0-9a-f]+)", err)
    assert m, f"no created id in error text: {err!r}"
    return m.group(1)


# -- 1. dynamic Kind fields/widgets, and unchanged defaults -------------------

def test_dynamic_kind_fields_and_widgets(world, conv, me_id):
    """`discipline` declares a `form`: a line, a paragraph, a list and a
    capabilities checkbox set. The builder reads that declaration and
    nothing else, so each of those widgets must actually render and accept
    input through the real component."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _open_quiet2(page, world)
            _open_new(page, "Discipline")
            _field(page, "name").fill("Fixture discipline")
            _field(page, "about").fill("Browser fixture tests")
            _field(page, "text").fill("Do the bounded thing and report it.")
            page.get_by_role("checkbox", name="discover").check()
            assert page.get_by_role("checkbox", name="discover").is_checked()
            _continue(page)
            # Initial status defaults to proposed (standing_apt True, entry door)
            status = page.get_by_label("Initial status")
            assert status.input_value() == "proposed"
            assert not errors, errors
        finally:
            browser.close()


def test_generic_persona_instruction_defaults_and_api_bodies_unchanged(world, conv, me_id):
    """Quiet presentation is additive only: the generic entry door's
    establish default, and the Persona and Instruction doors' own
    propose/establish default, must be exactly what the non-Quiet form has
    always sent -- read here from the real network request, not asserted
    from source text."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            # Persona: door starts proposed=false (startsProposed only applies
            # to the generic entry door), so it establishes by default.
            _open_quiet2(page, world)
            _open_new(page, "Persona")
            _field(page, "name").fill("Fixture persona")
            _field(page, "behaviour").fill("Answer briefly.")
            _continue(page)
            persona_req = {}

            def _capture_persona(r):
                if r.url.endswith("/api/personas") and r.method == "POST":
                    persona_req["body"] = r.post_data_json
            page.on("request", _capture_persona)
            _continue(page)
            _submit(page)
            page.wait_for_timeout(1500)
            assert persona_req.get("body", {}).get("propose") is False, persona_req
            assert persona_req["body"]["attributed_to"] == me_id

            # Instruction: same default-establish door; needs a destination.
            _open_quiet2(page, world)
            _open_new(page, "Instruction for a conversation")
            _field(page, "text").fill("Say so plainly.")
            _continue(page)
            _field(page, "Creation conversation").select_option(conv)
            instr_req = {}

            def _capture_instr(r):
                if "/instructions" in r.url and r.method == "POST":
                    instr_req["body"] = r.post_data_json
            page.on("request", _capture_instr)
            _continue(page)
            _submit(page)
            page.wait_for_timeout(1500)
            assert instr_req.get("body", {}).get("establish") is True, instr_req
            assert instr_req["body"]["attributed_to"] == me_id
            assert not errors, errors
        finally:
            browser.close()


# -- 2. create -> cite -> establish -> place, real ordering -------------------

def test_create_cite_establish_place_ordering(world, conv, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            calls: list[str] = []
            page.on("request", lambda r: calls.append(r.url) if r.method == "POST" and "/api/" in r.url else None)
            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Say what is true.")
            _field(page, "about").fill("ordering")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("It supports this.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Belongs here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            order = [u for u in calls if "/api/entries" in u]
            assert re.search(r"/api/entries$", order[0])
            assert re.search(r"/derive-from$", order[1])
            assert re.search(r"/establish$", order[2])
            assert re.search(r"/place$", order[3])
            assert not errors, errors
        finally:
            browser.close()


# -- 3. failed citation / establishment / placement: identity kept, no dup ---

def test_failed_citation_retries_original_identity(world, conv, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            create_posts: list[str] = []
            page.on("request", lambda r: create_posts.append(r.url)
                    if r.method == "POST" and re.search(r"/api/entries$", r.url) else None)
            failed = {"n": 0}

            def maybe_fail_derive(route):
                if "/derive-from" in route.request.url and failed["n"] == 0:
                    failed["n"] += 1
                    route.abort()
                else:
                    route.continue_()
            page.route("**/api/entries/*/derive-from", maybe_fail_derive)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Retry case.")
            _field(page, "about").fill("retry")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("Supports it.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator(".r2-error").wait_for(timeout=APPEARS_MS)
            first_id = _created_id_from_error(page)
            assert len(create_posts) == 1, create_posts

            # TRUTHFUL REMAINING PROGRESS: the Cancel guard, mid-failure.
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            assert first_id in g.inner_text()
            assert "citation" in g.inner_text()
            g.get_by_role("button", name="Keep editing").click()

            # Retry: derive-from now succeeds, and the rest follows through.
            _dialog(page).get_by_role("button", name="Retry remaining acts").click()
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            assert len(create_posts) == 1, "a retry must never create a second identity"
        finally:
            browser.close()


def test_failed_establishment_retries_original_identity(world, conv, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            create_posts: list[str] = []
            page.on("request", lambda r: create_posts.append(r.url)
                    if r.method == "POST" and re.search(r"/api/entries$", r.url) else None)
            failed = {"n": 0}

            def maybe_fail(route):
                if "/establish" in route.request.url and failed["n"] == 0:
                    failed["n"] += 1
                    route.abort()
                else:
                    route.continue_()
            page.route("**/api/entries/*/establish", maybe_fail)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Establish retry case.")
            _field(page, "about").fill("retry-establish")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("Supports it.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator(".r2-error").wait_for(timeout=APPEARS_MS)
            first_id = _created_id_from_error(page)

            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            text = g.inner_text()
            assert first_id in text
            # citation already completed; only establishment (and placement) remain
            assert "citation" not in text.split("Remaining:")[1].split(".")[0]
            assert "establishment" in text
            g.get_by_role("button", name="Keep editing").click()

            _dialog(page).get_by_role("button", name="Retry remaining acts").click()
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            assert len(create_posts) == 1
        finally:
            browser.close()


def test_failed_placement_retries_original_identity(world, conv, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            create_posts: list[str] = []
            page.on("request", lambda r: create_posts.append(r.url)
                    if r.method == "POST" and re.search(r"/api/entries$", r.url) else None)
            failed = {"n": 0}

            def maybe_fail(route):
                if "/place" in route.request.url and failed["n"] == 0:
                    failed["n"] += 1
                    route.abort()
                else:
                    route.continue_()
            page.route("**/api/entries/*/place", maybe_fail)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Placement retry case.")
            _field(page, "about").fill("retry-place")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("Supports it.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator(".r2-error").wait_for(timeout=APPEARS_MS)
            first_id = _created_id_from_error(page)

            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            text = g.inner_text()
            remaining = text.split("Remaining:")[1].split(".")[0]
            assert "placement" in remaining and "citation" not in remaining and "establishment" not in remaining
            g.get_by_role("button", name="Keep editing").click()

            _dialog(page).get_by_role("button", name="Retry remaining acts").click()
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            assert len(create_posts) == 1
        finally:
            browser.close()


# -- 4. Quiet Cancel/Close/Escape/kind-change: one question, state kept ------

def test_quiet_guard_one_question_keeps_state_resets_only_on_discard(world, conv, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            # Creation leaves the record "Created; finish remaining acts" only
            # while something has not completed -- force that by failing the
            # placement once, so the post-creation guard has something real
            # to show (a single successful write calls `onDone` at once).
            def fail_place_once(route):
                if failed["n"] == 0:
                    failed["n"] += 1
                    route.abort()
                else:
                    route.continue_()
            failed = {"n": 0}
            page.route("**/api/entries/*/place", fail_place_once)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Kept across a cancel.")

            # Close (x): one guard, Keep editing preserves the field.
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            assert "Discard this draft?" in g.inner_text()
            g.get_by_role("button", name="Keep editing").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert _field(page, "text").input_value() == "Kept across a cancel."

            # Escape opens the same guard; Escape again dismisses it (not a leave).
            page.keyboard.press("Escape")
            _guard(page)
            page.keyboard.press("Escape")
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert _field(page, "text").input_value() == "Kept across a cancel."

            # Kind change with unsaved state: one guard; Keep editing changes nothing.
            _kind_select(page).select_option("decision")
            g = _guard(page)
            g.get_by_role("button", name="Keep editing").click()
            assert _kind_select(page).input_value() == "rule"
            assert _field(page, "text").input_value() == "Kept across a cancel."

            # Discarding the kind change clears every mutable field, once.
            _kind_select(page).select_option("decision")
            g = _guard(page)
            g.get_by_role("button", name="Discard draft").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert _kind_select(page).input_value() == "decision"
            assert _field(page, "text").input_value() == ""

            # Create the record (placement fails once, so it stops "Created;
            # finish remaining acts" rather than finishing at once), then
            # Cancel: no discard is offered after creation.
            _field(page, "text").fill("Now recorded.")
            _field(page, "about").fill("post-create-guard")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("Supports it.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator(".r2-error").wait_for(timeout=APPEARS_MS)
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            assert "Created ent-" in g.inner_text()
            assert g.get_by_role("button", name="Discard draft").count() == 0
            g.get_by_role("button", name="Inspect created record").click()
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            assert not errors, errors
        finally:
            browser.close()


# -- 5. the pending (busy) guard blocks a background Escape -------------------

def test_pending_guard_blocks_background_escape_and_resubmit(world, conv, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            entries_posted = {"n": 0}

            def slow_create(route):
                if route.request.method == "POST":
                    entries_posted["n"] += 1
                    page.wait_for_timeout(1200)
                route.continue_()
            page.route("**/api/entries", slow_create)

            _open_quiet2(page, world)
            _open_new(page, "Discipline")
            _field(page, "name").fill("Busy case")
            _field(page, "about").fill("busy")
            _field(page, "text").fill("While recording.")
            _continue(page)
            _continue(page)
            page.locator(".r2-actions .r2-primary").last.click()
            # now busy: Cancel is disabled and Escape must do nothing
            assert _dialog(page).get_by_role("button", name="Cancel").is_disabled()
            page.keyboard.press("Escape")
            assert page.locator(".r2-create-guard").count() == 0
            assert page.locator(".r2-form").count() == 1
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            assert entries_posted["n"] == 1, "busy must block a second submission"
            assert not errors, errors
        finally:
            browser.close()


# -- 6. readonly/attribution and the default (non-Quiet) host -----------------

def test_attribution_is_the_resolved_participant(world, conv, me_id):
    """Not just that the write succeeds: the real network body the real
    component sent must carry the resolved owner and the typed fields,
    read from the request itself, never assumed from success alone."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            captured: dict = {}

            def _capture(r):
                if r.method == "POST" and re.search(r"/api/entries$", r.url):
                    captured["body"] = r.post_data_json
            page.on("request", _capture)

            _open_quiet2(page, world)
            _open_new(page, "Discipline")
            _field(page, "name").fill("Attribution case")
            _field(page, "about").fill("attribution")
            _field(page, "text").fill("Say who wrote it.")
            _continue(page)
            _continue(page)
            _submit(page)
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            page.wait_for_timeout(500)
            assert captured.get("body"), "no /api/entries write was captured"
            body = captured["body"]
            assert body["attributed_to"] == me_id
            assert body["kind"] == "discipline"
            assert body["body"]["name"] == "Attribution case"
            assert body["body"]["about"] == "attribution"
            assert body["body"]["text"] == "Say who wrote it."
            assert not errors, errors
        finally:
            browser.close()


def test_no_participant_blocks_write_before_any_post(world_no_owner):
    """`MeProvider` resolves `me` to null on a Brain with no Participant.
    The real door's own gate -- the primary action itself is
    `disabled={busy || !me}` -- must refuse before any write reaches the
    network: the actual read-only/no-attributed-owner case, through the
    real component and a real fixture server, never a source-text
    assertion. (`write`'s own "An attributed owner is needed." message is
    unreachable through the UI while that button stays disabled; this
    test exercises the real, reachable gate.)"""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            posts: list[str] = []
            page.on("request", lambda r: posts.append(r.url)
                    if r.method == "POST" and "/api/" in r.url else None)

            _open_quiet2(page, world_no_owner)
            _open_new(page, "Discipline")
            _field(page, "name").fill("No owner case")
            _field(page, "about").fill("no-owner")
            _field(page, "text").fill("Should not record.")
            _continue(page)
            _continue(page)
            primary = page.locator(".r2-actions .r2-primary").last
            primary.wait_for(timeout=APPEARS_MS)
            assert primary.is_disabled(), "no attributed owner must disable the primary action"
            page.wait_for_timeout(500)  # nothing fires on its own either
            assert not any(re.search(r"/api/(entries|personas)$", u) or "/instructions" in u
                            for u in posts), posts
            assert not errors, errors
        finally:
            browser.close()


def test_failed_citation_edited_refs_show_truthful_progress_then_restore_keeps_identity(
    world, conv, me_id, basis_note,
):
    """A citation failure after a no-standing-on-creation write (a basis was
    given, so the create body sends `establish: false` regardless of
    status): editing the Supporting references afterwards -- to another id,
    then to empty -- must still leave the guard showing the created
    identity and the TRUTHFUL remaining acts, never claiming establishment
    happened on creation. Restoring the original reference and retrying
    keeps that same identity; nothing is created twice."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            entries_bodies: list[dict] = []
            page.on("request", lambda r: entries_bodies.append(r.post_data_json)
                    if r.method == "POST" and re.search(r"/api/entries$", r.url) else None)
            failed = {"n": 0}

            def maybe_fail_derive(route):
                if "/derive-from" in route.request.url and failed["n"] == 0:
                    failed["n"] += 1
                    route.abort()
                else:
                    route.continue_()
            page.route("**/api/entries/*/derive-from", maybe_fail_derive)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Edit then restore case.")
            _field(page, "about").fill("edit-restore")
            _field(page, "Supporting references").fill(basis_note)
            _field(page, "Derivation reason").fill("Supports it.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")
            _continue(page)
            _submit(page)
            page.locator(".r2-error").wait_for(timeout=APPEARS_MS)
            first_id = _created_id_from_error(page)
            assert len(entries_bodies) == 1, entries_bodies
            # a basis was given, so the generic door never establishes on creation
            assert entries_bodies[0]["establish"] is False

            # EDIT the supporting references to a different id: the local
            # (Close creation) leave must still read the real, truthful
            # remaining acts -- citation still pending, establishment and
            # placement still ahead, never "established on creation".
            _field(page, "Correct supporting references").fill("ent-doesnotexist")
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            text = g.inner_text()
            assert first_id in text
            assert "created as a proposal" in text.lower()
            assert "requested on creation" not in text.lower()
            remaining = text.split("Remaining:")[1].split(".")[0]
            assert "citation" in remaining and "establishment" in remaining and "placement" in remaining
            g.get_by_role("button", name="Keep editing").click()

            # EDIT again to empty: the external leave path (Escape) reads the
            # same truthful state, not stale text from before the edit.
            _field(page, "Correct supporting references").fill("")
            page.keyboard.press("Escape")
            g = _guard(page)
            text = g.inner_text()
            assert first_id in text
            assert "created as a proposal" in text.lower()
            assert "requested on creation" not in text.lower()
            g.get_by_role("button", name="Keep editing").click()

            # RESTORE the original reference, then retry: the identity from
            # the first attempt is kept, and the rest follows through.
            _field(page, "Correct supporting references").fill(basis_note)
            _dialog(page).get_by_role("button", name="Retry remaining acts").click()
            page.locator('[data-brain-page="record"]').wait_for(timeout=APPEARS_MS)
            assert len(entries_bodies) == 1, "a retry must never create a second identity"
            assert not errors, errors
        finally:
            browser.close()


def test_leave_guard_keyboard_decides_once_and_keeps_every_value(world, conv, me_id):
    """Opening the leave question with Escape while the step's own primary
    action (Continue) holds focus; the guard's own "Keep editing" carries
    `autoFocus`, so Enter and Space must activate it (never a background
    submission or a silent reset), Tab must only move focus among the
    guard's own buttons without deciding anything, and every field, the
    chosen status and the current step survive -- the decision applies
    exactly once per Escape."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            posts: list[str] = []
            page.on("request", lambda r: posts.append(r.url)
                    if r.method == "POST" and "/api/" in r.url else None)

            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Kept through keyboard leave.")
            _field(page, "about").fill("keyboard-leave")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _field(page, "Creation conversation").select_option(conv)
            _field(page, "Placement reason").fill("Here.")
            _field(page, "Initial status").select_option("force")

            # Focus the step's own primary action, as a reader tabbing
            # through the form would, before asking to leave.
            _dialog(page).get_by_role("button", name="Continue").focus()
            page.keyboard.press("Escape")
            g = _guard(page)
            assert "Discard this draft?" in g.inner_text()
            # Enter activates the focused "Keep editing" -- not a submit.
            page.keyboard.press("Enter")
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert not posts, "Keep editing must never submit anything in the background"
            current_step = page.locator(".r2-create-steps [aria-current='step']").inner_text()
            assert "2" in current_step and "Reach & status" in current_step, current_step
            assert _field(page, "Where it reaches").input_value() == "placed"
            assert _field(page, "Initial status").input_value() == "force"

            # Back to step 1: the typed fields were never reset either.
            _dialog(page).get_by_role("button", name="Back").click()
            assert _field(page, "text").input_value() == "Kept through keyboard leave."
            assert _field(page, "about").input_value() == "keyboard-leave"
            _continue(page)

            # Escape again; this time Space activates the same focused
            # "Keep editing" -- same one decision, no discard, no submit.
            page.keyboard.press("Escape")
            _guard(page)
            page.keyboard.press("Space")
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert not posts
            assert _field(page, "Where it reaches").input_value() == "placed"

            # Escape a third time; Tab only moves focus among the guard's
            # own buttons -- it must decide nothing, and a second Escape
            # dismisses the still-open guard rather than leaving.
            page.keyboard.press("Escape")
            g = _guard(page)
            page.keyboard.press("Tab")
            assert page.locator(".r2-create-guard").count() == 1, "Tab must not have decided anything"
            page.keyboard.press("Escape")
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert not posts
            assert _field(page, "Where it reaches").input_value() == "placed"
            assert _field(page, "Initial status").input_value() == "force"
            assert not errors, errors
        finally:
            browser.close()


def test_default_non_quiet_host_unchanged(world, conv, me_id):
    """GovPage hosts the SAME `R2Create`, `quiet` unset: no step bar, no
    new guard -- cancelling with unsaved text goes at once, exactly as
    before this work."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _log_in_as_owner(page, world)
            page.goto(world["base"] + "/fluid?gov=1&s=rules")
            page.get_by_role("button", name=re.compile("Record a rule or decision")).click()
            page.locator(".fg-create .r2-form").wait_for(timeout=APPEARS_MS)
            assert page.locator(".r2-create-steps").count() == 0
            _field(page, "text").fill("Unsaved, non-Quiet.")
            _dialog(page).get_by_role("button", name="Close creation").click()
            # no Quiet guard exists on this host at all
            assert page.locator(".r2-create-guard").count() == 0
            assert not errors, errors
        finally:
            browser.close()


# -- 7. compact rendering, normal and narrow -----------------------------------

def test_compact_rendering_normal_and_narrow(world, conv, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        for width, height in ((1440, 1000), (375, 800)):
            browser, page, errors = _page(p, width=width, height=height)
            try:
                _open_quiet2(page, world)
                _open_new(page, "Rule, decision or lesson")
                dialog = page.locator(".r2-form")
                box = dialog.bounding_box()
                assert box is not None
                assert box["width"] <= width + 1, (width, box)
                assert page.locator(".r2-create-steps").is_visible()
                assert _dialog(page).get_by_role("button", name="Continue").is_visible()
                assert not errors, errors
            finally:
                browser.close()

