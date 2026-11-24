"""T1–T6: fixture-only managed routing, frozen identity and edited recovery."""
from copy import deepcopy

import pytest

from mentis.conversation import posting, versions
from mentis.fluid import commands, message_context as M
from mentis.fluid.inspect import brain_key
from mentis.web import dispatch as D
from tests._loop import world  # noqa: F401
from tests.test_agent_request_routing import a_magnet, a_workspace, own_conversation_of, post


def request(w, mid, *, action="record-only", op="managed-send", **extra):
    body = {"from": {"magnet": mid}, "author": w["who"]["@brian"],
            "text": "  how do I configure a magnet?\r\n🙂é  ",
            "action": action, "op": op, **extra}
    body["parts"] = [{"type": "text", "text": body["text"]}]
    if action == "ask-participant":
        agent = w.setdefault("agent", w["cv"].create_participant("@BoundaryAgent"))
        body.update(addressed_to=[agent], dispatch=[{"participant": agent, "runtime": "codex"}])
    return body


def send(w, body):
    return post(w, body, headers={"X-Mentis-Brain": brain_key(w["cv"]._c)})


def routed(w, answer):
    return w["cv"]._c.operational(act=M.ROUTED, turn=answer["post"])[0]["detail"]


@pytest.mark.parametrize("action", ["record-only", "ask-mentis", "ask-participant"])
@pytest.mark.parametrize("context", ["absent", None, "explicit"])
@pytest.mark.parametrize("origin", ["magnet", "workspace", "own-conversation"])
def test_managed_routes(world, action, context, origin):
    mid = a_magnet(world)
    b = request(world, mid, action=action)
    if context != "absent":
        b["magnet_context"] = (None if context is None else {
            "version": 1, "mode": "ordinary", "configuration_digest":
            M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
            "perspective": None, "references": []})
    if origin == "workspace":
        b.update({"from": {"workspace": a_workspace(world)}, "destination": {"magnet": mid}})
    elif origin == "own-conversation":
        b["from"] = {"conversation": own_conversation_of(world, mid)}
    status, answer = send(world, b)
    assert status == 200, answer
    frozen = routed(world, answer)["managed_context"]
    assert frozen["managed_context_version"] == 1 and frozen["selector"]["mode"] == "ordinary"
    assert frozen["turn"] == frozen["authored_version"] == answer["post"]
    stored = world["cv"]._c.read([answer["post"]])[0]["body"]["parts"]
    assert stored == b["parts"]
    assert M.words(world["cv"], frozen) == b["text"]
    assert frozen["text_digest"] == M.text_digest(b["text"])
    assert len(world["sent"]) == (action != "record-only")


@pytest.mark.parametrize("change", [
    {"magnet_context": {}}, {"magnet_context": {"version": 2}},
    {"magnet_context": []}, {"_magnetAssistance": {}},
    {"mode": "grounded"}, {"grounded": True}, {"retained_answer": True},
    {"dispatch": [{"work": "generated override"}]},
    {"text": "different projection"},
])
def test_preflight_refusals_write_no_domain_record(world, change):
    mid = a_magnet(world)
    b = request(world, mid)
    b.update(change)
    before = world["cv"]._c.advance()
    status, answer = send(world, b)
    assert status in (409, 422), answer
    assert world["cv"]._c.advance() == before
    assert not world["sent"]


def test_brain_owner_and_direct_post_refused(world):
    mid = a_magnet(world)
    b = request(world, mid)
    assert post(world, b, headers={})[0] == 409
    other = world["cv"].create_participant("@Impostor")
    assert send(world, {**b, "author": other})[0] == 403
    status, answer = send(world, b)
    assert status == 200
    assert post(world, {"conversation": answer["home"], "author": b["author"],
                        "text": "bypass", "action": "record-only"}, path="posts")[0] == 422


@pytest.mark.parametrize("changed", ["text", "action", "magnet_context", "dispatch", "replies_to"])
def test_replay_compares_submitted_identity_before_hydration(world, monkeypatch, changed):
    mid = a_magnet(world)
    b = request(world, mid)
    status, first = send(world, b)
    assert status == 200, first
    monkeypatch.setattr(M, "prepare", lambda *a: (_ for _ in ()).throw(AssertionError("fresh hydration")))
    status, replay = send(world, b)
    assert status == 200 and replay["post"] == first["post"] and replay["replayed"]
    different = {**b, changed: {"magnet_context": None, "text": b["text"] + "\n",
        "action": "ask-mentis", "dispatch": [], "replies_to": "ent-newtarget"}[changed]}
    assert send(world, different)[0] == 409


