"""Quiet Chat's Activity rail (package D) against real Mentis HTTP routes on
a disposable fixture Brain: two live runs side by side, each showing its
activity, runtime, requested model, permission mode and usage verbatim;
details and permission history opening in place; conversation activity told
apart from broader Mentis activity; Stop; and an open decision answered from
the rail.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1, as the other
Quiet browser suites do.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)


def _call(world, path, payload=None):
    req = urllib.request.Request(
        world["base"] + path, method="POST" if payload is not None else "GET",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"{exc.code}: {exc.read().decode()}") from None


def _start(cv, who, conversation, instance, *, model=None, caused_by=None):
    """A run as dispatch opens it: its start act, then held by this process
    (the same fixture `test_run_activity.py` uses)."""
    detail = {"requested_model": model} if model else None
    return cv.record_act(actor=who, act="execution-started",
                         conversation=conversation, turn=None,
                         execution=instance, runtime="claude",
                         caused_by=caused_by, because="test run", detail=detail)


def _requested(cv, owner, carrier, conversation):
    """An owner-authorised request, so a run under it can carry consent
    (`of_run`/`set_task` both need a request chain, docs/run-consent.md)."""
    turn = cv.say(conversation, owner, [text("build it")])
    return cv.expect(turn, of=carrier, kind="result", by=owner)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_activity_real_api(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, st, owner, care = world["cv"], world["state"], world["who"]["@brian"], world["steward"]
    here = cv.open_conversation("Activity browser: here", about="Where the rail is opened.")
    elsewhere = cv.open_conversation("Activity browser: elsewhere", about="Somewhere else entirely.")
    cv.join(owner, here)
    cv.join(owner, elsewhere)

    exp_here = _requested(cv, owner, care, here)
    run_here = _start(cv, care, here, "inst-here", model="claude-sonnet-5", caused_by=exp_here)
    st.agents.agents_open_run("inst-here", run_here)
    # `cancel()` only reports a run as asked when its instance is actually
    # running (`FakeExecution`, the default under `world`); Stop needs that
    # to be true for `ActivityRun.stopping` to ever flip.
    st.agents.execution._running.add("inst-here")
    st.agents._runs[run_here]["feed"].add(
        "tool_call", {"tool_call_id": "t1", "title": "Read AGENTS.md", "kind": "read", "status": "in_progress"}, time.time())
    st.agents._runs[run_here]["feed"].add(
        "usage_update", {"output_tokens": 4200, "input_tokens": 1000}, time.time())
    _call(world, f"/api/runs/{run_here}/consent", {"mode": "task"})
    cv.record_act(actor=care, act="operation-answered", conversation=here,
                  execution="inst-here", caused_by=run_here,
                  because="allowed by task: Run npm test",
                  detail={"operation": {"summary": "Run npm test", "tool": "execute", "category": "test"},
                          "answer": "allowed", "by": "task"})

    run_elsewhere = _start(cv, care, elsewhere, "inst-elsewhere")
    st.agents.agents_open_run("inst-elsewhere", run_elsewhere)
    st.agents._runs[run_elsewhere]["feed"].add(
        "tool_call", {"tool_call_id": "t2", "title": "Run tests", "kind": "execute", "status": "in_progress"}, time.time())

    asked_turn = cv.say(here, care, [text("Which branch should we prefer for the gate?")])
    decision = cv.expect(asked_turn, of=owner, kind="decision", by=care,
                         because="which branch",
                         detail={"options": [{"label": "Keep both gates"}, {"label": "Drop the slower one"}]})

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{here}")
            page.get_by_role("heading", name="Activity browser: here", exact=True).wait_for()
            page.get_by_role("button", name="Activity", exact=True).click()

            # Two groups, neither dropped: the run here, and the one elsewhere,
            # under their own labelled headings.
            page.get_by_role("heading", name="In this conversation", exact=True).wait_for()
            page.get_by_role("heading", name="Elsewhere in Mentis", exact=True).wait_for()
            here_group = page.locator(".qc-activity-group").filter(has_text="In this conversation")
            elsewhere_group = page.locator(".qc-activity-group").filter(has_text="Elsewhere in Mentis")
            here_row = here_group.locator(".qc-run").first
            elsewhere_row = elsewhere_group.locator(".qc-run").first

            # The row and the stream never intersect (the rail is its own
            # column -- a geometric fact of the margin, asserted directly).
            rail_box = page.locator(".qc-margin").bounding_box()
            stream_box = page.locator("#qc-stream").bounding_box()
            assert rail_box["x"] >= stream_box["x"] + stream_box["width"] - 1

            # Each row: current activity, runtime, model, permission mode,
            # and the feed's usage keys verbatim -- all against the fixture's
            # actually served values.
            here_row.get_by_text("Read AGENTS.md", exact=False).wait_for()
            assert "claude" in here_row.inner_text()
            assert "claude-sonnet-5" in here_row.inner_text()
            # The permission mode is its own read (`/api/runs/<run>/consent`),
            # separate from `/api/working`'s runtime and model -- waited for
            # on its own rather than assumed to have landed by the same tick.
            here_row.get_by_text("task", exact=False).wait_for()
            here_row.get_by_text("output_tokens", exact=False).wait_for()
            assert "4,200" in here_row.inner_text()
            assert "input_tokens" in here_row.inner_text()
            elsewhere_row.get_by_text("Run tests", exact=False).wait_for()

            # Detailed operations and permission history open from the row,
            # without leaving the conversation.
            assert here_row.locator(".qc-run-detail").count() == 0
            here_row.get_by_role("button", name="Show details", exact=True).click()
            here_row.get_by_text("Read AGENTS.md", exact=False).first.wait_for()
            here_row.get_by_text("Run npm test", exact=False).wait_for()
            assert here_row.get_by_text("allowed", exact=False).count() > 0
            assert page.url.endswith(f"/quiet#/c/{here}")

            # Stop is visually clear and posts to the real door.
            with page.expect_request(f"**/api/runs/{run_here}/stop"):
                here_row.get_by_role("button", name="Stop", exact=True).click()
            here_row.get_by_text("Stopping…", exact=False).wait_for()

            # An open decision is answerable from the rail; the answer is an
            # ordinary post carrying `chose`, never leaving the conversation.
            page.get_by_text("Which branch should we prefer for the gate?", exact=False).wait_for()
            sent = []
            page.route("**/fluid/api/posts", lambda route: (sent.append(route.request.post_data_json), route.continue_()))
            page.get_by_role("button", name="Drop the slower one", exact=True).click()
            page.wait_for_timeout(500)
            assert sent and sent[0]["chose"] == {"expectation": decision, "option": 1, "label": "Drop the slower one"}
            assert page.url.endswith(f"/quiet#/c/{here}")
            page.unroute("**/fluid/api/posts")

            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_activity_elsewhere_and_empty(world, engine):
    """A run elsewhere in Mentis is shown, under its own heading, rather than
    dropped by a plain `a.conversation === conversation` filter; a
    conversation nobody is working in shows the plain empty line instead of
    an empty heading. (The `working_on.conversation` fallback itself --
    `groupActivity` keeping an entry a bare `conversation ===` check would
    drop -- is asserted directly against the function in
    quiet_activity_unit.mjs, which does not depend on how the record happens
    to compute an execution's own `conversation` field.)"""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, st, owner, care = world["cv"], world["state"], world["who"]["@brian"], world["steward"]
    elsewhere = cv.open_conversation("Activity elsewhere only", about="A run lives only here.")
    cv.join(owner, elsewhere)
    run = _start(cv, care, elsewhere, "inst-only-elsewhere")
    st.agents.agents_open_run("inst-only-elsewhere", run)

    empty = cv.open_conversation("Activity empty", about="Nobody is working here.")
    cv.join(owner, empty)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(world["base"] + f"/quiet#/c/{empty}")
            page.get_by_role("heading", name="Activity empty", exact=True).wait_for()
            page.get_by_role("button", name="Activity", exact=True).click()
            page.get_by_role("heading", name="Elsewhere in Mentis", exact=True).wait_for()
            assert page.locator(".qc-activity-group").filter(has_text="In this conversation").count() == 0
            page.get_by_text("@Steward", exact=False).wait_for()

            page.goto(world["base"] + f"/quiet#/c/{elsewhere}")
            page.get_by_role("heading", name="Activity elsewhere only", exact=True).wait_for()
            page.get_by_role("button", name="Activity", exact=True).click()
            page.get_by_role("heading", name="In this conversation", exact=True).wait_for()
            assert page.locator(".qc-activity-group").filter(has_text="Elsewhere in Mentis").count() == 0
        finally:
            browser.close()
