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
@pytest.mark.parametrize("source_free", [False, True])
def test_real_dispatch_receives_separate_context_and_exact_task(world, action, source_free):
    from mentis.execution import RunResult
    from tests._loop import script_every_backend
    mid = a_magnet(world, sources=[] if source_free else None)
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
    assert {a["detail"]["state"] for a in acts} == {"prepared", "reserved", "sent", "supplied"}
    assert all(a["detail"]["context_digest"] == frozen["context_digest"] for a in acts)
    if source_free:
        assert frozen["configuration"]["sources"] == []


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


def _collected_selector(world, mid, reference):
    return {"version": 1, "mode": "ordinary", "configuration_digest":
            M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
            "perspective": None, "references": [reference]}


COLLECTED = {"kind": "collected_item", "ref": "live:ent-collected11:part:1",
             "version": "adm-0123456789ab", "digest": "b" * 64}


def test_a_collected_record_travels_as_identity_and_carries_no_collected_content(world, monkeypatch):
    """The owner's §§1/6 requirement at the door: a supporting record is what a
    message is about. Membership is the collection's own check, and what is
    frozen is identity -- never captured content, so the retained collection is
    still not answer evidence."""
    from mentis.magnet import collection as C
    mid = a_magnet(world)
    asked = []
    monkeypatch.setattr(C, "member", lambda st, m, r: asked.append((m, dict(r))) or dict(r))
    b = request(world, mid, op="with-collected",
                magnet_context=_collected_selector(world, mid, dict(COLLECTED)))
    status, selected = send(world, b)
    assert status == 200, selected
    assert asked and all(one == (mid, COLLECTED) for one in asked), \
        "every membership check is for exactly what was selected, in this Magnet"
    frozen = routed(world, selected)["managed_context"]
    assert frozen["references"] == [COLLECTED]
    assert set(frozen["references"][0]) == {"kind", "ref", "version", "digest"}
    # The one thing that must not happen: collected material reaching the run.
    # A post reference hydrates its `parts`; a collected record hydrates none,
    # and the prompt still says the collection is not answerable from.
    assert "parts" not in frozen["references"][0]
    payload = M.payload(frozen)
    assert COLLECTED["digest"] in payload and "Grounded answers from the retained collection" in payload
    # And the owner's own words are still exactly the owner's.
    assert M.words(world["cv"], frozen) == b["text"]


@pytest.mark.parametrize("code, status", [
    ("stale-reference", 409), ("restricted-reference", 403), ("invalid-reference", 422)])
def test_a_collected_record_the_collection_refuses_sends_nothing(world, monkeypatch, code, status):
    from mentis.magnet import collection as C
    mid = a_magnet(world)

    def refuse(st, m, r):
        M.refuse(code, "the fixture collection refuses this row", status=status)

    monkeypatch.setattr(C, "member", refuse)
    before = world["cv"]._c.advance()
    b = request(world, mid, op="refused-collected",
                magnet_context=_collected_selector(world, mid, dict(COLLECTED)))
    got, answer = send(world, b)
    assert got == status, answer
    assert answer["code"] == code, answer
    assert world["cv"]._c.advance() == before, "a refused selection writes no domain record"
    assert not world["sent"]


@pytest.mark.parametrize("edited", [False, True])
def test_delayed_intake_retains_permissions_and_refuses_material_edit(world, monkeypatch, edited):
    from mentis.web import resume_intake, resumable_intake
    from mentis.operational import follow_up_of
    from mentis import artifacts
    cv = world["cv"]
    mid = a_magnet(world)
    b = request(world, mid, action="ask-mentis", ask_mentis={
        "reach": "work", "coordinate": False, "follow_up": {"depth": 1},
        "consent": {"mode": "ask", "workspaces": []}})
    with monkeypatch.context() as patch:
        patch.setattr(cv, "intake_carrier", lambda: {
            "resolved": False, "reason": "none", "detail": "fixture outage"})
        status, answer = send(world, b)
    assert status == 200, answer
    exp = answer["expectations"][0]
    if edited:
        versions.edit(cv, answer["post"], text="new asking words", by=b["author"])
        before = cv._c.advance()
        assert exp not in resumable_intake(cv)
        assert cv._c.advance() == before, "a resumable-intake read writes no refusal audit"
    out = resume_intake(cv, exp, by=b["author"], enqueue=lambda **kw: world["sent"].append(kw))
    assert out["resumed"] is (not edited), out
    assert len(world["sent"]) == (not edited)
    if not edited:
        assert artifacts.reach_of(cv, exp)["reach"] == "work"
        assert world["sent"][0]["work"] == b["text"]