@pytest.mark.parametrize("edit", ["changed", "revert", "delete"])
def test_edited_late_address_and_dispatch_refuse(world, edit):
    mid = a_magnet(world)
    b = request(world, mid)
    status, first = send(world, b)
    assert status == 200
    cv, tid = world["cv"], first["post"]
    original = deepcopy(cv._c.read([tid])[0])
    if edit == "delete":
        versions.delete(cv, tid, by=b["author"], because="fixture deletion")
    else:
        changed = versions.edit(cv, tid, text="changed words", by=b["author"])
        if edit == "revert":
            versions.edit(cv, changed["version"], text=b["text"], by=b["author"])
    agent = cv.create_participant("@LateAgent")
    before = cv._c.operational(act="expectation-recorded", turn=tid)
    out, later = posting.address(cv, cv._c, tid,
        {"action": "ask-participant", "participant": agent, "op": "late"}, by=b["author"], agents=world["state"].agents)
    assert "error" in out and not later
    assert cv._c.operational(act="expectation-recorded", turn=tid) == before
    result = D.dispatch(world["state"], conversation=first["home"], turn=tid,
                        participant=agent, work="must not run")
    assert not result["ok"] and result["before_execution_started"]
    assert cv._c.read([tid])[0] == original
    assert send(world, b)[1]["post"] == tid  # original receipt, no execution
    assert send(world, {**b, "op": "explicit-new-request"})[0] == 200
    assert cv._c.operational(act=M.AUDIT, turn=tid)


def test_canonical_unicode_and_bounds():
    value = {"z": "\r\n🙂é", "a": {"β": True, "x": [1, None, "\\\""]}}
    assert M.canonical(value) == '{"a":{"x":[1,null,"\\\\\\\""],"β":true},"z":"\\r\\n🙂é"}'.encode()
    assert M.digest({"conversation": "ignored", "name": "A"}) != M.digest({"name": "A"})
    with pytest.raises(versions.Refused):
        M.canonical({"bad": "\ud800"})
    with pytest.raises(versions.Refused):
        M.canonical({"bad": 1.0})


@pytest.mark.parametrize("action", ["ask-mentis", "ask-participant"])
def test_real_dispatch_receives_separate_context_and_exact_task(world, action):
    from mentis.execution import RunResult
    from tests._loop import script_every_backend
    mid = a_magnet(world)
    body = request(world, mid, action=action)
    status, first = send(world, body)
    assert status == 200, first
    seen = []
    def perform(spec):
        seen.append(spec)
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
            text="Open Settings to configure the Magnet's sources.", stop_reason="end_turn",
            timing={"prompt_sent": 1.0})
    script_every_backend(world["state"].agents, perform)
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result["ok"], result
    assert len(seen) == 1
    frozen = routed(world, first)["managed_context"]
    assert M.payload(frozen) in seen[0].prompt
    assert body["text"] in seen[0].prompt
    assert world["cv"]._c.read([first["post"]])[0]["body"]["parts"] == body["parts"]
    acts = world["cv"]._c.operational(act=M.AUDIT, turn=first["post"])
    assert {a["detail"]["state"] for a in acts} == {"prepared", "supplied"}
    assert all(a["detail"]["context_digest"] == frozen["context_digest"] for a in acts)


@pytest.mark.parametrize("cut", ["before-summon", "before-send"])
def test_edit_winning_reservation_prevents_execution(world, monkeypatch, cut):
    mid = a_magnet(world)
    body = request(world, mid, action="ask-participant")
    status, first = send(world, body)
    assert status == 200
    svc = world["state"].agents
    called = []
    from tests._loop import script_every_backend
    script_every_backend(svc, lambda spec: called.append(spec))
    name = "agents_resolve" if cut == "before-summon" else "agents_perform"
    original = getattr(svc, name)
    def edit_then(*args, **kw):
        versions.edit(world["cv"], first["post"], text="changed before send", by=body["author"])
        return original(*args, **kw)
    monkeypatch.setattr(svc, name, edit_then)
    result = D.dispatch(world["state"], **world["sent"][0])
    assert not called
    assert result.get("ok") is False or result.get("terminal") == "cancelled", result
    states = [a["detail"]["state"] for a in world["cv"]._c.operational(act=M.AUDIT, turn=first["post"])]
    assert "refused" in states and "supplied" not in states


def test_reference_identity_and_availability_rechecked(world):
    mid = a_magnet(world)
    _, first = send(world, request(world, mid))
    cv = world["cv"]
    parts = cv._c.read([first["post"]])[0]["body"]["parts"]
    selector = {"version": 1, "mode": "ordinary", "configuration_digest":
        M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
        "perspective": None, "references": [{"kind": "post", "ref": first["post"],
            "version": first["post"], "digest": M.digest(parts)}]}
    b = request(world, mid, op="with-reference", magnet_context=selector)
    status, selected = send(world, b)
    assert status == 200, selected
    frozen = M.accepted(cv, turn=selected["post"])
    assert frozen["references"][0]["parts"] == parts
    versions.edit(cv, first["post"], text="changed reference", by=b["author"])
    with pytest.raises(versions.Refused):
        M.accepted(cv, turn=selected["post"])
