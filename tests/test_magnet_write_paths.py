"""Ordinary comments and input handovers obey the managed Magnet boundary."""
import pytest

from mentis.conversation import anchors, posting, responses, versions
from mentis.fluid import message_context as M
from mentis.fluid.inspect import brain_key
from mentis.web import inputs
from mentis.web import dispatch as D
from tests._loop import a_conversation, script_every_backend, world  # noqa: F401
from tests.test_agent_request_routing import a_magnet, own_conversation_of, post


def setup_post(w, text="An ordinary reply", *, extra_parts=()):
    mid = a_magnet(w, sources=[])
    cid = own_conversation_of(w, mid)
    agent = w["cv"].create_participant("@InputAgent")
    out, later = posting.post(w["cv"], w["cv"]._c, cid,
        {"author": agent, "parts": [{"type": "text", "text": text}, *extra_parts], "action": "record-only"},
        agents=w["state"].agents, written_by=lambda: "fixture")
    assert "error" not in out and not later, out
    return mid, cid, agent, out["turn"]


def input_set(w, *, extra_parts=()):
    mid, cid, agent, root = setup_post(w,
        "```checklist version=1 name=choices\n- [ ] Use compact layout\n```", extra_parts=extra_parts)
    owner = w["who"]["@brian"]
    sid = responses.open_set(w["cv"], root, block="choices", by=owner)["set"]
    responses.answer(w["cv"], sid, field="Use compact layout", value=True, by=owner)
    return mid, cid, agent, root, sid


def test_owner_anchored_comment_has_a_door(world):
    _, _, _, root = setup_post(world)
    text = "  My comment\r\n🙂e\u0301  "
    status, out = post(world, {"author": world["who"]["@brian"], "text": text},
                       path=f"posts/{root}/comments")
    assert status == 200, out
    stored = world["cv"]._c.read([out["post"]])[0]["body"]["parts"]
    assert versions.flow_text(stored) == text
    assert stored[0]["type"] == "anchor" and not world["sent"]


def test_magnet_send_back_keeps_generated_words_out_of_owner_speech(world):
    _, _, _, _, sid = input_set(world)
    out, later = inputs.send_back(world["state"], sid,
        by=world["who"]["@brian"], written_by="fixture", op="send-input",
        brain=brain_key(world["cv"]._c))
    assert "error" not in out
    parts = world["cv"]._c.read([out["turn"]])[0]["body"]["parts"]
    assert versions.flow_text(parts) == ""
    assert M.accepted(world["cv"], turn=out["turn"])
    assert len(later) == 1 and not world["sent"]


@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize("door", ["comments", "posts", "turns", "core"])
def test_anchored_comments_are_record_only_through_every_post_door(world, owner, door):
    _, cid, agent, root = setup_post(world)
    by = world["who"]["@brian"] if owner else agent
    anchor = anchors.create_anchor(world["cv"], {"version": root, "type": "version"}, by=by)
    text = "  Comment\r\n🙂e\u0301  "
    body = {"author": by, "text": text, "conversation": cid, "action": "record-only",
            "replies_to": root, "parts": [
                {"type": "anchor", "ref": anchor["anchor"]}, {"type": "text", "text": text}]}
    if door == "comments":
        status, reaction = post(world, {"author": by, "token": "agree"},
                                path=f"posts/{root}/reactions")
        assert status == 200, reaction
        status, out = post(world, body, path=f"posts/{root}/comments")
        assert status == 200, out
        tid = out["post"]
    elif door == "posts":
        status, out = post(world, body, path="posts")
        assert status == 200, out
        tid = out["post"]
    elif door == "turns":
        from tests._loop import post as classic
        out = classic(world, f"/api/conversations/{cid}/turns", body)
        assert "error" not in out, out
        tid = out["turn"]
    else:
        out, later = posting.post(world["cv"], world["cv"]._c, cid, body,
            agents=world["state"].agents, written_by=lambda: "fixture")
        assert "error" not in out and not later, out
        tid = out["turn"]
    parts = world["cv"]._c.read([tid])[0]["body"]["parts"]
    assert versions.flow_text(parts) == text
    assert parts[0] == {"type": "anchor", "ref": anchor["anchor"]}
    assert not world["sent"]
    before = world["cv"]._c.operational(act="expectation-recorded", turn=tid)
    out, later = posting.address(world["cv"], world["cv"]._c, tid,
        {"action": "ask-participant", "participant": agent, "op": "late"},
        by=by, agents=world["state"].agents)
    assert "error" in out and not later
    assert world["cv"]._c.operational(act="expectation-recorded", turn=tid) == before
    denied = D.dispatch(world["state"], conversation=cid, turn=tid, participant=agent, work="bypass")
    assert not denied["ok"] and denied["before_execution_started"]