@pytest.mark.parametrize("edited", [False, True])
def test_owner_retry_checks_original_authored_revision_before_retry_act(world, edited):
    mid = a_magnet(world)
    b = request(world, mid, action="ask-participant")
    _, answer = send(world, b)
    cv, exp = world["cv"], answer["expectations"][0]
    ask = cv.record_act(actor=world["steward"], act="expectation-recorded",
        conversation=answer["home"], turn=answer["post"], about=[b["author"]],
        detail={"recovery": D.EMPTY_RUN_REVIEW, "retry_of": exp, "carrier": world["agent"]})
    if edited:
        versions.edit(cv, answer["post"], text="changed before retry", by=b["author"])
    starts = D.retry_if_chosen(cv, {"expectation": ask, "option": 0}, by=b["author"], turn=answer["post"])
    assert len(starts) == (not edited)
    if starts:
        assert starts[0]["question"] == b["text"]
    assert len(cv._c.operational(act=D.WORK_RETRIED, caused_by=exp)) == (not edited)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("edited", [False, True])
def test_native_and_fresh_continuations_share_context_or_refuse(world, native, edited):
    mid = a_magnet(world)
    b = request(world, mid, action="ask-participant")
    _, answer = send(world, b)
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution
    ex.resumes = native
    start = world["sent"][0]
    assert D.dispatch(st, **start)["ok"]
    count = len(ex.performed)
    if edited:
        versions.edit(cv, answer["post"], text="changed before continuation", by=b["author"])
    resumed = cv.record_act(actor=b["author"], act="work-resumed", conversation=answer["home"],
        turn=answer["post"], caused_by=start["expectation"])
    result = D.dispatch(st, **{**start, "resumed_from": resumed, "work": "Continue this request."})
    assert result["ok"] is (not edited), result
    assert len(ex.performed) == count + (not edited)
    if not edited:
        frozen = routed(world, answer)["managed_context"]
        assert M.payload(frozen) in ex.performed[-1].prompt
        if native:
            assert M.payload(frozen) in ex.performed[-1].continuation


@pytest.mark.parametrize("door", ["magnet-extract", "magnet-perspective"])
def test_retained_pool_attachment_cannot_bypass_gate(world, door):
    from mentis import artifacts
    mid = a_magnet(world)
    b = request(world, mid)
    held = artifacts.hold(world["cv"]._c, world["cv"], b"pool", act=artifacts.SUBMITTED,
        actor=b["author"], source=f"magnet:{mid}", door=door,
        claimed_media_type="application/json")
    b["parts"].append({"type": "file", "ref": held["admission"]})
    before = world["cv"]._c.advance()
    status, out = send(world, b)
    assert status == 422 and out["code"] == "grounded-answers-blocked"
    assert world["cv"]._c.advance() == before


def test_receipt_replay_does_not_hand_on_owner_stopped_unstarted_work(world):
    mid = a_magnet(world)
    b = request(world, mid, action="ask-participant")
    status, answer = send(world, b)
    assert status == 200
    exp = answer["expectations"][0]
    world["state"].requests_started.clear()  # a reopened process has no in-memory starts
    world["sent"].clear()
    world["cv"].record_act(actor=b["author"], act=D.WORK_PARKED,
        conversation=answer["home"], turn=answer["post"], caused_by=exp,
        because="owner Stop", detail={"owner_stop": True})
    status, replay = send(world, b)
    assert status == 200 and replay["post"] == answer["post"] and replay["replayed"]
    assert not world["sent"]


def test_staged_file_only_message_keeps_intentional_attachment_on_recovery(world):
    from mentis import artifacts
    mid = a_magnet(world)
    b = request(world, mid, action="ask-participant", text="")
    staged = artifacts.stage(world["root"], b"intentional file bytes", "text/plain")
    b["parts"] = [{"type": "file", "ref": staged["staged"], "media_type": "text/plain", "alt": "notes"}]
    status, answer = send(world, b)
    assert status == 200, answer
    frozen = M.accepted(world["cv"], answer["expectations"][0])
    parts = world["cv"]._c.read([answer["post"]])[0]["body"]["parts"]
    assert parts[0]["ref"].startswith("adm-")
    assert parts[0]["ref"] in artifacts.asked_with(world["cv"]._c, world["cv"], answer["expectations"][0])
    assert frozen["authored_parts_digest"] == M.digest(parts)
    assert frozen["submitted_parts_digest"] == M.digest(b["parts"])
    assert M.words(world["cv"], frozen) == ""
    assert send(world, b)[1]["post"] == answer["post"]


