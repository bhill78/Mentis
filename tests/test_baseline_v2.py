"""Baseline version 2: one Discipline and one Workflow (docs/operating-model.md §2).

WHAT MUST HOLD:
  - a new Brain gets them ESTABLISHED, with the Workflow's activities naming
    this Brain's own Builder and Reviewer Personas and the Discipline;
  - a Brain at version 1 gets them as PROPOSALS only: nothing established,
    nothing it already holds overwritten;
  - running the same version again writes nothing;
  - what is delivered says the Discipline's tools are named, not granted.
"""

from __future__ import annotations

import copy

import pytest

import mentis.api as api
from mentis.bootstrap import baseline

SPEC = baseline.load()


def v1():
    """Version 1 as it shipped: the same items, without the new sections."""
    spec = copy.deepcopy(SPEC)
    spec["version"] = 1
    spec.pop("disciplines")
    spec.pop("workflows")
    return spec


@pytest.fixture
def brain(tmp_path):
    c = api.create_corpus(str(tmp_path / "brain"))
    yield c, api.brain(c).conversations
    c.close()


def test_version_two_ships_the_workflow_and_discipline():
    assert SPEC["version"] >= 2
    keys = {k: kind for k, kind, _ in baseline.items(SPEC)}
    assert keys["software-change"] == "workflow"
    assert keys["cli-mars-development"] == "discipline"
    # The Task Gravity guidance travels with the Builder (v3; it was the
    # repair-scope rule's in versions 1 and 2).
    assert "follow-up permission" in next(
        b["behaviour"] for k, _, b in baseline.items(SPEC) if k == "builder")
    flow = next(b for k, _, b in baseline.items(SPEC) if k == "software-change")
    # Version 4 added plan, plan-review, review and correct (the owner's
    # review ruling); version 2's activities are all still there, in order.
    assert [a["key"] for a in flow["activities"]] == [
        "orient-recall", "record-request", "plan", "plan-review", "implement",
        "review", "correct", "integrate", "verify",
        "record-outcome-and-learning"]
    assert set(SPEC["_not_carried"]) >= {"operating facts about Mentis"}


def test_a_new_brain_gets_them_established(brain):
    c, cv = brain
    out = baseline.install(c, "@owner")
    assert out["action"] == "install"
    items = out["items"]
    for key in ("software-change", "cli-mars-development"):
        assert items[key]["how"] == "establish"
        assert c.stands(items[key]["entry"])["stands"]
    flow = c.read([items["software-change"]["entry"]])[0]
    assert flow["origin"] == f"bootstrap:mentis-baseline@{SPEC['version']}/software-change"
    rows = {a["key"]: a for a in flow["body"]["activities"]}
    # The keys were written as THIS Brain's entries.
    assert rows["implement"]["who"]["persona"] == items["builder"]["entry"]
    assert rows["review"]["who"]["persona"] == items["independent-reviewer"]["entry"]
    assert rows["plan"]["who"]["persona"] == items["planner"]["entry"]
    assert rows["implement"]["disciplines"] == [
        items["cli-mars-development"]["entry"]]
    assert flow["body"]["persona"] == items["caretaker"]["entry"]
    assert "baseline:" not in str(flow["body"])
    # Neither is placed: a Discipline reaches work through the activity
    # that names it, a Workflow by being named for a request.
    wb = cv.whole_brain()
    for key in ("software-change", "cli-mars-development"):
        assert wb not in cv.placements_now(items[key]["entry"])


def test_the_discipline_is_delivered_as_named_not_granted(brain):
    c, cv = brain
    items = baseline.install(c, "@owner")["items"]
    owner = baseline.people(c, cv)["owner"]
    comp = cv.compose(participant=owner,
                      behavioural=[items["cli-mars-development"]["entry"],
                                   items["software-change"]["entry"]])
    text = comp.payload()
    assert ("Tools it uses (named, not granted; whether installed is the "
            "runtime's, whether permitted is your grant's):\n- git") in text
    assert "Requires (runtime capabilities):\n- call_mentis_tools" in text
    assert "Known limitations and dependencies:" in text
    assert "What supports completion:" in text
    assert "If interrupted: what remains and how it continues:" in text
    assert "Projects it applies to:\n- Mentis\n- MARS" in text
    assert "as Persona Builder (" in text