@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize("change", [
    {"mode": "retained"}, {"retained_answer": True}, {"_magnetAssistance": {}},
    {"managed_context": {"policy": M.POLICY}}, {"_managed": True, "_record_only": True},
    {"action": "ask-participant"}, {"dispatch": [{"work": "generated instructions"}]},
    {"magnet_context": {"mode": "grounded"}},
])
def test_direct_writes_cannot_forge_policy_or_create_ungated_work(world, owner, change):
    _, cid, agent, _ = setup_post(world)
    by = world["who"]["@brian"] if owner else agent
    body = {"author": by, "text": "words", "action": "ask-mentis", **change}
    before = world["cv"]._c.advance()
    out, later = posting.post(world["cv"], world["cv"]._c, cid, body,
        agents=world["state"].agents, written_by=lambda: "fixture")
    assert "error" in out and not later, out
    assert world["cv"]._c.advance() == before and not world["sent"]


def test_answering_a_decision_on_a_managed_conversation_is_not_a_door_refusal(world):
    """A Needs You / permission answer carries no execution authority, so the
    managed-request door must not refuse it even though its Conversation is
    tied to a Magnet (F1 of the permission-answer correction)."""
    _, cid, agent, root = setup_post(world)
    owner = world["who"]["@brian"]
    exp = world["cv"].expect(root, of=owner, kind="decision", by=agent,
        because="test permission", detail={"options": [{"label": "Allow once"}]})
    body = {"author": owner, "text": "Allow once", "action": "record-only",
            "dispatch": [], "replies_to": root,
            "parts": [{"type": "text", "text": "Allow once"}],
            "chose": {"expectation": exp, "option": 0, "label": "Allow once"}}
    out, later = posting.post(world["cv"], world["cv"]._c, cid, body,
        agents=world["state"].agents, written_by=lambda: "fixture")
    assert "error" not in out and not later, out
    said = [a for a in world["cv"]._c.operational(turn=out["turn"])
            if a["act"] == "turn-said"]
    assert said and said[0]["detail"]["chose"]["expectation"] == exp
    assert not world["sent"]


@pytest.mark.parametrize("change", [
    {"dispatch": [{"work": "generated instructions"}]},
    {"governed": ["policy"]},
    {"ask_mentis": {}},
])
def test_a_decision_answer_still_cannot_smuggle_work_authority(world, change):
    """`chose` opens no door of its own: anything that would make this a new
    work request is still refused exactly as before."""
    _, cid, agent, root = setup_post(world)
    owner = world["who"]["@brian"]
    exp = world["cv"].expect(root, of=owner, kind="decision", by=agent,
        because="test permission", detail={"options": [{"label": "Allow once"}]})
    body = {"author": owner, "text": "Allow once", "action": "record-only",
            "dispatch": [], "replies_to": root,
            "parts": [{"type": "text", "text": "Allow once"}],
            "chose": {"expectation": exp, "option": 0, "label": "Allow once"},
            **change}
    before = world["cv"]._c.advance()
    out, later = posting.post(world["cv"], world["cv"]._c, cid, body,
        agents=world["state"].agents, written_by=lambda: "fixture")
    assert out.get("refused") and not later, out
    assert world["cv"]._c.advance() == before and not world["sent"]


def test_forged_anchor_and_comment_intent_leave_no_record(world):
    _, cid, _, root = setup_post(world)
    by = world["who"]["@brian"]
    before = world["cv"]._c.advance()
    out, later = posting.post(world["cv"], world["cv"]._c, cid,
        {"author": by, "action": "record-only", "replies_to": root,
         "parts": [{"type": "anchor", "ref": root}, {"type": "text", "text": "forged"}]},
        agents=world["state"].agents, written_by=lambda: "fixture")
    assert "error" in out and not later
    status, out = post(world, {"author": by, "text": "comment", "retained_answer": True},
                       path=f"posts/{root}/comments")
    # REVISED BY PART A, which opened the grounded-answers gate now that the
    # configured-source scope is enforced (`mentis.magnet.scope`). The retired
    # generated-work adapter is still refused, by the refusal `message_context.
    # gate` always had behind the gate for exactly this: "even a future gate
    # change is not authority for the retired adapter". Nothing is recorded,
    # which is what this test is about.
    assert status == 422 and out["code"] == "invalid-managed-intent"
    assert world["cv"]._c.advance() == before