def test_reference_only_message_has_no_synthetic_text_parts(world):
    mid = a_magnet(world)
    _, first = send(world, request(world, mid))
    parts = world["cv"]._c.read([first["post"]])[0]["body"]["parts"]
    selection = {"version": 1, "mode": "ordinary", "configuration_digest":
        M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
        "perspective": None, "references": [{"kind": "post", "ref": first["post"],
            "version": first["post"], "digest": M.digest(parts)}]}
    b = request(world, mid, text="", op="reference-only", magnet_context=selection)
    b["parts"] = []
    status, answer = send(world, b)
    assert status == 200, answer
    assert world["cv"]._c.read([answer["post"]])[0]["body"]["parts"] == []
    assert M.accepted(world["cv"], turn=answer["post"])["authored_parts_digest"] == M.digest([])


@pytest.mark.parametrize("action", ["record-only", "ask-mentis", "ask-participant"])
def test_question_chip_only_preserves_empty_authored_parts(world, action):
    from mentis.magnet import perspectives as P
    mid = a_magnet(world, sources=[])
    own_conversation_of(world, mid)
    question = P.command(world["state"], mid, None, "create", {
        "brain": brain_key(world["cv"]._c), "op": "create-question-chip",
        "name": "Setup", "question": "How can I configure this Magnet?"},
        written_by="fixture-owner")
    selection = {"version": 1, "mode": "ordinary", "configuration_digest":
        M.digest(M.definition_body(commands._magnet_config(world["state"], mid))),
        "perspective": {"id": question["perspective"],
                        "question_ref": question["question"]["ref"],
                        "question_digest": question["question"]["digest"]},
        "references": []}
    body = request(world, mid, action=action, text="", magnet_context=selection)
    body["parts"] = []
    status, answer = send(world, body)
    assert status == 200, answer
    assert world["cv"]._c.read([answer["post"]])[0]["body"]["parts"] == []
    accepted = M.accepted(world["cv"], turn=answer["post"])
    assert accepted["selector"] == selection
    assert accepted["question"]["question"] == "How can I configure this Magnet?"
    assert M.words(world["cv"], accepted) == ""
    # Removing the only reference leaves no content and must refuse, with no
    # fabricated copy of the saved question in the author's message.
    body["op"] = "removed-question-chip"
    body["magnet_context"] = {**selection, "perspective": None}
    before = world["cv"]._c.advance()
    assert send(world, body)[0] == 422
    assert world["cv"]._c.advance() == before


def test_search_preserves_historical_pollution_and_new_authored_words(world):
    from mentis.fluid import route
    mid = a_magnet(world)
    b = request(world, mid)
    _, answer = send(world, b)
    cv = world["cv"]
    old = cv.say(answer["home"], b["author"], [{"type": "text", "text":
        "Historical generated instructions: UNIQUE-OLD-POLLUTION"}])
    got = route(world["state"], "/fluid/api/search", {"conversation": [answer["home"]], "q": ["UNIQUE-OLD-POLLUTION"]})
    assert [h["post"] for h in got["hits"]] == [old]
    new = route(world["state"], "/fluid/api/search", {"conversation": [answer["home"]], "q": ["how do I configure a magnet?"]})
    assert [h["post"] for h in new["hits"]] == [answer["post"]]
    assert versions.presented(cv._c, cv._c.read([answer["post"]])[0])["body"]["parts"] == b["parts"]


def test_raw_selector_bound_cannot_be_evaded_by_whitespace_or_escaped_key():
    M.check_raw_selector(b'{"text":"a,}\\\"", "magnet_context":null}')
    M.check_raw_selector(b'{"other":{"nested":[1,{"key":"value"}]},"magnet_context":null}')
    with pytest.raises(versions.Refused):
        M.check_raw_selector(b'{"magnet_context":{' + b" " * M.SELECTOR_MAX + b'}}')
    with pytest.raises(versions.Refused):
        M.check_raw_selector(b'{"magnet_\\u0063ontext":{' + b" " * M.SELECTOR_MAX + b'}}')
    with pytest.raises(versions.Refused):
        M.check_raw_selector(b'{"magnet_context":null,"magnet_context":null}')
    with pytest.raises(versions.Refused):
        M.check_raw_selector(b'{"magnet_context":{"version":2,"version":1}}')


