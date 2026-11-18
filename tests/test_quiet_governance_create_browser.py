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


# -- the four Kinds with a workspace of their own (`R2Shaped.tsx`) -----------
#
# Decision, Workflow, Discipline and Conversation Instruction are laid out
# around their own job, with the record beside the writing and creation in
# that preview: no step bar and no review step. Every other Kind keeps the
# generic step flow, which is what the `rule`-driven tests below still drive.

SHAPED = ("decision", "workflow", "discipline", "conversation-instruction")
MENU = {"decision": "Rule, decision or lesson", "workflow": "Workflow",
        "discipline": "Discipline",
        "conversation-instruction": "Instruction for a conversation"}


def _open_shaped(page, kind):
    _open_new(page, MENU[kind])
    if kind == "decision":  # the rules section opens on its first Kind
        _kind_select(page).select_option("decision")
    page.locator(".r2-create-shaped").wait_for(timeout=APPEARS_MS)


def _create(page):
    """The primary action where this layout puts it: beside the preview."""
    page.locator(".r2c-commitbox .r2-primary").click()


def _open_settings(page):
    """Reach, standing and supporting material are folded away until wanted."""
    page.locator(".r2c-placement > summary").click()


def _preview(page):
    return page.locator("#r2c-preview .r2c-record")


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
            _open_shaped(page, "discipline")
            _field(page, "name").fill("Fixture discipline")
            _field(page, "about").fill("Browser fixture tests")
            _field(page, "text").fill("Do the bounded thing and report it.")
            # the declared `list` input, as the practice reads it: rows
            _dialog(page).get_by_role("button", name="+ Add tool").click()
            _field(page, "Tools it uses 1").fill("git")
            page.get_by_role("checkbox", name="discover").check()
            assert page.get_by_role("checkbox", name="discover").is_checked()
            _open_settings(page)
            # Initial status defaults to proposed (standing_apt True, entry door)
            status = page.get_by_label("Initial status")
            assert status.input_value() == "proposed"
            assert not errors, errors
        finally:
            browser.close()


def test_generic_persona_instruction_defaults_and_api_bodies_unchanged(world, conv, me_id):
    """NOTHING IS ESTABLISHED BY DEFAULT (Quiet UI audit 2026-11-18, Defect 7):
    the generic entry door, the Persona door and the Instruction door all
    start at "Keep proposed", and each door is sent the matching value --
    read here from the real network request, not asserted from source text.
    Establishing stays an explicit choice ("Initial status")."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            # Persona: starts proposed like every Kind standing applies to, so
            # its door is sent `propose: true` unless the owner chooses to
            # establish.
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
            assert persona_req.get("body", {}).get("propose") is True, persona_req
            assert persona_req["body"]["attributed_to"] == me_id

            # Instruction: the same default, proposed; its Conversation is
            # chosen first and visibly, not behind a step.
            _open_quiet2(page, world)
            _open_shaped(page, "conversation-instruction")
            _field(page, "text").fill("Say so plainly.")
            _field(page, "Creation conversation").select_option(conv)
            instr_req = {}

            def _capture_instr(r):
                if "/instructions" in r.url and r.method == "POST":
                    instr_req["body"] = r.post_data_json
            page.on("request", _capture_instr)
            _create(page)
            page.wait_for_timeout(1500)
            assert instr_req.get("body", {}).get("establish") is False, instr_req
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
            # Decision has a workspace of its own, so the discard is checked
            # on that layout too: the same one question cleared it.
            page.locator(".r2-create-shaped").wait_for(timeout=APPEARS_MS)
            assert _field(page, "text").input_value() == ""

            # Back to a Kind on the generic step flow for the rest: what is
            # being checked here is the post-creation guard, which is the
            # same code on both layouts.
            _kind_select(page).select_option("rule")

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
            _open_shaped(page, "discipline")
            _field(page, "name").fill("Busy case")
            _field(page, "about").fill("busy")
            _field(page, "text").fill("While recording.")
            _create(page)
            # now busy: the way out is disabled and Escape must do nothing
            assert _dialog(page).get_by_role("button", name="Close creation").is_disabled()
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
            _open_shaped(page, "discipline")
            _field(page, "name").fill("Attribution case")
            _field(page, "about").fill("attribution")
            _field(page, "text").fill("Say who wrote it.")
            _create(page)
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
            _open_shaped(page, "discipline")
            _field(page, "name").fill("No owner case")
            _field(page, "about").fill("no-owner")
            _field(page, "text").fill("Should not record.")
            primary = page.locator(".r2c-commitbox .r2-primary")
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
    """The generic step flow, on a Kind that has no workspace of its own."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        for width, height in ((1440, 1000), (375, 800)):
            browser, page, errors = _page(p, width=width, height=height)
            try:
                _open_quiet2(page, world)
                _open_new(page, "Rule, decision or lesson")
                _kind_select(page).select_option("rule")
                dialog = page.locator(".r2-form")
                box = dialog.bounding_box()
                assert box is not None
                assert box["width"] <= width + 1, (width, box)
                assert page.locator(".r2-create-steps").is_visible()
                assert _dialog(page).get_by_role("button", name="Continue").is_visible()
                assert not errors, errors
            finally:
                browser.close()