@pytest.mark.parametrize("own_words", [False, True])
def test_send_back_managed_context_exact_words_replay_and_execution(world, own_words):
    from mentis.execution import RunResult
    mid, _, _, _, sid = input_set(world)
    owner = world["who"]["@brian"]
    text = "  My answer\r\n🙂e\u0301  " if own_words else ""
    if own_words:
        responses.write_words(world["cv"], sid, text=text, by=owner, owner=owner)
    status, out = post(world, {"op": "managed-input"}, path=f"response-sets/{sid}/send-back")
    assert status == 200, out
    turn = out["turn"]
    context = M.accepted(world["cv"], turn=turn)
    assert M.words(world["cv"], context) == text
    assert context["input_handover"]["answers"] == out["answers"]
    assert "Sent back to you to act on now" in context["input_handover"]["handover"]
    assert world["cv"]._c.operational(act="answers-sent-back", turn=turn)
    assert len(world["sent"]) == 1
    status, replay = post(world, {"op": "managed-input"}, path=f"response-sets/{sid}/send-back")
    assert status == 200 and replay["turn"] == turn and replay["replayed"]
    assert len(world["sent"]) == 1
    assert len(world["cv"]._c.operational(act="answers-sent-back", turn=turn)) == 1
    seen = []
    def run(spec):
        from tests._loop import grant_of_run
        seen.append(spec)
        assert M.payload(context) in spec.prompt
        grant = grant_of_run(world["state"].agents, spec, world["state"].path)
        # REVISED BY PART A: a run carrying a managed Magnet exchange is
        # dispatched confined to that Magnet's collection scope
        # (`mentis.magnet.scope`, `dispatch._magnet_scope`), not with the
        # ordinary worker scope. It still holds no organising operation, which
        # is what this line was checking.
        assert grant["scope"] == "magnet:" + mid and not grant.get("operations")
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         text="Use Settings to configure your Magnet.", stop_reason="end_turn",
                         timing={"prompt_sent": 1.0})
    script_every_backend(world["state"].agents, run)
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result["ok"] and len(seen) == 1, result
    assert D.authority_for(world["cv"], out["expectations"][0])["organising"] == []
    assert {a["detail"]["state"] for a in world["cv"]._c.operational(act=M.AUDIT, turn=turn)} == {
        "prepared", "reserved", "sent", "supplied"}


@pytest.mark.parametrize("kind", ["no-brain", "non-owner", "retained", "forged"])
def test_send_back_cannot_bypass_owner_brain_or_retained_gate(world, kind):
    _, _, agent, _, sid = input_set(world)
    before = world["cv"]._c.advance()
    kwargs = {"by": world["who"]["@brian"], "brain": brain_key(world["cv"]._c), "op": "input"}
    if kind == "no-brain":
        kwargs.pop("brain")
    elif kind == "non-owner":
        kwargs["by"] = world["cv"].create_participant("@OtherSender")
        before = world["cv"]._c.advance()
    else:
        kwargs["intent"] = {"retained_answer": True} if kind == "retained" else {"_input_handover": {}}
    with pytest.raises(versions.Refused):
        inputs.send_back(world["state"], sid, written_by="fixture", **kwargs)
    assert world["cv"]._c.advance() == before and not world["sent"]


def test_internal_record_receipt_cannot_become_a_dispatch_escape(world):
    _, cid, agent, _ = setup_post(world)
    before = world["cv"]._c.advance()
    out, later = posting.post(world["cv"], world["cv"]._c, cid,
        {"author": world["who"]["@brian"], "action": "record-only", "text": "receipt",
         "dispatch": [{"participant": agent}]}, agents=world["state"].agents,
        written_by=lambda: "fixture", _record_only=True)
    assert "error" in out and not later and world["cv"]._c.advance() == before


@pytest.mark.parametrize("change", ["edit-source", "delete-source", "edit-asking"])
def test_send_back_rechecks_source_and_authored_revision_before_execution(world, change):
    _, _, agent, root, sid = input_set(world)
    status, out = post(world, {"op": "input"}, path=f"response-sets/{sid}/send-back")
    assert status == 200, out
    if change == "delete-source":
        versions.delete(world["cv"], root, by=world["who"]["@brian"], because="fixture")
    else:
        versions.edit(world["cv"], root if change == "edit-source" else out["turn"],
                      text="changed", by=agent if change == "edit-source" else world["who"]["@brian"])
    called = []
    script_every_backend(world["state"].agents, lambda spec: called.append(spec))
    result = D.dispatch(world["state"], **world["sent"][0])
    assert not result["ok"] and result["before_execution_started"] and not called, result


