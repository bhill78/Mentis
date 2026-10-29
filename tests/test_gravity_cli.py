"""Contract tests for Task Gravity on the CLI/server path."""

import pytest

from mentis.conversation import text
from mentis.operational import discovery, pursuit_permitted
from mentis.web import _routes
from tests.test_manual_session import _session, world


def _finding(cv, actor, conversation, parent, words):
    turn = cv.say(conversation, actor, [text(words)])
    expectation = cv.expect(turn, of=None, kind="result", by=actor,
                            caused_by=parent)
    cv.record_act(actor=actor, act="work-discovered",
                  conversation=conversation, turn=turn, caused_by=parent,
                  about=[expectation], because=words)
    return expectation


@pytest.mark.parametrize("setting,allowed,refused", [
    ({"depth": 1}, 1, 2), ({"depth": 2}, 2, 3),
])
def test_depth_allows_exactly_its_generations(world, setting, allowed, refused):
    cv = world["st"].cv
    grant, op = _session(world)
    _, opened = op("open_conversation", name=f"Depth {allowed}")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up=setting)
    current = request["expectation"]
    findings = []
    for n in range(1, refused + 1):
        current = _finding(cv, grant["participant"], opened["conversation"],
                           current, f"generation {n}")
        findings.append(current)
    assert discovery(cv, findings[allowed - 1])["generation"] == allowed
    assert pursuit_permitted(cv, findings[allowed - 1])
    assert discovery(cv, findings[refused - 1])["generation"] == refused
    assert pursuit_permitted(cv, findings[refused - 1]) is None


def test_unrestricted_reaches_generation_five_and_ask_reaches_none(world):
    cv = world["st"].cv
    grant, op = _session(world)
    _, opened = op("open_conversation", name="Unlimited")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="root", follow_up="unrestricted")
    current = request["expectation"]
    for n in range(5):
        current = _finding(cv, grant["participant"], opened["conversation"],
                           current, f"generation {n + 1}")
    assert pursuit_permitted(cv, current)
    _, ask = op("record_request", conversation=opened["conversation"],
                text="ask root", follow_up="ask")
    asked = _finding(cv, grant["participant"], opened["conversation"],
                     ask["expectation"], "ask first")
    assert pursuit_permitted(cv, asked) is None


def test_child_inherits_and_cannot_widen(world):
    _, op = _session(world)
    _, opened = op("open_conversation", name="Children")
    _, parent = op("record_request", conversation=opened["conversation"],
                   text="parent", follow_up={"depth": 1})
    status, refused = op("record_request", conversation=opened["conversation"],
                         text="child", parent=parent["expectation"],
                         follow_up={"depth": 2})
    assert status == 403
    assert "original request" in refused["error"]
    status, child = op("record_request", conversation=opened["conversation"],
                       text="child", parent=parent["expectation"])
    assert status == 200
    assert world["st"].cv._act(child["expectation"])["detail"]["follow_up"] == {
        "depth": 1}


def test_request_metadata_overview_and_gravity_route(world):
    st, cv = world["st"], world["st"].cv
    _, op = _session(world)
    _, opened = op("open_conversation", name="Metadata")
    persona = cv.define_persona("Builder", "Build it", attributed_to=world["owner"])
    workflow = st.corpus.create_and_establish(
        kind="workflow", body={"name": "Software", "about": "software",
                               "text": "build", "activities": [],
                               "decisions": [], "done_when": "tested",
                               "requires": []}, attributed_to=world["owner"])
    status, request = op("record_request", conversation=opened["conversation"],
                         text="root", follow_up={"depth": 2}, persona=persona,
                         workflow=workflow, runtime="codex")
    assert status == 200
    detail = cv._act(request["expectation"])["detail"]
    assert detail["persona"] == persona and detail["workflow"] == workflow
    assert detail["runtime"] == "codex"
    assert cv.governed_named(request["expectation"]) == [workflow]
    status, overview = op("work_overview", conversation=opened["conversation"])
    assert status == 200
    item = next(i for i in overview["items"]
                if i["expectation"] == request["expectation"])
    assert item["follow_up"] == {"depth": 2} and item["generation"] == 0
    gravity = _routes(st, "/api/gravity",
                      {"expectation": [request["expectation"]]}, {}, "GET")
    assert gravity == {"setting": {"depth": 2},
                       "label": "May pursue side work 2 generations deep",
                       "generation": 0, "may_pursue_next": True,
                       "deferred": []}


def test_nonstanding_persona_and_workflow_are_refused(world):
    st, cv = world["st"], world["st"].cv
    _, op = _session(world)
    _, opened = op("open_conversation", name="Standing")
    persona = cv.propose_persona("Maybe", "Maybe", attributed_to=world["owner"])
    workflow = st.corpus.write(kind="workflow", body={"name": "Maybe"},
                               attributed_to=world["owner"])
    for key, value in (("persona", persona), ("workflow", workflow)):
        status, refused = op("record_request",
                             conversation=opened["conversation"], text="root",
                             **{key: value})
        assert status == 403 and "does not stand" in refused["error"]