# -- 8. the four shaped workspaces -------------------------------------------

def test_each_shaped_kind_opens_its_own_layout_with_a_live_preview(world, conv, me_id):
    """Each of the four opens the layout built for its own job, keeps the
    record as it will read beside the writing, updates that record while the
    person types, and offers creation there -- with no step bar and no
    separate review step anywhere."""
    playwright = pytest.importorskip("playwright.sync_api")
    marks = {
        "decision": (".r2c-short-layout", "text"),
        "workflow": (".r2c-tabs", "name"),
        "discipline": (".r2c-practice-grid", "name"),
        "conversation-instruction": (".r2c-instruction-context", "text"),
    }
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            for kind in SHAPED:
                own, field = marks[kind]
                _open_quiet2(page, world)
                _open_shaped(page, kind)
                assert page.locator(own).is_visible(), f"{kind} must open its own layout"
                # no step bar and no review step on these four
                assert page.locator(".r2-create-steps").count() == 0, kind
                assert _dialog(page).get_by_role("button", name="Continue").count() == 0, kind

                typed = f"A live {kind} being written"
                _field(page, field).fill(typed)
                assert typed in _preview(page).inner_text(), f"{kind} preview must follow the typing"
                _field(page, field).fill(typed + ", changed")
                assert typed + ", changed" in _preview(page).inner_text(), kind

                # creation is beside that preview, not behind a review step
                create = page.locator(".r2c-commitbox .r2-primary")
                assert create.is_visible() and kind.replace("-", " ") in create.inner_text().lower()
                # and it uses the width: writing left, record right
                ed = page.evaluate("document.querySelector('.r2c-editor').getBoundingClientRect()")
                pv = page.evaluate("document.querySelector('.r2c-previewcol').getBoundingClientRect()")
                assert ed["right"] <= pv["left"], (kind, ed, pv)

                _dialog(page).get_by_role("button", name="Close creation").click()
                _guard(page).get_by_role("button", name="Discard draft").click()
            assert not errors, errors
        finally:
            browser.close()