def test_production_canonicalizer_matches_published_cross_language_vectors():
    import json
    from pathlib import Path
    path = Path(__file__).parents[1] / "apps/fluid-web/tests/fixtures/magnet_boundary_vectors.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))
    for v in vectors["canonical"]:
        assert M.canonical(v["value"]).decode("utf-8") == v["canonical"], v["name"]
        assert M.digest(v["value"]) == v["digest"], v["name"]
    for v in vectors["text_digests"]:
        assert M.text_digest(v["text"]) == v["digest"], v["name"]


def test_managed_request_uses_one_validated_snapshot_and_defers_the_mirror(world, monkeypatch):
    from mentis.magnet import snapshot as SNAP
    mid = a_magnet(world, sources=[])
    original = SNAP.take
    reads = []
    def take(*a, **kw):
        snap = original(*a, **kw)
        reads.append(snap)
        return snap
    monkeypatch.setattr(SNAP, "take", take)
    status, answer = send(world, request(world, mid))
    assert status == 200, answer
    assert len(reads) == 1
    context = routed(world, answer)["managed_context"]
    assert context["definition_digest"] == reads[0].digest
    assert context["configuration"] == __import__('json').loads(reads[0].canonical)
    assert context["definition_file_sha256"] == reads[0].file_sha256
    assert reads[0].conversation is None
    assert original(world["root"], mid).conversation == answer["home"]


def test_nonserialized_definition_change_rolls_back_request_before_commit(world, monkeypatch):
    import json
    import mentis.magnet as magnet
    mid = a_magnet(world)
    body = request(world, mid, action="ask-participant")
    before = world["cv"]._c.advance()
    write = commands.write_post
    def bypass_boundary(*a, **kw):
        out = write(*a, **kw)
        path = magnet._path(world["root"], mid)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["identity"] = {"name": "writer bypassed the boundary"}
        path.write_text(json.dumps(data), encoding="utf-8")
        return out
    monkeypatch.setattr(commands, "write_post", bypass_boundary)
    status, answer = send(world, body)
    assert status == 409 and answer["code"] == "definition-not-serialized", answer
    assert world["cv"]._c.advance() == before
    assert not world["sent"]
    assert not world["cv"]._c.operational(act=M.ROUTED)


def test_historic_routed_association_cannot_be_omitted_to_bypass_managed_policy(world):
    mid = a_magnet(world, sources=[])
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Historic own Conversation", attributed_to=owner)
    old = cv.say(cid, owner, [{"type": "text", "text": "historic unchanged question"}])
    cv.record_act(actor=owner, act=M.ROUTED, conversation=cid, turn=old,
                  detail={"own": ["magnet", mid], "starts": [], "op": "old-route"})
    assert not commands._claimed(world["state"], "magnet", mid)
    body = request(world, mid)
    body["from"] = {"conversation": cid}
    assert send(world, body)[0] == 200
    bad = {**body, "op": "retained-override", "dispatch": [{"work": "old generated instructions"}]}
    assert send(world, bad)[0] == 422
    assert post(world, {"conversation": cid, "author": owner, "text": "direct post"}, path="posts")[0] == 422


@pytest.mark.parametrize("wrong", ["outer-version", "author", "writer", "parts"])
def test_consistent_digest_cannot_hide_wrong_authored_identity(world, monkeypatch, wrong):
    mid = a_magnet(world)
    body = request(world, mid, action="ask-participant")
    _, answer = send(world, body)
    cv, corpus = world["cv"], world["cv"]._c
    read = corpus.operational
    def inconsistent(*args, **kwargs):
        rows = read(*args, **kwargs)
        if kwargs.get("act") != M.ROUTED or kwargs.get("turn") != answer["post"]:
            return rows
        rows = deepcopy(rows)
        detail = rows[0]["detail"]
        c = detail["managed_context"]
        if wrong == "outer-version":
            detail["managed_context_version"] = 2
        elif wrong == "author":
            c["author"] = world["agent"]
        elif wrong == "writer":
            c["writer"] = c["observed_writer"] = "forged-observed-writer"
        else:
            c["authored_parts_digest"] = c["asking"]["parts_digest"] = "a" * 64
        c["context_digest"] = M.digest({k: v for k, v in c.items() if k != "context_digest"})
        return rows
    monkeypatch.setattr(corpus, "operational", inconsistent)
    monkeypatch.setattr(world["state"].agents, "agents_summon",
                        lambda *a, **kw: pytest.fail("invalid context must never summon"))
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result["ok"] is False and result["before_execution_started"], result
    audit = read(act=M.AUDIT, turn=answer["post"])[-1]
    assert audit["actor"] == body["author"] and audit["detail"]["state"] == "refused"


