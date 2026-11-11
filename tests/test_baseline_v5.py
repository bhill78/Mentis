"""Baseline version 5: installation-neutral defaults (owner decision 2026-11-11).

WHAT MUST HOLD:
  - no shipped item names the day-to-day Brain, this machine's paths or
    release process, a mandatory merge-and-push, or a deployment or drain
    strategy; the software-change Workflow is complete when the request's
    objective is met with evidence, and integration, commit, push, release and
    deployment belong to it only where the request, the installation's own
    Workflow or the owner asks; the version 4 review ruling is unchanged;
  - a Brain seeded at an earlier version -- here a COPY of a fixture Brain
    seeded on disk, reopened as an existing Brain is -- gets each changed item
    only as a PROPOSAL: nothing is established, superseded or rewritten, and its
    installation-specific wording stays the standing text;
  - an owner's own successor (local wording) keeps standing, and the proposal
    names it;
  - nothing seeds or applies the baseline when a server starts.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re
import shutil

import pytest

import mentis.api as api
from mentis.bootstrap import baseline

SPEC = baseline.load()
V4 = baseline.load(pathlib.Path(__file__).resolve().parent / "fixtures" / "baseline"
                   / "baseline-v4.json")
CHANGED = {"software-change", "cli-mars-development", "finish-tests",
           "git-belongs-to-the-work", "coordinated-work"}
# Words that tie a universal default to one installation's process.
INSTALLATION_SPECIFIC = [
    r"day-to-day", r"this machine", r"C:\\", r"Mentis-wt", r"MARS-wt", r"Mark IV",
    r"merged and pushed", r"commit and push", r"\bdrain", r"origin/main",
    r"mentis\.execution", r"live Brain",
]


def v2_from(spec):
    """Version 2 as test_baseline_v3 rebuilds it: temporary-custody back."""
    spec = copy.deepcopy(spec)
    spec["version"] = 2
    for r in spec["rules"]:
        r.pop("delivery", None), r.pop("when", None)
    spec["rules"] = [r for r in spec["rules"] if r["key"] not in (
        "git-belongs-to-the-work", "coordinated-work")] + [{
        "key": "temporary-custody", "carried_from": "x", "status": "x",
        "text": "Source-changing work uses Mentis-provisioned temporary custody; "
                "the serving checkout is not a development workspace."}]
    return spec


def _body(key, spec=SPEC):
    return next(b for k, _, b in baseline.items(spec) if k == key)


def _governed_text(body) -> str:
    return json.dumps(body, ensure_ascii=False)


@pytest.fixture
def brain(tmp_path):
    c = api.create_corpus(str(tmp_path / "brain"))
    yield c, api.brain(c).conversations
    c.close()


def test_version_five_ships_installation_neutral_text():
    assert SPEC["version"] == 5 and V4["version"] == 4
    baseline.validate_spec(SPEC)
    for key, kind, body in baseline.items(SPEC):
        text = _governed_text(body)
        for pattern in INSTALLATION_SPECIFIC:
            assert not re.search(pattern, text, re.I), (key, pattern)
    flow = _body("software-change")
    assert flow["projects"] == []                    # none means any
    assert "objective is met and shown by evidence" in flow["done_when"]
    for text in (flow["text"], flow["done_when"]):
        assert "the request, this installation's own Workflow or the owner asks" in text
    assert "none of them implies another" in flow["text"]
    # Nothing in the shipped Workflow makes delivery a step of its own.
    assert not re.search(r"\b(always|every change must|mandatory)\b", flow["text"], re.I)
    assert not re.search(r"\d", flow["text"])
    # A decision still asks the owner before anything is deployed or released.
    assert any("Deploying or releasing" in d for d in flow["decisions"])


def test_the_review_ruling_and_activities_are_unchanged():
    flow, old = _body("software-change"), _body("software-change", V4)
    assert [a["key"] for a in flow["activities"]] == [a["key"] for a in old["activities"]]
    for new_a, old_a in zip(flow["activities"], old["activities"]):
        assert new_a["who"] == old_a["who"]
        assert new_a.get("disciplines") == old_a.get("disciplines")
    rule = _body("coordinated-work")
    for text in (flow["text"], rule["text"]):
        for said in ("complexity, foundational impact and the cost of finding a "
                     "defect later", "routine styling, simple filters and localised "
                     "changes need none", "shared APIs, governance, execution, "
                     "security and foundational changes warrant it",
                     "not by repeating the whole review"):
            assert said in text


def test_only_the_named_items_changed_from_version_four():
    old = {k: b for k, _, b in baseline.items(V4)}
    new = {k: b for k, _, b in baseline.items(SPEC)}
    assert set(old) == set(new)
    assert {k for k in new if new[k] != old[k]} == CHANGED


def test_a_new_brain_gets_version_five_established(brain):
    c, cv = brain
    out = baseline.install(c, "@owner")
    assert out["action"] == "install"
    for key in CHANGED:
        assert out["items"][key]["how"] == "establish"
        entry = c.read([out["items"][key]["entry"]])[0]
        assert entry["origin"] == f"bootstrap:mentis-baseline@5/{key}"
        assert c.stands(entry["id"])["stands"]


def _standing(c):
    return {e["id"]: json.dumps(c.read([e["id"]])[0]["body"], sort_keys=True)
            for kind in ("persona", "rule", "decision", "discipline", "workflow")
            for e in c.entries_of_kind(kind) if c.stands(e["id"])["stands"]}


@pytest.mark.parametrize("seeded", ["v4", "v2"])
def test_an_existing_brain_copy_gets_proposals_only(tmp_path, seeded):
    """Seed a fixture Brain on disk at the earlier version, close it, COPY it,
    and update only the copy: the fixture stays as it was, and the copy gets
    proposals, never an established or rewritten item."""
    prior = V4 if seeded == "v4" else v2_from(V4)
    fixture = tmp_path / "fixture"
    c = api.create_corpus(str(fixture))
    first = baseline.install(c, "@owner", spec=prior)["items"]
    c.close()
    copy_dir = tmp_path / "copy"
    shutil.copytree(fixture, copy_dir)

    c = api.open_corpus(str(copy_dir), access="write")
    try:
        before = _standing(c)
        out = baseline.install(c, "@owner")
        assert out["action"] == "update"
        changed = {k for k, r in out["items"].items() if r["how"] != "unchanged"}
        if seeded == "v4":
            assert changed == CHANGED
        for key in changed:
            row = out["items"][key]
            assert row["how"] in ("propose", "propose-new"), (key, row)
            proposal = row.get("proposal") or row["entry"]
            assert not c.stands(proposal)["stands"]
            if row["how"] == "propose":
                assert c.stands(row["entry"])["stands"]          # nothing displaced
                assert row["entry"] in json.dumps(c.proposed_supersessions(proposal))
        # Every entry that stood stands with the same body; nothing new stands.
        assert _standing(c) == before
        flow = first["software-change"]["entry"]
        assert "merged and pushed" in c.read([flow])[0]["body"]["done_when"]
        proposal = out["items"]["software-change"].get("proposal")
        if proposal:
            assert "merged and pushed" not in json.dumps(c.read([proposal])[0]["body"])
        again = baseline.install(c, "@owner")
        assert again["action"] == "unchanged"
    finally:
        c.close()

    # The fixture itself was never written by the update.
    c = api.open_corpus(str(fixture), access="write")
    try:
        assert baseline.applied(api.brain(c).conversations)["detail"]["version"] == prior["version"]
    finally:
        c.close()


def test_an_owners_local_workflow_keeps_standing(brain):
    """The installation's own wording (e.g. merge, push, deploy) is established
    local configuration: the new default proposes to supersede it, displaces
    nothing."""
    c, cv = brain
    first = baseline.install(c, "@owner", spec=V4)["items"]
    old = first["software-change"]["entry"]
    body = dict(c.read([old])[0]["body"])
    body["done_when"] = "Merged, pushed, deployed to our day-to-day Brain and drained."
    mine = c.create_and_establish(kind="workflow", body=body, attributed_to="human")
    c.write(body={"reason": "owner's local process"}, attributed_to="human",
            link={"from": mine, "to": old, "relation": c.superseding_relation()})
    row = baseline.install(c, "@owner")["items"]["software-change"]
    assert row["how"] == "propose" and row["entry"] == mine
    assert c.stands(mine)["stands"]
    assert c.read([mine])[0]["body"]["done_when"].startswith("Merged, pushed, deployed")
    assert mine in json.dumps(c.proposed_supersessions(row["proposal"]))


def test_a_server_start_never_seeds(brain, capsys):
    from mentis.web import _say_intake_is_missing
    c, cv = brain
    before = c.writes
    _say_intake_is_missing(c)
    assert c.writes == before
    assert baseline.applied(cv) is None
    assert "Nothing has been seeded" in capsys.readouterr().out
