"""Track 3 correction: existing controls, compact presentation, fixture Brain.

The owner's later request supersedes the old always-visible action explanation
and side-by-side run cards. No MARS or live Brain is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mentis.conversation import text
from mentis.execution import FakeExecution
from tests._loop import world  # noqa: F401
from tests.test_quiet_activity_browser import _open_run, _requested

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)


def _conversation(world):
    cv, owner, vera = world["cv"], world["who"]["@brian"], world["who"]["@Vera"]
    here = cv.open_conversation("Track 3 fixture", about="Quiet Chat correction")
    cv.join(owner, here)
    cv.join(vera, here)
    for n in range(12):
        cv.say(here, owner, [text(f"A conversation with room to think. Post {n + 1}.")])
    return here


def _shot(page, name):
    destination = os.environ.get("MENTIS_TRACK3_EVIDENCE")
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=path / name)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [390, 1440])
def test_track3_composer_and_shared_settings_fit_and_preserve_the_dispatch(world, engine, width):
    playwright = pytest.importorskip("playwright.sync_api")
    world["state"].agents.execution = FakeExecution([
        {"id": "claude", "kind": "acp", "available": True, "reason": None,
         "version": "fixture", "models": [
             {"id": "opus", "name": "Opus"},
             {"id": "sonnet", "name": "Sonnet with a longer display name"},
         ], "efforts": ["high", "low"], "supports": {"mcp": ["stdio"]}},
    ])
    task_workspace = Path(world["root"]).parent / "workspace"
    task_workspace.mkdir()
    conversation = _conversation(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(world["base"] + f"/quiet#/c/{conversation}")
            field = page.get_by_label("Continue the conversation")
            field.wait_for()
            composer = page.locator(".qc-composer")
            composer.scroll_into_view_if_needed()
            assert composer.bounding_box()["height"] < 120
            assert page.locator(".qc-action-why").count() == 0
            _shot(page, f"track3-rest-{engine}-{width}.png")

            # The hidden tool row opens on both textbox and keyboard focus.
            field.focus()
            page.get_by_label("Posting action").wait_for(state="visible")
            assert page.get_by_label("Posting action").get_attribute("title")
            ask = page.get_by_label("Ask someone to work")
            ask.focus()
            ask.locator("option", has_text="Vera").wait_for(state="attached")
            ask.select_option(label="@Vera")
            page.get_by_title("Will be asked to work: open to choose runtime, model and effort").click()
            settings = page.get_by_role("region", name="Participant settings", exact=True)
            settings.get_by_role("button", name="claude", exact=True).click()
            settings.get_by_role("button", name="Opus", exact=True).click()
            settings.get_by_role("button", name="high", exact=True).click()

            # Shared runtime/model cascade: a new model drops the old effort.
            settings.get_by_role("button", name="Sonnet with a longer display name", exact=True).click()
            assert settings.get_by_role("button", name="the model's default", exact=True).get_attribute("aria-pressed") == "true"
            settings.get_by_role("button", name="low", exact=True).click()
            settings.locator(".fc-settings").evaluate("el => el.scrollTop = 0")
            _shot(page, f"track3-models-{engine}-{width}.png")
            assert settings.get_by_role("button", name="May coordinate this work", exact=True).count() == 0
            settings.get_by_role("button", name="Does this work only", exact=True).click()
            settings.get_by_role("button", name="Routine work", exact=False).click()
            settings.get_by_label("the task's workspaces, absolute directories").fill(str(task_workspace))
            # Changing settings never posts the message, even with a draft.
            field.fill("Please check the fixture.")
            assert world["sent"] == []
            geometry = settings.evaluate("""el => ({
                width: el.clientWidth, scroll: el.scrollWidth,
                composer: el.closest('.qc-composer').getBoundingClientRect().toJSON(),
                rows: [...el.querySelectorAll('.fc-srow')].map(row => ({width: row.clientWidth, scroll: row.scrollWidth}))
            })""")
            assert geometry["scroll"] <= geometry["width"] + 1, geometry
            assert all(row["scroll"] <= row["width"] + 1 for row in geometry["rows"]), geometry
            assert geometry["composer"]["right"] <= width + 1, geometry
            _shot(page, f"track3-settings-{engine}-{width}.png")
            page.get_by_role("button", name="Close participant settings", exact=True).click()
            assert settings.count() == 0
            assert field.input_value() == "Please check the fixture."
            toggle = page.get_by_title("Will be asked to work: open to choose runtime, model and effort")
            assert toggle.evaluate("el => el === document.activeElement")
            toggle.click()
            settings.get_by_role("button", name="Close participant settings", exact=True).press("Escape")
            assert settings.count() == 0
            assert toggle.evaluate("el => el === document.activeElement")

            with page.expect_response("**/fluid/api/posts") as response, page.expect_request("**/fluid/api/posts") as sent:
                field.press("Control+Enter")
            assert response.value.ok, response.value.text()
            body = sent.value.post_data_json
            assert body["action"] == "ask-participant"
            dispatch = body["dispatch"][0]
            assert dispatch["runtime"] == "claude"
            assert dispatch["model"] == "sonnet"
            assert dispatch["effort"] == "low"
            assert dispatch["coordinate"] is True
            assert dispatch["consent"]["mode"] == "task"
            assert dispatch["consent"]["workspaces"] == [str(task_workspace)]
            page.wait_for_function("document.querySelector('#qc-compose').value === ''")
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [390, 1440])
def test_track3_activity_rows_fit_the_margin_and_stop_stays_clear(world, engine, width):
    playwright = pytest.importorskip("playwright.sync_api")
    here = _conversation(world)
    parent = _requested(world["cv"], world["who"]["@brian"], world["steward"], here)
    first, _ = _open_run(world, here, "track3-a", model="a-model-with-a-very-long-name-to-check-wrapping", caused_by=parent)
    _open_run(world, here, "track3-b", model="sonnet", caused_by=parent)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000})
            page.goto(world["base"] + f"/quiet#/c/{here}")
            page.get_by_role("button", name="Activity", exact=True).click()
            rows = page.locator(".qc-run")
            rows.nth(1).wait_for()
            assert rows.count() == 2
            boxes = [rows.nth(i).bounding_box() for i in range(2)]
            assert boxes[1]["y"] >= boxes[0]["y"] + boxes[0]["height"] - 1
            for i in range(2):
                row = rows.nth(i)
                assert row.get_by_role("button", name="Stop", exact=True).is_visible()
                assert row.locator(".qc-run-detail").count() == 0
                assert row.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
            if width > 900:
                stream = page.locator("#qc-stream").bounding_box()
                assert boxes[0]["x"] >= stream["x"] + stream["width"] - 1
            first_row = rows.filter(has=page.locator(f"[aria-controls='qc-run-detail-{first}']"))
            first_row.get_by_role("button", name="Show details", exact=True).click()
            assert first_row.locator(".qc-run-detail").evaluate("el => getComputedStyle(el).position") == "static"
            assert first_row.get_by_role("button", name="Stop", exact=True).is_visible()
            first_row.get_by_role("button", name="Hide details", exact=True).click()
            _shot(page, f"track3-activity-{engine}-{width}.png")

            # A refusal is explicit and still leaves Stop available to use.
            page.route(f"**/api/runs/{first}/stop", lambda route: route.fulfill(
                status=403, content_type="application/json", body=json.dumps({"error": "Fixture refusal"})))
            first_row.get_by_role("button", name="Stop", exact=True).click()
            first_row.get_by_role("alert").filter(has_text="Could not stop").wait_for()
            assert first_row.get_by_role("button", name="Stop", exact=True).is_visible()
            page.unroute(f"**/api/runs/{first}/stop")
            with page.expect_request(f"**/api/runs/{first}/stop"):
                first_row.get_by_role("button", name="Stop", exact=True).click()
            first_row.get_by_text("Stopping…", exact=True).wait_for()
        finally:
            browser.close()