def test_post_cutover_missing_snapshot_never_replays_as_legacy(world):
    from mentis.conversation import anchors
    mid = a_magnet(world)
    body = request(world, mid)
    assert send(world, body)[0] == 200  # durable cutover fence
    legacy_shaped = request(world, mid, op="missing-post-cutover-binding")
    operation = {k: v for k, v in legacy_shaped.items() if k != "from"}
    commands._first_time(world["state"], operation, operation["author"], operation["op"],
        anchors.digest({"from": ("magnet", mid), "destination": None}), None,
        "magnet", "magnet", mid, written_by=lambda: "fixture-incomplete-record")
    status, out = send(world, legacy_shaped)
    assert status == 409 and out["code"] == "missing-managed-context", out


@pytest.mark.parametrize("explicit", [False, True])
def test_config_save_waits_through_managed_request_commit_and_replay_is_frozen(world, monkeypatch, explicit):
    import threading
    import mentis.magnet as magnet
    from mentis.magnet import snapshot as SNAP
    from mentis.fluid import arrangements as A
    mid = a_magnet(world, sources=[])
    snap = SNAP.take(world["root"], mid)
    body = request(world, mid)
    if explicit:
        body["magnet_context"] = {"version": 1, "mode": "ordinary", "configuration_digest": snap.digest,
                                  "perspective": None, "references": []}
    key = A.references(world["root"], mid)[0]["arrangement"]
    entered, release, attempted, saved = [threading.Event() for _ in range(4)]
    result, errors = {}, []
    write = commands.write_post
    def paused(*a, **kw):
        out = write(*a, **kw)
        entered.set()
        if not release.wait(10):
            raise AssertionError("fixture never released request commit")
        return out
    monkeypatch.setattr(commands, "write_post", paused)
    conn = world["cv"]._c._store._conn
    class CommitCheck:
        def __getattr__(self, name):
            return getattr(conn, name)
        def execute(self, sql, *args):
            if sql == "COMMIT" and entered.is_set() and not saved.is_set():
                assert not saved.wait(0.1), "definition boundary must remain held through commit"
            return conn.execute(sql, *args)
    monkeypatch.setattr(world["cv"]._c._store, "_conn", CommitCheck())
    def submit():
        try:
            result["request"] = commands.agent_request(world["state"], body,
                written_by=lambda: "fixture-owner", brain=brain_key(world["cv"]._c))
        except BaseException as exc:
            errors.append(exc)
    def save():
        attempted.set()
        try:
            A.reconfigure_magnet(world["root"], key, mid, {"change": {"identity": {"name": "After request"}}})
            saved.set()
        except BaseException as exc:
            errors.append(exc)
    request_thread = threading.Thread(target=submit)
    save_thread = threading.Thread(target=save)
    request_thread.start()
    try:
        assert entered.wait(10)
        save_thread.start()
        assert attempted.wait(5)
        assert not saved.wait(0.2), "save waits while the request holds its snapshot"
        assert magnet._path(world["root"], mid).read_bytes()
    finally:
        release.set()
        request_thread.join(15)
        if save_thread.ident is not None:
            save_thread.join(15)
    assert not request_thread.is_alive() and not save_thread.is_alive()
    assert not errors, errors
    assert saved.is_set()
    status, answer, _ = result["request"]
    assert status == 200, answer
    frozen = routed(world, answer)["managed_context"]
    assert frozen["definition_digest"] == snap.digest
    assert SNAP.take(world["root"], mid).digest != snap.digest
    assert send(world, body)[1]["post"] == answer["post"]
    if explicit:
        assert send(world, {**body, "op": "fresh-stale"})[0] == 409