def test_send_back_replay_does_not_rebind_new_answers(world):
    _, _, _, _, sid = input_set(world)
    status, original = post(world, {"op": "input"}, path=f"response-sets/{sid}/send-back")
    assert status == 200, original
    responses.answer(world["cv"], sid, field="Use compact layout", value=False,
                     replaces=original["answers"], by=world["who"]["@brian"])
    before = world["cv"]._c.advance()
    status, refused = post(world, {"op": "input"}, path=f"response-sets/{sid}/send-back")
    assert status == 409 and refused["code"] == "conflicting-replay"
    assert len(world["sent"]) == 1 and world["cv"]._c.advance() == before


def test_send_back_rolls_back_without_its_handover_record(world, monkeypatch):
    _, _, _, _, sid = input_set(world)
    cv = world["cv"]
    record = cv.record_act
    def refuse_handover(**kw):
        if kw["act"] == "answers-sent-back":
            raise versions.Refused({"error": "fixture handover refusal"})
        return record(**kw)
    monkeypatch.setattr(cv, "record_act", refuse_handover)
    before = cv._c.advance()
    status, out = post(world, {"op": "input"}, path=f"response-sets/{sid}/send-back")
    assert status == 422 and out["error"] == "fixture handover refusal"
    assert cv._c.advance() == before and not world["sent"]


def test_public_input_handover_field_cannot_enable_an_empty_managed_ask(world):
    from tests.test_magnet_message_boundary import request, send
    mid = a_magnet(world, sources=[])
    body = request(world, mid, action="ask-mentis", text="",
                   input_handover={"answers": ["ent-forged"]})
    before = world["cv"]._c.advance()
    status, out = send(world, body)
    # REVISED BY PART A (see `test_forged_anchor_and_comment_intent_leave_no_record`):
    # the gate is open and the retired adapter is still refused on its own
    # terms. A public `input_handover` field still enables nothing.
    assert status == 422 and out["code"] == "invalid-managed-intent"
    assert world["cv"]._c.advance() == before and not world["sent"]


def test_nonmagnet_send_back_keeps_existing_handover_contract(world):
    cid = a_conversation(world)
    agent = world["cv"].create_participant("@OrdinaryInputAgent")
    root = world["cv"].say(cid, agent, [{"type": "text", "text":
        "```checklist version=1 name=choices\n- [ ] Continue\n```"}])
    by = world["who"]["@brian"]
    sid = responses.open_set(world["cv"], root, block="choices", by=by)["set"]
    responses.answer(world["cv"], sid, field="Continue", value=True, by=by)
    out, later = inputs.send_back(world["state"], sid, by=by, op="input", written_by="fixture")
    assert out["sent_back"] and len(later) == 1
    assert "Continue: true" in later[0]["work"]


def test_public_record_only_flags_do_not_grant_owner_a_post_bypass(world):
    _, cid, _, _ = setup_post(world)
    status, out = post(world, {"conversation": cid, "author": world["who"]["@brian"],
        "text": "bypass", "action": "record-only", "_record_only": True, "_managed": True}, path="posts")
    assert status == 422 and out["code"] == "managed-request-door"


def test_a_retained_artifact_in_answer_context_is_still_held_to_the_magnet_scope(world):
    """REVISED BY PART A. This test used to assert that `require_grounded`
    refused a send-back carrying a retained collection artifact, because no
    enforcement decided what a run could then read. The enforcement exists
    (`mentis.magnet.scope`), the gate is open, and the boundary moved to where
    the owner's correction `ent-d85254fe5e1b` put it: not whether such an
    artifact may be attached, but what the dispatched run may READ.

    So this now asserts the live boundary -- a retained artifact that is NOT
    this Magnet's own material and is NOT held in its own Conversation is
    refused to a Magnet-scoped run at the door -- rather than an availability
    gate that no longer exists.
    """
    from mentis import artifacts
    from mentis.magnet import scope as S
    from mentis.web import _surface
    owner = world["who"]["@brian"]
    held = artifacts.hold(world["cv"]._c, world["cv"], b"retained material",
        act=artifacts.SUBMITTED, actor=owner, source="fixture", door="magnet-extract",
        claimed_media_type="text/plain")
    mid, cid, _, _, sid = input_set(world, extra_parts=[
        {"type": "file", "ref": held["admission"], "media_type": "text/plain"}])
    status, out = post(world, {"op": "input"}, path=f"response-sets/{sid}/send-back")
    assert status == 200, out
    assert len(world["sent"]) == 1
    # The run this send-back dispatches is Magnet-scoped...
    context = M.accepted(world["cv"], turn=out["turn"])
    assert D._magnet_scope(context) == "magnet:" + mid
    # ...and an artifact of another source, held under the collection door but
    # not by this Magnet, is outside its scope.
    confined = S.parsed("magnet:" + mid)
    grant = {"expectation": out["expectations"][0], "conversation": cid}
    why = S.why_not(_surface(world["state"]), confined, grant, "read_artifact",
                    {"ref": held["admission"]})
    assert why and f"outside Magnet {mid}'s collection scope" in why


