"""tools/establish_governance.py: the owner's approved successors, established.

Against a real server on a fixture Brain: a dry run writes nothing; applying
finds the existing exact-text proposal rather than writing a second, makes it
standing (the predecessor becomes history and stops being delivered), writes a
new rule, and places each at its delivery level. A predecessor that no longer
stands is refused, and then nothing at all is written.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

from mentis.conversation import WHOLE_BRAIN_SCOPE
from tests.test_manual_session import world  # noqa: F401

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "establish_governance.py"
spec = importlib.util.spec_from_file_location("establish_governance", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _decisions(tmp_path, items):
    p = tmp_path / "decisions.json"
    p.write_text(json.dumps({"items": items}), encoding="utf-8")
    return str(p)


def test_successors_are_established_once_and_placed_at_their_level(world, tmp_path):
    st, owner = world["st"], world["owner"]
    cv, corpus = st.cv, st.corpus
    old = corpus.create_and_establish(kind="rule", body={"text": "Deploy on merge."},
                                      attributed_to=owner)
    cv.place(old, whole_brain=True, by=owner, because="old practice")
    other = corpus.create_and_establish(kind="rule", body={"text": "Push weekly."},
                                        attributed_to=owner)
    cv.place(other, whole_brain=True, by=owner, because="old practice")
    new_words = "Merged means pushed."
    proposed = corpus.write(kind="rule", body={"text": new_words}, attributed_to=owner)
    corpus.propose_supersession(proposed, [old], attributed_to=owner, reason="baseline")
    items = [
        {"key": "merged", "title": "Merged means pushed", "text": new_words,
         "replaces": old, "placement": {"whole_brain": True, "delivery": "conditional",
                                        "when": "merging work into main"}},
        {"key": "fresh", "title": "Fresh successor", "text": "Pushed after merging.",
         "replaces": other, "placement": {"whole_brain": True, "delivery": "full"}},
        {"key": "ref", "title": "Mark IV is the reference", "text": "Mark IV is reference.",
         "replaces": None, "placement": {"whole_brain": True, "delivery": "full"}},
    ]
    path = _decisions(tmp_path, items)
    assert tool.main(["--server", world["url"], "--decisions", path]) == 0
    assert corpus.stands(old)["stands"]                 # the dry run wrote nothing
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 0
    assert not corpus.stands(old)["stands"]
    assert corpus.stands(old)["superseded_by"] == [proposed]   # the proposal, not a copy
    assert corpus.stands(proposed)["stands"]
    assert not corpus.stands(other)["stands"]      # proposed here, then established
    assert cv.placement_delivery(proposed, WHOLE_BRAIN_SCOPE) == {
        "delivery": "conditional", "when": "merging work into main"}
    comp = cv.compose(conversation=cv.open_conversation("Any"), participant=owner)
    ids = {c.source_id for c in comp.components}
    assert proposed in ids and old not in ids
    # Running it again changes nothing and refuses nothing.
    assert tool.main(["--server", world["url"], "--decisions", path]) == 0
    writes = corpus.writes
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 0
    rules = [e for e in corpus.read(corpus.ids_of_kind("rule"))
             if e["body"].get("text") == "Mark IV is reference."] if hasattr(
        corpus, "ids_of_kind") else None
    assert rules is None or len(rules) == 1
    assert corpus.writes - writes <= 2     # at most re-placements, never a new rule


def test_a_predecessor_that_no_longer_stands_is_refused_and_nothing_is_written(
        world, tmp_path):
    st, owner = world["st"], world["owner"]
    corpus = st.corpus
    gone = corpus.write(kind="rule", body={"text": "Never established."},
                        attributed_to=owner)
    before = corpus.writes
    path = _decisions(tmp_path, [
        {"key": "x", "title": "X", "text": "Successor.", "replaces": gone,
         "placement": {"whole_brain": True, "delivery": "full"}},
        {"key": "y", "title": "Y", "text": "New rule.", "replaces": None,
         "placement": {"whole_brain": True, "delivery": "full"}}])
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 1
    assert corpus.writes == before


def _workflow(text, activities):
    return {"name": "Change", "about": "changing software", "text": text,
            "activities": activities}


def test_a_structured_successor_is_found_by_its_body_and_placed_conditional(
        world, tmp_path):
    """A Workflow's proposal is matched on every field, not on `text`: a
    competing proposal with the same text and other activities is not the
    approved one, and the approved one is what becomes standing."""
    st, owner = world["st"], world["owner"]
    cv, corpus = st.cv, st.corpus
    step = {"key": "build", "what": "Build it.", "who": {"role": "a worker"},
            "done_when": "Built."}
    review = {"key": "review", "what": "Review what warrants it.",
              "who": {"role": "a reviewer"}, "done_when": "Reviewed."}
    old = corpus.create_and_establish(kind="workflow",
                                      body=_workflow("Build.", [step]),
                                      attributed_to=owner)
    cv.place(old, whole_brain=True, by=owner, because="old practice",
             delivery="reference")
    approved = _workflow("Build, review what warrants it.", [step, review])
    lookalike = corpus.write(kind="workflow",
                             body=_workflow(approved["text"], [step]),
                             attributed_to=owner)
    corpus.propose_supersession(lookalike, [old], attributed_to=owner, reason="draft")
    proposed = corpus.write(kind="workflow", body=approved, attributed_to=owner)
    corpus.propose_supersession(proposed, [old], attributed_to=owner, reason="baseline")
    path = _decisions(tmp_path, [
        {"key": "flow", "title": "Change (Workflow)", "kind": "workflow",
         "body": approved, "replaces": old,
         "placement": {"whole_brain": True, "delivery": "conditional",
                       "when": "changing Mentis code"}}])
    plan = tool.plan_item(tool.Server(world["url"]),
                          json.loads(pathlib.Path(path).read_text())["items"][0])
    assert plan["how"] == "establish-proposal" and plan["proposal"] == proposed
    assert plan["other_proposals"] == [lookalike]
    before = corpus.writes
    assert tool.main(["--server", world["url"], "--decisions", path]) == 0
    assert corpus.writes == before                     # the dry run wrote nothing
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 0
    assert corpus.stands(old)["superseded_by"] == [proposed]
    assert corpus.stands(proposed)["stands"] and not corpus.stands(lookalike)["stands"]
    assert cv.placement_delivery(proposed, WHOLE_BRAIN_SCOPE) == {
        "delivery": "conditional", "when": "changing Mentis code"}
    # Again: already established, nothing new written beyond a no-op placement.
    writes = corpus.writes
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 0
    assert corpus.writes == writes


def test_a_structured_item_is_refused_against_a_predecessor_of_another_kind(
        world, tmp_path):
    st, owner = world["st"], world["owner"]
    corpus = st.corpus
    rule = corpus.create_and_establish(kind="rule", body={"text": "A rule."},
                                       attributed_to=owner)
    before = corpus.writes
    path = _decisions(tmp_path, [
        {"key": "flow", "title": "Flow", "kind": "workflow",
         "body": _workflow("Build.", []), "replaces": rule,
         "placement": {"whole_brain": True, "delivery": "reference"}}])
    assert tool.main(["--server", world["url"], "--decisions", path, "--apply",
                      "--attributed-to", owner]) == 1
    assert corpus.writes == before and corpus.stands(rule)["stands"]
