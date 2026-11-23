"""Independent reviewer's own probes for H6's durable rename verb.

Not part of the candidate. Written by the review, in the review's own clone, to
check the declared property from the reviewer's assertions rather than the
builder's.
"""
import json
import uuid

import pytest

from mentis.conversation.versions import Refused
from mentis.fluid.inspect import brain_key
from mentis.magnet import perspectives as P
from mentis.spine import held
from tests.test_magnet_perspectives import (inquiry, cmd, create, owner_http,  # noqa: F401
    world, built, MAGNET, artifact_of, define_from, ask_commit, send, JSON_HEADERS)  # noqa: F401


def _label(w, topic):
    one = [t for t in w.cv.topics(P.home(w.state, MAGNET)) if t["id"] == topic][0]
    return (one.get("body") or {}).get("name", one.get("name"))


def test_probe_topic_label_does_not_follow_the_rename(inquiry):
    w = inquiry
    topic = create(w, name="Created label")["perspective"]
    before = _label(w, topic)
    cmd(w, "rename", topic, name="Owner's new name")
    after = _label(w, topic)
    assert P.state(w.state, MAGNET, topic)["name"] == "Owner's new name"
    # The Conversation's own Topic list still reads the create-time label.
    assert after == before == "Created label"


def test_probe_rename_of_a_retired_perspective_is_accepted(inquiry):
    w = inquiry
    topic = create(w, name="Before retirement")["perspective"]
    cmd(w, "retire", topic, reason="done with it")
    assert P.state(w.state, MAGNET, topic)["retired"] is True
    cmd(w, "rename", topic, name="Renamed while retired")
    state = P.state(w.state, MAGNET, topic)
    assert state["name"] == "Renamed while retired" and state["retired"] is True


def test_probe_rename_refuses_a_reason_other_lifecycle_writes_accept(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    before = w.corpus.advance()
    with pytest.raises(Refused) as exc:
        cmd(w, "rename", topic, name="New name", reason="the old one was wrong")
    assert exc.value.refusal["code"] == "invalid-fields"
    assert w.corpus.advance() == before


def test_probe_every_earlier_name_stays_readable_in_history(inquiry):
    w = inquiry
    topic = create(w, name="First")["perspective"]
    cmd(w, "rename", topic, name="Second")
    cmd(w, "rename", topic, name="Third")
    names = [e["data"]["name"] for e in P.history(w.state, MAGNET, topic)["events"]
             if e["event"] in ("created", "rename")]
    assert names == ["First", "Second", "Third"]
    snapshots = [json.loads(held.read(w.root, e["snapshot"]["digest"]))
                 for e in P.history(w.state, MAGNET, topic)["events"] if e["event"] == "rename"]
    assert [s["data"]["name"] for s in snapshots] == ["Second", "Third"]
    assert P.state(w.state, MAGNET, topic)["name"] == "Third"


def test_probe_renaming_a_branch_child_leaves_the_parent_alone(inquiry):
    w = inquiry
    parent = create(w, name="Parent")["perspective"]
    child = cmd(w, "branch", parent, name="Child", question="And the branch?")["perspective"]
    cmd(w, "rename", child, name="Renamed child")
    assert P.state(w.state, MAGNET, parent)["name"] == "Parent"
    assert P.state(w.state, MAGNET, child)["name"] == "Renamed child"


def test_probe_an_op_key_cannot_cross_from_rename_to_another_verb(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    op = "shared-" + uuid.uuid4().hex[:8]
    body = {"brain": brain_key(w.corpus), "op": op, "name": "Renamed once"}
    P.command(w.state, MAGNET, topic, "rename", body, written_by="probe")
    with pytest.raises(Refused) as exc:
        P.command(w.state, MAGNET, topic, "retire",
                  {"brain": brain_key(w.corpus), "op": op}, written_by="probe")
    assert "different request" in str(exc.value.refusal.get("error", exc.value.refusal))
    assert P.state(w.state, MAGNET, topic)["retired"] is False
    assert P.state(w.state, MAGNET, topic)["name"] == "Renamed once"


def test_probe_renaming_does_not_unblock_grounded_answers(inquiry, monkeypatch):
    w = inquiry
    topic = create(w)["perspective"]
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    cmd(w, "rename", topic, name="Still blocked")
    for verb in ("prepare", "reconcile", "finalize"):
        with pytest.raises(Refused) as exc:
            P.command(w.state, MAGNET, topic, verb,
                      {"brain": brain_key(w.corpus), "op": str(uuid.uuid4())})
        assert exc.value.refusal["code"] == "grounded-answers-blocked"
    detail = P.route_read(w.state, MAGNET, [topic], lambda k, d=None: d)
    assert detail["name"] == "Still blocked" and detail["grounded_answers"] is False


def test_probe_rename_survives_a_reopened_store_and_keeps_the_question(inquiry):
    w = inquiry
    created = create(w, name="Original")
    topic = created["perspective"]
    cmd(w, "rename", topic, name="Durable")
    from mentis.web import _State
    reopened = _State(str(w.root))
    try:
        state = P.state(reopened, MAGNET, topic, detail=True)
        assert state["name"] == "Durable"
        assert state["current_question"]["revision"] == created["question"]["ref"]
        assert state["perspective"] == topic
    finally:
        reopened.agents.close()
        reopened.corpus._store.close()