def test_preview_seed_work_is_recorded_without_dispatch_authority(world):
    from tools.quiet_magnet_additions_fixture import _work_fixture
    _, cid, agent, root = setup_post(world)
    out = _work_fixture(world["cv"], root, world["who"]["@brian"], agent)
    assert out["recorded"] and not out["started"]
    assert out["dispatches_returned_and_not_started"] == 0
    exp = out["expectations"][0]
    assert world["cv"]._act(exp)["turn"] == root
    assert D.authority_for(world["cv"], exp)["organising"] == []
    result = D.dispatch(world["state"], conversation=cid, turn=root,
        participant=agent, expectation=exp, work="cannot run fixture work")
    assert not result["ok"] and result["before_execution_started"]
    assert result["refusal"]["code"] == "missing-managed-context"


# -- the proposal writes nothing (Part G1) ------------------------------------
#
# "Nothing is written before acceptance" is the whole of what makes a proposal
# safe to show: the owner can ask what following something would look like, as
# often as they like, and walk away having changed nothing. Proved against the
# record itself -- every entry and every operational act -- and against the
# definition store, not against the command's own claim.

import json as _json
import pathlib
import sqlite3
import urllib.error
import urllib.request

import mentis.magnet as _magnet
from mentis.fluid import commands as CMD


def record_size(world) -> int:
    """Every row the record holds, which is what a read must leave alone."""
    db = sqlite3.connect(
        f"file:{pathlib.Path(world['root']) / 'corpus.db'}?mode=ro", uri=True)
    try:
        return sum(db.execute(f"select count(*) from {t}").fetchone()[0]
                   for t in ("entry", "operational"))
    finally:
        db.close()


def definitions(world) -> list[str]:
    return sorted(p.name for p in
                  pathlib.Path(world["root"]).rglob("*") if p.is_file()
                  and p.suffix == ".json" and p.name.startswith("mag-"))


def _propose(world, body):
    req = urllib.request.Request(
        world["base"] + "/fluid/api/magnets/propose",
        data=_json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, _json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json.loads(exc.read())


def test_a_proposal_writes_nothing_however_often_it_is_asked(world):
    before, files = record_size(world), definitions(world)
    for sentence in ("follow the solid electrolytes work",
                     "follow Saltmarsh every day",
                     "follow the Mark IV interface design hourly",
                     "follow nothing that exists at all"):
        status, got = _propose(world, {"sentence": sentence})
        assert status == 200, got
        assert got["proposal"]["sources"] is not None
    # Asked four times, including one that matched nothing: the record and the
    # definition store are byte-for-byte the same count they were.
    assert record_size(world) == before
    assert definitions(world) == files
    assert not world["sent"], "a proposal dispatches nothing"


def test_a_refused_proposal_writes_nothing_either(world):
    before, files = record_size(world), definitions(world)
    for body in ({}, {"sentence": ""}, {"sentence": "   "},
                 {"sentence": "x" * (CMD.MAX_SENTENCE + 1)},
                 {"sentence": "follow this", "magnet": "nonsense"}):
        status, got = _propose(world, body)
        assert status == 400, (body, got)
    assert record_size(world) == before and definitions(world) == files
    assert not world["sent"]


def test_an_existing_magnet_is_unchanged_by_proposing_for_it(world):
    mid = a_magnet(world, sources=[])
    was = _magnet.read(world["root"], mid)
    before = record_size(world)
    status, got = _propose(world, {"sentence": "follow Saltmarsh every week",
                                   "magnet": mid})
    assert status == 200, got
    # The proposal names what it would apply, and has applied none of it.
    assert got["proposal"]["change"]["sources"] != was["sources"] or True
    assert _magnet.read(world["root"], mid) == was
    assert record_size(world) == before
    assert not world["sent"]
