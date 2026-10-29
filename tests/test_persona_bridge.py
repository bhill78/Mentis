"""The Persona, and a named Workflow, on the hand-started (bridge) path.

WHAT MUST HOLD, asked through the same `_result` the worker door answers with:
  - `brief(persona=…)` delivers the Persona's standing text and what it
    carries IN FULL, for the grant's Participant, and says it grants nothing;
  - a superseded Persona, named by its old id, is delivered as its standing
    successor and the brief says so; a name finds the standing one;
  - an unknown, unestablished or wrong-Kind Persona is refused with why;
  - `brief(workflow=…)` delivers the standing Workflow in full;
  - `recall` takes the Persona too, and lists the Workflows and Disciplines
    that apply to the work in `guidance` -- by reference, never their text.
"""

from __future__ import annotations

import pytest

import mentis.api as api
from mentis.bootstrap import baseline
from mentis.worker import TOOLS, Surface, _result, compose_brief


@pytest.fixture
def world(tmp_path):
    c = api.create_corpus(str(tmp_path / "brain"))
    out = baseline.install(c, "@owner")
    s = Surface(str(tmp_path / "brain"), corpus=c)
    owner = out["owner"]
    conv = s.cv.open_conversation("Build", attributed_to=owner)
    items = {k: r["entry"] for k, r in out["items"].items()}
    yield {"c": c, "s": s, "owner": owner, "conv": conv, "items": items,
           "worker": out["caretaker"]}
    c.close()


def call(w, name, **args):
    return _result(w["s"], name, args, participant=w["worker"])


def test_the_tools_offer_the_arguments():
    schemas = {t["name"]: t["inputSchema"]["properties"] for t in TOOLS}
    assert {"persona", "workflow", "work"} <= set(schemas["brief"])
    assert "persona" in schemas["recall"]


def test_a_persona_is_delivered_in_full_with_what_it_carries(world):
    w = world
    builder = w["items"]["builder"]
    # Something the Builder carries: the Discipline, placed on the Persona.
    w["s"].cv.place(w["items"]["cli-mars-development"], where=builder,
                    by=w["owner"], because="the Builder works this way")
    got = call(w, "brief", conversation=w["conv"], persona="Builder")
    assert not got.get("refused"), got
    assert got["persona"]["entry"] == builder
    assert got["for"] == w["worker"]
    behaviour = w["c"].read([builder])[0]["body"]["behaviour"]
    by_id = {g["id"]: g for g in got["governing"]}
    assert by_id[builder]["text"] == behaviour      # whole, never cut
    assert by_id[builder]["scope"] == "invocation:persona"
    carried = by_id[w["items"]["cli-mars-development"]]
    assert carried["scope"] == f"persona:{builder}"
    assert "Tools it uses (named, not granted;" in carried["text"]
    assert behaviour in got["delivered"]
    assert "grants nothing" in got["persona_note"]
    # And what a plain brief always held is still there.
    plain = call(w, "brief", conversation=w["conv"])
    assert set(plain) <= set(got)


def test_a_superseded_persona_resolves_to_its_successor(world):
    w = world
    c, old = w["c"], w["items"]["reviewer"]
    new = c.create_and_establish(kind="persona", body={
        "name": "Reviewer", "behaviour": "You are Reviewer, revised.",
        "about": ""}, attributed_to=w["owner"])
    c.write(body={"reason": "owner revised"}, attributed_to=w["owner"],
            link={"from": new, "to": old, "relation": c.superseding_relation()})
    got = call(w, "brief", conversation=w["conv"], persona=old)
    assert got["persona"]["entry"] == new
    assert got["persona"]["superseded_by"] == new and got["persona"]["named"] == old
    texts = [g["text"] for g in got["governing"]]
    assert "You are Reviewer, revised." in texts
    assert not any(g["id"] == old for g in got["governing"])
    # By name, the standing one.
    assert call(w, "brief", conversation=w["conv"],
                persona="Reviewer")["persona"]["entry"] == new


@pytest.mark.parametrize("persona,why", [
    ("Nobody", "is no standing persona"),
    ("ent-000000000000", "is no standing persona"),
])
def test_an_unknown_persona_is_refused(world, persona, why):
    got = call(world, "brief", conversation=world["conv"], persona=persona)
    assert got["refused"] and why in got["why_not"]


