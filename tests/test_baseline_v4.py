"""Baseline version 4: the owner's review ruling (2026-10-29).

WHAT MUST HOLD:
  - the Workflow plans, reviews what warrants it, corrects with a scoped
    re-review, and names the standing Planner, Builder and Independent
    Reviewer; its text states the ruling's criteria, with no score and no
    review every change must go through;
  - on a Brain at version 3 both successors arrive as PROPOSALS of the items
    they succeed, and the Workflow proposal is the body the decisions sheet
    (docs/governance/workflow-2026-10-29.json) establishes, so they are one
    entry;
  - the sheet's `when` is met by ordinary development requests and not by
    ordinary posts, and condense delivers the Workflow placed with it in full
    to the one and as a single conditional line to the other.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

import mentis.api as api
from mentis.bootstrap import baseline
from mentis.conversation.condense import CONDITIONAL, FULL, condense
from mentis.conversation.knowledge import meets

SPEC = baseline.load()
SHEET = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "governance"
                    / "workflow-2026-10-29.json").read_text(encoding="utf-8"))
FLOW_ITEM = next(i for i in SHEET["items"] if i["key"] == "software-change")
WHEN = FLOW_ITEM["placement"]["when"]

DEVELOPMENT = [
    "Fix the bug where the Fluid sidebar loads slowly",
    "Add a status filter to the conversation list in Fluid",
    "Implement B1: delegate with activity gives the child the activity's Persona, with tests",
    "Refactor dispatch.py so resumed runs keep their Persona, and add tests",
    "The MARS backend crashes when the runtime is rate limited; please fix it",
    "Change the Fluid button colour to blue",
    "Write a test for establish_governance and commit it on a branch",
    "Make the Mentis server cache work_overview so the sidebar is faster",
    "Merge the consent-gaps branch into main and push",
    "Add an endpoint to the Mentis HTTP API that lists placements",
    "Update MARS so the Codex backend reads capacity before choosing a model",
    "The Fluid build fails after the last merge; fix it",
]
ORDINARY = [
    "Plan the garden borders for spring",
    "Summarise the minutes of the budget committee and list the three action items",
    "Can you change my dentist appointment to Friday?",
    "Draft a birthday message for my sister",
    "What did we decide about the holiday budget?",
    "Remind me to buy milk and bread tomorrow",
    "Where should we eat tonight?",
    "I want to build a shed in the garden this weekend",
    "Fix the leaking kitchen tap",
    "Help me change my running plan for the marathon",
    "Update my CV with the new job",
    "What does Mentis know about my reading list?",
    "Add eggs and flour to the shopping list",
]


def v3():
    """Version 3 as it shipped: v4 with its two changed items put back."""
    spec = copy.deepcopy(SPEC)
    spec["version"] = 3
    flow = spec["workflows"][0]
    keep = ("orient-recall", "record-request", "implement", "integrate",
            "verify", "record-outcome-and-learning")
    flow["activities"] = [a for a in flow["activities"] if a["key"] in keep]
    flow["text"] = "Orient, record, hand parts to workers, integrate, test, record."
    for r in spec["rules"]:
        if r["key"] == "coordinated-work":
            r["text"] = "How coordinated work is organised. Version 3's words."
    return spec


@pytest.fixture
def brain(tmp_path):
    c = api.create_corpus(str(tmp_path / "brain"))
    yield c, api.brain(c).conversations
    c.close()


def _flow():
    return next(b for k, _, b in baseline.items(SPEC) if k == "software-change")


def test_version_four_ships_the_ruling():
    assert SPEC["version"] == 4
    flow = _flow()
    rows = {a["key"]: a for a in flow["activities"]}
    assert list(rows) == ["orient-recall", "record-request", "plan", "plan-review",
                          "implement", "review", "correct", "integrate", "verify",
                          "record-outcome-and-learning"]
    assert flow["persona"] == "baseline:caretaker"
    assert rows["plan"]["who"]["persona"] == "baseline:planner"
    assert rows["plan-review"]["who"]["persona"] == "baseline:independent-reviewer"
    assert rows["review"]["who"]["persona"] == "baseline:independent-reviewer"
    assert rows["implement"]["who"]["persona"] == "baseline:builder"
    assert rows["correct"]["who"]["persona"] == "baseline:builder"
    for key in ("plan", "implement", "correct", "integrate", "verify"):
        assert rows[key]["disciplines"] == ["baseline:cli-mars-development"]
    for a in flow["activities"]:
        assert a["what"] and a["done_when"] and a["who"]["role"]
    assert "review_of" in rows["review"]["what"]
    assert "discovered work" in rows["record-outcome-and-learning"]["what"]
    assert "verdict" in flow["evidence"] and flow["decisions"] and flow["interrupted"]
    rule = next(b for k, _, b in baseline.items(SPEC) if k == "coordinated-work")
    for text in (flow["text"], rule["text"]):
        for said in ("complexity, foundational impact and the cost of finding a "
                     "defect later", "routine styling, simple filters and localised "
                     "changes need none", "shared APIs, governance, execution, "
                     "security and foundational changes warrant it",
                     "not by repeating the whole review"):
            assert said in text
        assert not re.search(r"\d", text)          # no score, no threshold
        assert not re.search(r"\b(always|every change must|mandatory)\b", text,
                             re.I)


def test_the_sheet_is_the_baseline_with_this_brains_entries():
    here = {"caretaker": "ent-a87fd088a7d6", "planner": "ent-b98523d87399",
            "builder": "ent-9e865d1fabe6",
            "independent-reviewer": "ent-a7c92c5a63d5",
            "cli-mars-development": "ent-80392167cca0"}
    assert FLOW_ITEM["body"] == baseline.resolved(_flow(), here)
    assert FLOW_ITEM["replaces"] == "ent-0b4b07f5432f"
    assert FLOW_ITEM["placement"] == {"whole_brain": True, "delivery": "conditional",
                                      "when": WHEN}
    rule = next(i for i in SHEET["items"] if i["key"] == "coordinated-work")
    assert rule["text"] == next(
        b for k, _, b in baseline.items(SPEC) if k == "coordinated-work")["text"]
    assert rule["replaces"] == "ent-80100415feed"


def test_a_version_three_brain_gets_both_as_proposals(brain):
    c, cv = brain
    first = baseline.install(c, "@owner", spec=v3())
    out = baseline.install(c, "@owner")
    assert out["action"] == "update"
    for key in ("software-change", "coordinated-work"):
        row = out["items"][key]
        assert row["how"] == "propose" and row["entry"] == first["items"][key]["entry"]
        assert c.stands(row["entry"])["stands"]        # nothing displaced
        assert not c.stands(row["proposal"])["stands"]
        assert row["entry"] in json.dumps(c.proposed_supersessions(row["proposal"]))
    assert {k for k, r in out["items"].items() if r["how"] != "unchanged"} == {
        "software-change", "coordinated-work"}
    flow = c.read([out["items"]["software-change"]["proposal"]])[0]["body"]
    rows = {a["key"]: a for a in flow["activities"]}
    items = first["items"]
    assert rows["implement"]["who"]["persona"] == items["builder"]["entry"]
    assert rows["review"]["who"]["persona"] == items["independent-reviewer"]["entry"]
    assert rows["plan"]["who"]["persona"] == items["planner"]["entry"]
    assert flow["persona"] == items["caretaker"]["entry"]


@pytest.mark.parametrize("work", DEVELOPMENT)
def test_development_requests_meet_the_condition(work):
    assert meets(work, WHEN), work


@pytest.mark.parametrize("post", ORDINARY)
def test_ordinary_posts_do_not(post):
    assert not meets(post, WHEN), post


def test_condense_delivers_the_placed_workflow_by_the_condition(brain):
    c, cv = brain
    items = baseline.install(c, "@owner")["items"]
    owner = baseline.people(c, cv)["owner"]
    flow = items["software-change"]["entry"]
    cv.place(flow, whole_brain=True, by=owner, because="the owner's ruling",
             delivery=CONDITIONAL, when=WHEN)
    conv = cv.open_conversation("Any", attributed_to=owner)

    def level(work):
        comp = cv.compose(conversation=conv, participant=owner, question=work)
        got = [d for d in condense(c, comp, question=work)
               if d.component.source_id == flow]
        assert len(got) == 1
        return got[0].level

    assert level(DEVELOPMENT[0]) == FULL
    assert level(DEVELOPMENT[-1]) == FULL
    assert level(ORDINARY[0]) == CONDITIONAL
    assert level(ORDINARY[2]) == CONDITIONAL
