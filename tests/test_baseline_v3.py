"""Baseline version 3: the owner-approved operating rules (2026-10-29).

A renamed item (`was`) is its predecessor's successor; each rule is placed at
the delivery level it names on a new Brain; the release data refuses a bad
`was` or delivery. The approved texts are the ones in
docs/cutover/governance-2026-10-29.json, so the baseline's proposal and the
cutover successor are one entry.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import mentis.api as api
from mentis.bootstrap import baseline
from mentis.conversation import WHOLE_BRAIN_SCOPE

SPEC = baseline.load()
GOV = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs" / "cutover"
                  / "governance-2026-10-29.json").read_text(encoding="utf-8"))


def v2():
    """Version 2 as it shipped, rebuilt from v3's shape: temporary-custody back."""
    spec = copy.deepcopy(SPEC)
    spec["version"] = 2
    for r in spec["rules"]:
        r.pop("delivery", None), r.pop("when", None)
    spec["rules"] = [r for r in spec["rules"] if r["key"] not in (
        "git-belongs-to-the-work", "coordinated-work")] + [{
        "key": "temporary-custody", "carried_from": "x", "status": "x",
        "text": "Source-changing work uses Mentis-provisioned temporary custody; "
                "the serving checkout is not a development workspace."}]
    return spec


@pytest.fixture
def brain(tmp_path):
    c = api.create_corpus(str(tmp_path / "brain"))
    yield c, api.brain(c).conversations
    c.close()


def test_the_shipped_rules_are_the_approved_texts():
    shipped = {k: b["text"] for k, kind, b in baseline.items(SPEC) if kind == "rule"}
    approved = {i["baseline_key"]: i["text"] for i in GOV["items"] if i["baseline_key"]}
    assert shipped == approved


def test_a_renamed_item_proposes_to_supersede_what_it_was(brain):
    c, cv = brain
    first = baseline.install(c, "@owner", spec=v2())
    custody = first["items"]["temporary-custody"]["entry"]
    out = baseline.install(c, "@owner", spec=SPEC)
    row = out["items"]["git-belongs-to-the-work"]
    assert row["how"] == "propose" and row["entry"] == custody
    assert custody in json.dumps(c.proposed_supersessions(row["proposal"]))
    assert "temporary-custody" not in out["removed"]
    assert c.stands(custody)["stands"]          # proposing displaces nothing
    assert out["items"]["coordinated-work"]["how"] == "propose-new"


def test_a_new_brain_places_each_rule_at_its_delivery_level(brain):
    c, cv = brain
    out = baseline.install(c, "@owner")
    tests = out["items"]["finish-tests"]["entry"]
    runtime = out["items"]["name-the-runtime"]["entry"]
    assert cv.placement_delivery(tests, WHOLE_BRAIN_SCOPE) == {
        "delivery": "conditional", "when": "running tests"}
    assert (cv.placement_delivery(runtime, WHOLE_BRAIN_SCOPE) or {}).get(
        "delivery") in (None, "full")


def test_bad_release_data_is_refused():
    spec = copy.deepcopy(SPEC)
    spec["rules"][0]["delivery"] = "sometimes"
    with pytest.raises(baseline.BootstrapRefused):
        baseline.validate_spec(spec)
    spec = copy.deepcopy(SPEC)
    spec["rules"][1]["was"] = spec["rules"][0]["key"]
    with pytest.raises(baseline.BootstrapRefused):
        baseline.validate_spec(spec)