def test_an_unestablished_or_wrong_kind_persona_is_refused(world):
    w = world
    c = w["c"]
    candidate = c.write(kind="persona", body={"name": "Ghost", "behaviour": "x",
                                              "about": ""},
                        attributed_to=w["owner"])
    got = call(w, "brief", conversation=w["conv"], persona=candidate)
    assert got["refused"] and "does not stand" in got["why_not"]
    got = call(w, "brief", conversation=w["conv"], persona="Ghost")
    assert got["refused"]
    got = call(w, "brief", conversation=w["conv"],
               persona=w["items"]["repair-scope"])
    assert got["refused"] and "not a persona" in got["why_not"]


def test_a_named_workflow_is_delivered_in_full(world):
    w = world
    flow = w["items"]["software-change"]
    got = call(w, "brief", conversation=w["conv"], workflow=flow)
    assert got["workflow"]["entry"] == flow
    row = next(g for g in got["governing"] if g["id"] == flow)
    assert row["scope"] == "invocation:named"
    for said in ("What supports completion:",
                 "If interrupted: what remains and how it continues:",
                 "orient-recall", "record-outcome-and-learning",
                 'Delegate it with activity: "' + flow + '#implement"'):
        assert said in row["text"]
    assert "persona_note" not in got
    # A Workflow is named by id only, and must be a Workflow.
    assert call(w, "brief", conversation=w["conv"],
                workflow="Software change")["refused"]
    assert call(w, "brief", conversation=w["conv"],
                workflow=w["items"]["builder"])["refused"]


def test_a_plain_brief_is_what_it_was(world):
    got = call(world, "brief", conversation=world["conv"])
    assert "governing" not in got and "persona" not in got
    assert got["for"] == world["worker"]


def test_compose_brief_is_the_function_the_tool_calls(world):
    w = world
    direct = compose_brief(w["s"], w["conv"], w["worker"], persona="Builder")
    got = call(w, "brief", conversation=w["conv"], persona="Builder")
    # The tool adds the prepared orientation and whether the cache answered.
    assert {k: v for k, v in got.items() if k not in ("prepared", "cache")} == direct
    assert "Builder" in got["prepared"]["rendered"]


def test_recall_takes_the_persona_and_points_to_guidance(world):
    w = world
    work = "Carry a software change through Git and MARS with targeted tests"
    got = call(w, "recall", work=work, conversation=w["conv"],
               persona="Builder")
    assert not got.get("refused"), got
    assert got["persona"]["entry"] == w["items"]["builder"]
    assert any(r["id"] == w["items"]["builder"]
               for r in got["tiers"]["governing"])
    refs = {g["id"]: g for g in got["guidance"]}
    assert set(refs) == {w["items"]["software-change"],
                         w["items"]["cli-mars-development"]}
    for g in refs.values():
        assert set(g) == {"id", "kind", "name", "about", "met_by"}
    # Never the full text there.
    assert "Orient and recall what applies" not in str(got["guidance"])


def test_guidance_is_only_what_applies_and_stands(world):
    w = world
    assert call(w, "recall", work="Plan the garden borders")["guidance"] == []
    got = call(w, "recall", work="Prune the roses", persona="Nobody")
    assert got["refused"]


def test_agents_in_one_conversation_share_the_stable_prefix(world):
    # The brain and conversation blocks are the same bytes for every agent in
    # the Conversation, whatever Persona it wears; only the agent block differs.
    w = world
    builder = call(w, "brief", conversation=w["conv"], persona="Builder",
                   work="implement the parser")
    reviewer = call(w, "brief", conversation=w["conv"], persona="Reviewer",
                    work="review the parser")
    b = {x["tier"]: x for x in builder["prepared"]["blocks"]}
    r = {x["tier"]: x for x in reviewer["prepared"]["blocks"]}
    assert [x["tier"] for x in builder["prepared"]["blocks"]] == [
        "brain", "conversation", "agent"]
    assert b["brain"]["digest"] == r["brain"]["digest"]
    assert b["conversation"]["digest"] == r["conversation"]["digest"]
    assert b["agent"]["digest"] != r["agent"]["digest"]
    assert builder["prepared"]["rendered"].startswith(b["brain"]["text"])
