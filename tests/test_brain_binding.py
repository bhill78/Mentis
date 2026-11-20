"""A decision made on one Brain is never recorded in another (owner, 2026-11-20, "Needs You
Safety"): `GET /fluid/api/needs-you/brain` names the Brain served, and a write that names
another (`X-Mentis-Brain`) is refused before anything is written.

The identity is the Brain's id and an instance fingerprint of its id, the folder it is served
from and the last restore Mentis recorded in it: stable across requests, different for a copy
served elsewhere and for a copy restored in place. It never tells where the Brain is.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request

import pytest

from mentis.fluid import inspect
from mentis.spine.backup import RESTORED_ACT
from tests._loop import world  # noqa: F401
from tests.needs_you_kinds import build


def get(world, path):
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def post(world, path, payload, brain=None):
    headers = {"X-Mentis-Client": "1", "Content-Type": "application/json"}
    if brain is not None:
        headers["X-Mentis-Brain"] = brain
    req = urllib.request.Request(world["base"] + path, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture()
def kinds(world):
    return build(world)


def key(world):
    b = get(world, "/fluid/api/needs-you/brain")["brain"]
    return f"{b['corpus_id']}@{b['instance']}"


def answer(world, kinds, op, brain=None, text="Keep it"):
    """The owner choosing "Keep it" on the fixture's own decision, under `op`."""
    cv, w = world["cv"], kinds
    conv = w["cid"]
    body = {"author": world["who"]["@brian"], "parts": [{"type": "text", "text": text}], "text": text,
            "addressed_to": [], "topics": [], "because": f"answering expectation {w['own']}",
            "action": "record-only", "dispatch": [], "replies_to": w["own_post"], "op": op,
            "chose": {"expectation": w["own"], "option": 0, "label": "Keep it"}}
    return conv, post(world, f"/api/conversations/{conv}/turns", body, brain)


def recorded(world, op):
    """What the server says the keyed write came to: a read."""
    return get(world, f"/api/operations?op={op}&author={world['who']['@brian']}")["recorded"]


def acts(world):
    return len(world["state"].corpus.operational())


def test_the_brain_is_named_without_where_it_is_and_stays_the_same(world, kinds):
    st = world["state"]
    first = get(world, "/fluid/api/needs-you/brain")
    again = get(world, "/fluid/api/needs-you/brain")
    assert first == again, "the same Brain, request after request"
    root = st.corpus.root
    want = hashlib.sha256(f"{st.corpus.corpus_id}\0{root}\0".encode("utf-8")).hexdigest()[:16]
    assert first["brain"] == {"corpus_id": st.corpus.corpus_id, "instance": want}
    whole = json.dumps(first)
    assert str(root) not in whole and str(root).replace("\\", "/") not in whole


def test_a_copy_restored_in_place_is_not_the_brain_it_was_copied_from(world, kinds):
    """The same id and folder: only the restore Mentis recorded in it tells it apart. A server
    opens it afresh (a restore takes the Brain's exclusive lock), so a new opening reads it."""
    st = world["state"]
    before = inspect.brain_of(st.corpus)["instance"]
    st.corpus.append_operational({"id": "opr-restoredabc1", "at": 1.0, "actor": "mentis-migration",
                                  "act": RESTORED_ACT, "because": "restored from backup b1",
                                  "about": [], "detail": {"restore_id": "rst-1"}}) \
        if hasattr(st.corpus, "append_operational") else st.corpus._store.append_operational(
            {"id": "opr-restoredabc1", "at": 1.0, "actor": "mentis-migration", "act": RESTORED_ACT,
             "because": "restored from backup b1", "about": [], "detail": {"restore_id": "rst-1"}})
    assert inspect.brain_of(st.corpus)["instance"] == before, "read once per opened Brain"
    del st.corpus._mentis_instance                           # as a server opening it afresh
    after = inspect.brain_of(st.corpus)["instance"]
    assert after != before
    want = hashlib.sha256(f"{st.corpus.corpus_id}\0{st.corpus.root}\0opr-restoredabc1".encode()).hexdigest()[:16]
    assert after == want


def test_an_answer_naming_this_brain_is_recorded_once_however_often_it_is_sent(world, kinds):
    """The normal answer, and a lost acknowledgment retried under the same key: one post."""
    here = key(world)
    conv, (status, got) = answer(world, kinds, "decision:own:k1", here)
    assert status in (200, 201), got
    assert recorded(world, "decision:own:k1")
    n = acts(world)
    conv, (status, again) = answer(world, kinds, "decision:own:k1", here)
    assert status in (200, 201), again
    assert acts(world) == n, "the retry under the same key records nothing more"
    open_now = [i for i in get(world, "/fluid/api/needs-you/items")["items"] if kinds["own"] in (i.get("asks") or [])]
    assert open_now == [], "the decision is answered"


def test_an_answer_naming_another_brain_is_refused_and_writes_nothing(world, kinds):
    here = key(world)
    cid, _, inst = here.partition("@")
    ops_before = acts(world)
    for other in (f"{cid}@0123456789abcdef",              # a copy: the same id, another instance
                  f"corpus-other@{inst}",                   # another Brain altogether
                  "", "nonsense"):
        _, (status, got) = answer(world, kinds, "decision:own:stale", other)
        assert status == 409 and got["kind"] == "BrainChanged", (other, status, got)
        assert "Nothing was recorded" in got["error"]
        assert here not in json.dumps(got) and str(world["state"].corpus.root) not in json.dumps(got)
    assert acts(world) == ops_before, "no post, no act of any kind"
    assert not recorded(world, "decision:own:stale"), "the key was never recorded"
    asked = [i for i in get(world, "/fluid/api/needs-you/items")["items"] if kinds["own"] in (i.get("asks") or [])]
    assert asked, "the decision is still open"
    # the refused key was never recorded, so the same key can still be sent to the right Brain
    _, (status, got) = answer(world, kinds, "decision:own:stale", here)
    assert status in (200, 201), got
    assert recorded(world, "decision:own:stale") and acts(world) > ops_before


def test_a_write_naming_no_brain_is_as_it_always_was(world, kinds):
    """Fluid, agents' own clients and older pages name no Brain: unchanged."""
    conv, (status, got) = answer(world, kinds, "decision:own:plain", None)
    assert status in (200, 201), got


def test_every_write_route_is_guarded_not_only_answers(world, kinds):
    """The check stands before every POST route, Fluid's command door included."""
    for path, body in (("/api/conversations", {"name": "Not made"}),
                       ("/fluid/api/conversations", {"name": "Not made", "author": world["who"]["@brian"]}),
                       (f"/api/entries/{kinds['rule']}/decline", {"attributed_to": world["who"]["@brian"], "because": "no"})):
        status, got = post(world, path, body, "corpus-other@0000000000000000")
        assert status == 409 and got["kind"] == "BrainChanged", (path, status, got)
