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
            # ordinary post carrying `chose`, never leaving the conversation,
            # and -- a record-only reply -- dispatches nothing (world["sent"],
            # not a browser-local interception list).
            page.get_by_text("Which branch should we prefer for the gate?", exact=False).wait_for()
            with page.expect_response("**/fluid/api/posts"):
                page.get_by_role("button", name="Drop the slower one", exact=True).click()
            posted = cv.turns(here)[-1]["turn"]
            said = next(a for a in st.corpus.operational(turn=posted) if a["act"] == "turn-said")
            assert said["detail"]["chose"] == {"expectation": decision, "option": 1, "label": "Drop the slower one"}
            assert not world["sent"]
            assert page.url.endswith(f"/quiet#/c/{here}")

            assert errors == []
        finally:
            browser.close()


def _open_run(world, here, instance, *, model=None, caused_by=None,
              activity="Initial activity", usage=True, stopping=False):
    """A live run as the rail meets one: open, held by this process, with a
    current activity in its feed and a permission mode already answered.
    `stopping=True` asks Stop on the server BEFORE any row mounts, which is
    the only way `ActivityRun.stopping` can be true that no local click
    state would ever account for."""
    cv, st, care = world["cv"], world["state"], world["steward"]
    run = _start(cv, care, here, instance, model=model, caused_by=caused_by)
    st.agents.agents_open_run(instance, run)
    st.agents.execution._running.add(instance)
    feed = st.agents._runs[run]["feed"]
    feed.add("tool_call", {"tool_call_id": "a1", "title": activity,
                           "kind": "read", "status": "in_progress"}, time.time())
    if usage:
        feed.add("usage_update", {"output_tokens": 4200, "input_tokens": 1000}, time.time())
    _call(world, f"/api/runs/{run}/consent", {"mode": "task"})
    if stopping:
        assert _call(world, f"/api/runs/{run}/stop", {})["asked"]
    return run, feed


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_activity_stays_current_while_the_rail_stays_open(world, engine):
    """THE RAIL'S READINGS ARE LIVE, NOT FIRST-TICK ONLY (review findings 1-3
    on 38562ec). All three were right on the opening tick and then went wrong
    while nothing but the server changed, so each is asserted only AFTER a
    change made with the row already mounted:

    1. USAGE SURVIVES A POLL THAT CARRIES NONE. The feed is read
       `?after=<next>`, so a later poll's delta holds only what changed. The
       server keeps usage as ONE entry (`run_feed.py`'s fixed `"usage"` id,
       reported verbatim), so a delta in which usage did not change carries
       no usage entry at all -- and reading that delta's own usage instead of
       the accumulated entries is what made the figures vanish.
    2. CURRENT ACTIVITY REFRESHES. `/api/activity` is read with `runs: true`,
       so a run advance rereads it; without that the row kept the activity it
       first read while the server had moved on.
    3. PERMISSION MODE AND HISTORY REFRESH. `/api/runs/<run>/consent` is
       reread while the rail is open, not once when the run starts.
    """
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    here = cv.open_conversation("Activity stays current", about="Readings must not go stale.")
    cv.join(owner, here)
    parent = _requested(cv, owner, care, here)
    run, feed = _open_run(world, here, "inst-current", model="claude-sonnet-5", caused_by=parent)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{here}")
            page.get_by_role("button", name="Activity", exact=True).click()
            row = page.locator(".qc-run").first
            # The opening tick: what the first read already got right.
            row.get_by_text("Initial activity", exact=True).wait_for()
            row.get_by_text("task", exact=True).wait_for()
            row.get_by_text("output_tokens 4,200", exact=True).wait_for()

            # Now change only the server, with the row mounted and polling.
            # Deliberately NO `usage_update`: every poll from here on carries
            # a delta in which usage does not appear.
            feed.add("tool_call", {"tool_call_id": "a2", "title": "New current activity",
                                   "kind": "execute", "status": "in_progress"}, time.time())
            _call(world, f"/api/runs/{run}/consent", {"mode": "deny"})
            cv.record_act(actor=care, act="operation-answered", conversation=here,
                          execution="inst-current", caused_by=run,
                          because="refused by deny: Later operation",
                          detail={"operation": {"summary": "Later operation", "tool": "execute"},
                                  "answer": "refused", "by": "deny"})

            # 2. The row follows the server's own current activity.
            row.get_by_text("New current activity", exact=True).wait_for()
            served = next(r["activity"] for a in _call(world, "/api/activity")["activity"]
                          for r in a.get("runs", []) if r["run"] == run)
            assert row.locator(".qc-run-activity").inner_text() == served

            # 1. The figures are still there, several polls after the one
            # that carried them -- the activity above only changed because
            # later deltas landed, and none of them held usage.
            assert "output_tokens 4,200" in row.inner_text()
            assert "input_tokens 1000" in row.inner_text()
            assert row.locator(".qc-run-usage").count() == 1

            # 3. The mode in force, and an operation answered since mounting.
            row.get_by_text("deny", exact=True).wait_for()
            assert "deny" in row.locator(".qc-run-head").inner_text()
            row.get_by_role("button", name="Show details", exact=True).click()
            row.get_by_text("Later operation", exact=False).wait_for()
            assert "refused" in row.locator(".qc-run-detail").inner_text()

            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_activity_server_stopping_reads_as_stopping(world, engine):
    """A RUN ALREADY STOPPING IS NOT OFFERED AN INERT "Stop" (review finding
    5 on 38562ec). Stop was asked on the server before this row ever mounted,
    so there is no local click state to read it from: the wording must come
    from `ActivityRun.stopping` itself, and no live Stop button may remain to
    be pressed again."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    here = cv.open_conversation("Activity already stopping", about="Stop was asked already.")
    cv.join(owner, here)
    parent = _requested(cv, owner, care, here)
    run, _feed = _open_run(world, here, "inst-stopping", caused_by=parent, stopping=True)
    served = next(r for a in _call(world, "/api/activity")["activity"]
                  for r in a.get("runs", []) if r["run"] == run)
    assert served["stopping"], "the fixture must report a run the server knows is stopping"

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(world["base"] + f"/quiet#/c/{here}")
            page.get_by_role("button", name="Activity", exact=True).click()
            row = page.locator(".qc-run").first
            row.get_by_text("Stopping…", exact=True).wait_for()
            assert "qc-run-stopping" in (row.get_attribute("class") or "")
            assert row.get_by_role("button", name="Stop", exact=True).count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_activity_two_runs_side_by_side_and_pending_decision(world, engine):
    """TWO LIVE RUNS SIDE BY SIDE, AND A DECISION ON NO POST YET (review
    findings 6 and 4 on 38562ec).

    6. Two runs in one conversation are two rows that occupy DISJOINT
       horizontal spans -- the brief's literal "side by side" -- not one
       column stacked vertically. Both still clear the stream.
    4. A standard pending decision form carries `turn: null` until it lands
       on a post. It is served in `owed` with its own options, so it must be
       answerable from the rail rather than omitted when `/api/turns/null`
       cannot be read -- and READABLE there: with no post to read, its
       `because` is a generic fallback, so the question itself must be shown
       or the rail offers options for something nobody can see.
    """
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    from mentis.worker import _decision_form
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    here = cv.open_conversation("Activity two runs", about="Two runs, and a pending form.")
    cv.join(owner, here)
    parent = _requested(cv, owner, care, here)
    _open_run(world, here, "inst-one", model="claude-sonnet-5", caused_by=parent)
    _open_run(world, here, "inst-two", model="claude-sonnet-5", caused_by=parent,
              activity="The second run", usage=False)

    # A decision form on no post yet: `pending`, so its `owed` row's `turn`
    # is null (`Conversations.attach_pending_forms` lands it only later).
    form = _decision_form(
        cv, {"question": "Which gate should the pending form prefer?",
             "options": [{"label": "Pending keep both"}, {"label": "Pending drop one"}]},
        actor=care, parent=parent, here=here, wrote=None,
        act=lambda kind, **kw: cv.record_act(actor=care, act=kind, execution="inst-one",
                                             caused_by=parent, **kw),
        where=lambda cid: cid, execution="inst-one")
    assert form["pending"], "this test needs a form that has not landed on a post"
    owed = _call(world, f"/api/conversations/{here}?batch=0")["owed"]
    question = next(o for o in owed if o["turn"] is None and o.get("options"))
    # The fixture must be the case the finding was about: no post, options of
    # its own, and a `because` that is NOT the question.
    assert question["question"] == "Which gate should the pending form prefer?"
    assert question["because"] != question["question"], question

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{here}")
            page.get_by_role("button", name="Activity", exact=True).click()
            page.get_by_role("heading", name="In this conversation", exact=True).wait_for()
            here_group = page.locator(".qc-activity-group").filter(has_text="In this conversation")
            rows = here_group.locator(".qc-run")
            page.get_by_text("The second run", exact=True).wait_for()
            assert rows.count() == 2

            # Disjoint horizontal spans, both clear of the stream.
            boxes = [rows.nth(i).bounding_box() for i in range(2)]
            stream = page.locator("#qc-stream").bounding_box()
            assert all(b["x"] >= stream["x"] + stream["width"] - 1 for b in boxes), (boxes, stream)
            first, second = sorted(boxes, key=lambda b: b["x"])
            assert first["x"] + first["width"] <= second["x"] + 1, boxes

            # The turn-less decision is shown, in the asker's own words, and
            # answerable from the rail.
            decision = page.locator(".qc-decision").filter(has_text="Which gate should the pending form prefer?")
            decision.wait_for()
            answer = decision.get_by_role("button", name="Pending drop one", exact=True)
            assert answer.count() == 1
            with page.expect_response("**/fluid/api/posts"):
                answer.click()
            state = cv.expectation_state(question["expectation"])
            assert state["response_present"], state
            assert page.url.endswith(f"/quiet#/c/{here}")

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