def test_workflow_sequence_adds_reorders_and_removes_with_its_own_question(world, conv, me_id):
    """The hard part, and why the layout exists: an ordered activity list
    beside the activity being edited. Adding, moving and removing must keep
    every part of every activity -- its own participant and Persona
    included -- and the record preview must follow the same order. Removing
    one is asked about, and the question says the others keep their order."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _open_quiet2(page, world)
            _open_shaped(page, "workflow")
            page.get_by_role("button", name=re.compile(r"^Activities")).click()

            for key, what in (("orient", "Orient and read what governs the work."),
                              ("record", "Record the request with its expectation."),
                              ("build", "Build the part on its own branch.")):
                _dialog(page).get_by_role("button", name="+ Add activity").first.click()
                _field(page, "activity what").fill(what)
                _field(page, "activity key").fill(key)
            assert page.locator(".r2c-sequence li").count() == 3

            # each activity carries its own participant and Persona
            _field(page, "activity participant").select_option(index=1)
            _field(page, "activity persona").select_option(index=1)
            who = _field(page, "activity participant").input_value()
            assert who, "an activity must be able to carry its own participant"

            def order():
                return [b.inner_text().split("\n")[-1]
                        for b in page.locator(".r2c-sequence li button").all()]

            def shown():
                """The record reads the whole activity; the sequence beside it
                reads a short title, so they are compared by that title."""
                return [li.inner_text().split("\n")[0].rstrip(".")
                        for li in page.locator("#r2c-preview .r2c-activities > li").all()]

            before = order()
            assert shown() == before, (shown(), before)

            # MOVE UP: the selected activity keeps everything and changes place
            page.get_by_role("button", name="↑ Move up").click()
            assert order() == [before[0], before[2], before[1]], order()
            assert shown() == order(), "the record must read in the new order"
            assert _field(page, "activity key").input_value() == "build"
            assert _field(page, "activity participant").input_value() == who

            # MOVE DOWN puts it back, still whole
            page.get_by_role("button", name="↓ Move down").click()
            assert order() == before
            assert _field(page, "activity key").input_value() == "build"
            assert _field(page, "activity participant").input_value() == who

            # REMOVING ONE IS ASKED ABOUT, and cancelling keeps all of it
            page.get_by_role("button", name="Remove activity").first.click()
            ask = page.locator(".r2c-remove-guard")
            ask.wait_for(timeout=APPEARS_MS)
            assert "keep their order" in ask.inner_text()
            ask.get_by_role("button", name="Keep activity").click()
            page.locator(".r2c-remove-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert page.locator(".r2c-sequence li").count() == 3
            assert _field(page, "activity key").input_value() == "build"

            # confirming removes exactly that one, the others keeping order
            page.get_by_role("button", name="Remove activity").first.click()
            page.locator(".r2c-remove-guard").get_by_role("button", name="Remove activity").click()
            page.locator(".r2c-remove-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert page.locator(".r2c-sequence li").count() == 2
            assert order() == before[:2]
            assert shown() == before[:2]
            assert not errors, errors
        finally:
            browser.close()


def test_shaped_draft_protection_keeps_part_written_activities_and_list_rows(world, conv, me_id):
    """The protection that has been fought for twice. On every shaped Kind,
    closing with an unfinished record raises the separate readable warning,
    and Keep editing returns to everything typed. An activity or a list row
    that was added and not yet written is still a draft to protect."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            # every shaped Kind raises the readable warning, and keeps it all
            for kind in SHAPED:
                field = "text" if kind in ("decision", "conversation-instruction") else "name"
                _open_quiet2(page, world)
                _open_shaped(page, kind)
                _field(page, field).fill(f"Half-written {kind}")
                _dialog(page).get_by_role("button", name="Close creation").click()
                g = _guard(page)
                assert "Discard this draft?" in g.inner_text(), kind
                assert g.get_by_role("button", name="Keep editing").count() == 1, kind
                assert g.get_by_role("button", name="Discard draft").count() == 1, kind
                g.get_by_role("button", name="Keep editing").click()
                page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
                assert _field(page, field).input_value() == f"Half-written {kind}", kind
                _dialog(page).get_by_role("button", name="Close creation").click()
                _guard(page).get_by_role("button", name="Discard draft").click()

            # AN EMPTY ADDED ACTIVITY IS A DRAFT: nothing was typed into it,
            # and it is still something the person would lose.
            _open_quiet2(page, world)
            _open_shaped(page, "workflow")
            page.get_by_role("button", name=re.compile(r"^Activities")).click()
            _dialog(page).get_by_role("button", name="+ Add activity").first.click()
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            assert "Discard this draft?" in g.inner_text()
            g.get_by_role("button", name="Keep editing").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert page.locator(".r2c-sequence li").count() == 1

            # a part-written activity, and the one being edited, survive it
            _field(page, "activity what").fill("Part-written, not finished")
            _dialog(page).get_by_role("button", name="+ Add activity").first.click()
            _field(page, "activity key").fill("second")
            page.keyboard.press("Escape")
            g = _guard(page)
            g.get_by_role("button", name="Keep editing").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert page.locator(".r2c-sequence li").count() == 2
            assert _field(page, "activity key").input_value() == "second", "the selected activity must survive"
            page.locator(".r2c-sequence li button").first.click()
            assert _field(page, "activity what").input_value() == "Part-written, not finished"
            _dialog(page).get_by_role("button", name="Close creation").click()
            _guard(page).get_by_role("button", name="Discard draft").click()

            # AN EMPTY ADDED LIST ROW IS A DRAFT TOO
            _open_quiet2(page, world)
            _open_shaped(page, "discipline")
            _dialog(page).get_by_role("button", name="+ Add tool").click()
            _dialog(page).get_by_role("button", name="Close creation").click()
            g = _guard(page)
            assert "Discard this draft?" in g.inner_text()
            g.get_by_role("button", name="Keep editing").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            row = _field(page, "Tools it uses 1")
            assert row.count() == 1, "the added row must still be there"
            row.fill("git")
            _dialog(page).get_by_role("button", name="+ Add tool").click()
            _field(page, "Tools it uses 2").fill("pytest")
            page.keyboard.press("Escape")
            _guard(page).get_by_role("button", name="Keep editing").click()
            page.locator(".r2-create-guard").wait_for(state="hidden", timeout=APPEARS_MS)
            assert _field(page, "Tools it uses 1").input_value() == "git"
            assert _field(page, "Tools it uses 2").input_value() == "pytest"
            assert "pytest" in _preview(page).inner_text()
            assert not errors, errors
        finally:
            browser.close()


def test_shaped_layout_uses_the_width_and_falls_back_to_one_column(world, conv, me_id):
    """1440 and 1024 keep the writing and the record side by side; 375 is one
    column, writing before the record, with the jump links between them."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        for width, height in ((1440, 1000), (1024, 900), (375, 800)):
            browser, page, errors = _page(p, width=width, height=height)
            try:
                _open_quiet2(page, world)
                _open_shaped(page, "workflow")
                assert page.evaluate("document.documentElement.scrollWidth") <= width + 1, width
                ed = page.evaluate("document.querySelector('.r2c-editor').getBoundingClientRect()")
                pv = page.evaluate("document.querySelector('.r2c-previewcol').getBoundingClientRect()")
                if width >= 1024:
                    assert ed["right"] <= pv["left"], (width, ed, pv)
                else:
                    assert pv["top"] >= ed["bottom"], (width, ed, pv)
                    assert page.locator(".r2c-mobilebar").is_visible()
                    assert page.get_by_role("button", name="Live preview ↓").is_visible()
                assert page.locator(".r2c-commitbox .r2-primary").is_visible(), width
                assert not errors, errors
            finally:
                browser.close()