def test_a_version_one_brain_gets_proposals_only(brain):
    c, cv = brain
    first = baseline.install(c, "@owner", spec=v1())
    standing_before = {e["id"] for kind in ("persona", "rule", "decision")
                       for e in c.entries_of_kind(kind)
                       if c.stands(e["id"])["stands"]}
    out = baseline.install(c, "@owner")
    assert out["action"] == "update"
    items = out["items"]
    for key in ("software-change", "cli-mars-development"):
        assert items[key]["how"] == "propose-new"
        eid = items[key]["entry"]
        assert not c.stands(eid)["stands"]
        assert not c.stands(eid)["superseded_by"]
    # Everything version 1 wrote is untouched and still stands.
    for key, row in first["items"].items():
        assert items[key]["how"] == "unchanged"
        assert items[key]["entry"] == row["entry"]
    assert standing_before == {e["id"] for kind in ("persona", "rule",
                                                    "decision")
                               for e in c.entries_of_kind(kind)
                               if c.stands(e["id"])["stands"]}
    assert not any(c.stands(e["id"])["stands"]
                   for kind in ("workflow", "discipline")
                   for e in c.entries_of_kind(kind))
    # The proposed Workflow names this Brain's standing Builder and the
    # proposed Discipline.
    flow = c.read([items["software-change"]["entry"]])[0]
    rows = {a["key"]: a for a in flow["body"]["activities"]}
    assert rows["implement"]["who"]["persona"] == first["items"]["builder"]["entry"]
    assert rows["implement"]["disciplines"] == [
        items["cli-mars-development"]["entry"]]


def test_an_owner_successor_is_what_the_proposal_names(brain):
    c, cv = brain
    first = baseline.install(c, "@owner", spec=v1())
    old = first["items"]["builder"]["entry"]
    new = c.create_and_establish(
        kind="persona", body={"name": "Builder", "behaviour": "Mine.",
                              "about": ""}, attributed_to="human")
    c.write(body={"reason": "owner revised"}, attributed_to="human",
            link={"from": new, "to": old,
                  "relation": c.superseding_relation()})
    items = baseline.install(c, "@owner")["items"]
    flow = c.read([items["software-change"]["entry"]])[0]
    rows = {a["key"]: a for a in flow["body"]["activities"]}
    assert rows["implement"]["who"]["persona"] == new


def test_a_rerun_writes_nothing(brain):
    c, cv = brain
    baseline.install(c, "@owner", spec=v1())
    baseline.install(c, "@owner")
    before = c.writes
    again = baseline.install(c, "@owner")
    assert again["action"] == "unchanged"
    assert c.writes == before


def test_check_plans_without_writing(brain):
    c, cv = brain
    baseline.install(c, "@owner", spec=v1())
    before = c.writes
    out = baseline.install(c, "@owner", dry_run=True)
    assert out["dry_run"] and out["items"]["software-change"]["how"] == "propose-new"
    assert c.writes == before


def test_a_key_must_name_an_item_shipped_before_it(brain):
    c, cv = brain
    spec = copy.deepcopy(SPEC)
    spec["workflows"][0]["activities"][2]["disciplines"] = ["baseline:nothing"]
    with pytest.raises(baseline.BootstrapRefused, match="baseline:nothing"):
        baseline.install(c, "@owner", spec=spec)
    assert c.entries_of_kind("workflow") == []


def test_a_brain_before_the_revision_is_told_to_revise_first(brain):
    c, cv = brain
    baseline.install(c, "@owner", spec=v1())
    props = dict(c.current_definition("workflow")["body"])
    props.pop("kind")
    props.pop("fields")
    c.define_kind("workflow", fields=["name", "about", "text", "activities",
                                      "decisions", "done_when", "carrier",
                                      "persona", "requires"],
                  properties=props, attributed_to="human")
    with pytest.raises(baseline.BootstrapRefused,
                       match="operating_vocabulary.py"):
        baseline.install(c, "@owner")
