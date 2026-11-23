"""Part P fixtures: real append-only Brain and owner/worker HTTP doors.

FakeExecution exercises native product dispatch/grant seams. These tests do not
claim a real MARS/model continuation, a UI check or TEST audience eligibility.
"""
import base64
import copy
import hashlib
import json
import uuid

import pytest

from mentis import artifacts
from mentis.conversation import text
from mentis.conversation.owner import _owner
from mentis.conversation.versions import Refused
from mentis.fluid import commands
from mentis.fluid.inspect import brain_key
from mentis.magnet import perspectives as P, perspectives_evidence as E, perspectives_work as W
from mentis.spine import held
from tests.test_magnet_activation import (world, built, MAGNET, artifact_of, define_from,
    ask_commit, send, JSON_HEADERS)  # noqa: F401


@pytest.fixture
def inquiry(world, monkeypatch):
    w = world
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", True)
    raw = artifact_of(w, op="perspective-batch", change=lambda a: a["page"]["sources"][0]["results"][0].update(
        value={"parts": [{"type": "text", "text": "Original α evidence. A shared observation."}]}))
    define_from(w, raw)
    batch = ask_commit(w, raw)["body"]["artifact"]
    w.batch, w.by = batch, _owner(w.cv)
    w.sent = []
    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: w.sent.append(kw))
    return w


def cmd(w, verb="create", topic=None, **body):
    body = {"brain": brain_key(w.corpus), "op": str(uuid.uuid4()), **body}
    return P.command(w.state, MAGNET, topic, verb, body, written_by="fixture-owner")


def create(w, words="What did the original say?", name="Inquiry"):
    return cmd(w, name=name, question=words)


def prepare(w, created=None, **kwargs):
    c = created or create(w)
    return cmd(w, "prepare", c["perspective"], question=c["question"]["ref"],
               batches=[w.batch["ref"]], selections=[], **kwargs)


def request(w, prepared, *, more="", extra_parts=(), reach="work"):
    agent = w.cv.create_participant("@Perspective" + uuid.uuid4().hex[:6])
    words = prepared["text"] + more
    body = {"from": {"magnet": MAGNET}, "author": w.by,
        "text": words, "parts": [{"type": "text", "text": words}, *prepared["parts"], *extra_parts],
        "op": prepared["request_op"], "action": "ask-participant", "addressed_to": [agent],
        "topics": [prepared["perspective"]],
        "dispatch": [{"participant": agent, "runtime": "codex", "reach": reach, "work": words}]}
    status, out, _ = commands.agent_request(w.state, body, written_by=lambda: "unattributed-local-request")
    assert status == 200, out
    return out["expectations"][0], out["post"], agent, body


def bind(w, prepared, **kwargs):
    req, post, agent, body = request(w, prepared, **kwargs)
    cmd(w, "bind", prepared["perspective"], intent=prepared["intent"], request=req)
    return req, post, agent, body


def live(w, req, agent, *, instance=None, delivered=None):
    """Explicit synthetic grant facts; actual dispatch is tested separately."""
    execution = instance or str(uuid.uuid4())
    exp = w.cv._act(req)
    run = w.cv.record_act(actor=agent, act="execution-started", conversation=exp["conversation"],
                         turn=exp["turn"], execution=execution, caused_by=req)
    # A standing governing id proves delivery facts are present, including
    # an artifact-free delivery; not a claim that synthetic facts ran a model.
    if delivered is None:
        delivered = [w.cv.define_persona("Fixture delivery", "Do the bounded fixture work.")]
    authority = w.state.agents.authority
    authority.authorise_for(execution, {"expectation": req, "run": run, "participant": agent,
        "conversation": exp["conversation"], "delivered": delivered})
    authority._grant(execution, w.state.path)
    return execution, run


def answer(w, req, agent, execution, run, words="A provisional answer."):
    exp = w.cv._act(req)
    post = w.cv.say(exp["conversation"], agent, [text(words)], replies_to=exp["turn"])
    w.cv.record_act(actor=agent, act="turn-said", conversation=exp["conversation"], turn=post,
                    execution=execution, caused_by=req)
    w.cv.record_act(actor=agent, act="result-returned", conversation=exp["conversation"],
                    turn=exp["turn"], execution=execution, caused_by=run, detail={"reply_turn": post})
    return post


def qualify(w, prepared, **kwargs):
    return cmd(w, "reconcile", prepared["perspective"], intent=prepared["intent"], purpose="display", **kwargs)


def owner_http(w, tail, body, *, headers=(), owner=True):
    return send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives{tail}",
        [*JSON_HEADERS, ["X-Mentis-Brain", brain_key(w.corpus)], *headers],
        P.encoded({"brain": brain_key(w.corpus), "op": str(uuid.uuid4()), **body}), owner=owner)


def test_lifecycle_is_append_only_topic_local_and_selection_does_not_configure(inquiry):
    w = inquiry
    config = w.definition_path.read_bytes()
    one, two = create(w), create(w, name="Alternative")
    topic = one["perspective"]
    assert w.cv.conversation_of_topic(topic) == P.home(w.state, MAGNET)
    cmd(w, "selected", perspective=topic)
    cmd(w, "question", topic, text="Exact revised question α", reason="counterexample")
    cmd(w, "challenge", topic, text="Shared source is not independent corroboration")
    cmd(w, "retire", topic, reason="paused")
    assert P.selected(w.state, MAGNET) is None
    with pytest.raises(Refused, match="Resume"):
        cmd(w, "selected", perspective=topic)
    cmd(w, "resume", topic)
    cmd(w, "selected", perspective=two["perspective"])
    assert P.state(w.state, MAGNET, topic)["retired"] is False
    assert w.definition_path.read_bytes() == config and not w.sent
    got = E.bounded_read(w.state, E.descriptor(w.state, one["question"]["ref"]), E.MAX_BYTES)
    assert json.loads(got)["text"] == "What did the original say?"
    for event in P.history(w.state, MAGNET, topic, limit=100)["events"]:
        assert not w.corpus.stands(event["post"])["stands"]


def test_history_is_bounded_stable_after_appends_and_brain_scoped(inquiry):
    w = inquiry
    c = create(w)
    for i in range(107):
        cmd(w, "challenge", c["perspective"], text=f"Challenge {i}")
    first = P.history(w.state, MAGNET, c["perspective"], limit=100)
    assert len(first["events"]) == 100 and first["next"]
    cmd(w, "question", c["perspective"], text="arrived after snapshot")
    second = P.history(w.state, MAGNET, c["perspective"], limit=100, cursor=first["next"])
    assert len(second["events"]) == 9 and second["next"] is None
    assert second["through"] == first["through"]
    assert {r["post"] for r in first["events"]}.isdisjoint(r["post"] for r in second["events"])
    other = create(w, name="other")
    with pytest.raises(Refused, match="cursor"):
        P.history(w.state, MAGNET, other["perspective"], cursor=first["next"])
    with pytest.raises(Refused, match="limit"):
        P.history(w.state, MAGNET, c["perspective"], limit=101)


def test_create_branch_and_list_pagination(inquiry):
    w = inquiry
    c = create(w)
    page = P.listing(w.state, MAGNET, limit=1)
    branch = cmd(w, "branch", c["perspective"], name="Branch", question="Different premise")
    assert branch["perspective"] != c["perspective"]
    assert P.history(w.state, MAGNET, branch["perspective"])["events"][0]["data"]["parent"] == c["perspective"]
    assert len(page["perspectives"]) == 1
    assert len(P.listing(w.state, MAGNET)["perspectives"]) == 2


def test_prepare_then_reload_lens_and_question_changes_keep_same_intent(inquiry):
    w = inquiry
    c = create(w)
    body = {"brain": brain_key(w.corpus), "op": "uncertain-prepare", "question": c["question"]["ref"],
            "batches": [w.batch["ref"]], "selections": []}
    p = P.command(w.state, MAGNET, c["perspective"], "prepare", body)
    before = w.corpus.advance()
    assert P.command(w.state, MAGNET, c["perspective"], "prepare", body)["replayed"]
    assert w.corpus.advance() == before
    other = create(w, name="different")
    cmd(w, "selected", perspective=other["perspective"])
    cmd(w, "question", c["perspective"], text="Changed after uncertain send")
    loaded = W.intent_read(w.state, MAGNET, c["perspective"], p["intent"])["prepared"]
    assert loaded["question"] == p["question"] and loaded["parts"] == p["parts"]
    assert loaded["brain"] == brain_key(w.corpus)
    bind(w, p)
    assert loaded["closure"]["count"] == len(loaded["parts"])
    assert loaded["closure"]["bytes"] == sum(a["size"] for a in loaded["artifacts"])
    assert p["manifest"]["ref"] in {part["ref"] for part in p["parts"]}
    with pytest.raises(Refused, match="different request"):
        P.command(w.state, MAGNET, c["perspective"], "prepare", {**body, "batches": []})


@pytest.mark.parametrize("damage", ["missing", "purged", "corrupt", "range", "attachment"])
def test_required_input_refusals(inquiry, damage):
    w = inquiry
    c = create(w)
    if damage == "range":
        obj = json.loads(held.read(w.root, w.batch["digest"]))
        row = obj["page"]["sources"][0]["results"][0]
        with pytest.raises(Refused, match="range|exceed"):
            cmd(w, "prepare", c["perspective"], question=c["question"]["ref"], batches=[w.batch["ref"]],
                selections=[{"batch": w.batch["ref"], "source": obj["page"]["sources"][0]["key"],
                    "item": row["id"], "version": row["version"], "start": 0, "end": 50000,
                    "stance": "supporting"}])
        return
    if damage == "attachment":
        raw = artifact_of(w, op="attachment", change=lambda a: a["page"]["sources"][0]["results"][0].update(
            value={"parts": [{"type": "file", "ref": "adm-missing123"}]}))
        w.batch = ask_commit(w, raw)["body"]["artifact"]
    elif damage == "missing":
        held.path(w.root, w.batch["digest"]).unlink()
    elif damage == "corrupt":
        held.path(w.root, w.batch["digest"]).write_bytes(b"corrupt")
    else:
        artifacts.purge(w.corpus, w.cv, w.batch["ref"], by=w.by, because="fixture purge")
    with pytest.raises(Refused):
        prepare(w, c)


def test_single_valid_oversized_batch_names_actual_size_and_real_remedy(inquiry):
    w = inquiry
    # Keep every post at the legal per-post character cap. 45 three-byte
    # characters pages spread over three Conversation sources exceed 8 MiB.
    def large(a):
        first = a["page"]["sources"][0]
        first["results"] = [{**first["results"][0], "id": f"ent-{i:012d}", "version": f"ent-{i:012d}",
            "value": {"parts": [{"type": "text", "text": "界" * 65536}]}} for i in range(1, 21)]
        a["page"]["sources"] = []
        config = a["definition"]["value"]
        config["sources"] = []
        for i in range(3):
            src = {"kind": "conversation", "conversation": f"ent-{100+i:012d}"}
            config["sources"].append(src)
            page = copy.deepcopy(first)
            page.update(source=src, key=f"conversation:{src['conversation']}")
            for row in page["results"]:
                row["conversation"] = src["conversation"]
            a["page"]["sources"].append(page)
        raw = json.dumps({**config, "schema_version": 1})
        a["definition"].update(raw=raw, sha256=hashlib.sha256(raw.encode()).hexdigest())
    raw = artifact_of(w, op="oversized-valid", change=large)
    define_from(w, raw)
    w.batch = ask_commit(w, raw)["body"]["artifact"]
    assert w.batch["size"] > E.MAX_BYTES
    with pytest.raises(Refused) as exc:
        prepare(w)
    assert exc.value.refusal["code"] == "batch-too-large"
    assert str(w.batch["size"]) in str(exc.value.refusal)
    assert "8 MiB" in str(exc.value.refusal) and "Collect" in str(exc.value.refusal)


def arbitrary(w, raw=b"independent bytes"):
    got = artifacts.hold(w.corpus, w.cv, raw, act=artifacts.SUBMITTED, actor=w.by,
                         source="fixture-owner", door="human", claimed_media_type="text/plain")
    return got["admission"]


@pytest.mark.parametrize("count,ok", [(32, True), (33, False)])
def test_closure_exact_count_and_overflow_sentinel(inquiry, count, ok, monkeypatch):
    w = inquiry
    all_refs = [arbitrary(w, str(i).encode()) for i in range(count)]
    graph = E.Closure(w.state, MAGNET)
    if ok:
        for ref in all_refs:
            graph.add(ref)
        assert graph.summary()["count"] == 32
    else:
        with pytest.raises(Refused) as exc:
            for ref in all_refs:
                graph.add(ref)
        assert exc.value.refusal["code"] == "reference-limit" and graph.inspected == 33


@pytest.mark.parametrize("extra,ok", [(0, True), (1, False)])
def test_closure_exact_bytes_are_enforced_before_read(inquiry, extra, ok, monkeypatch):
    w = inquiry
    ref = arbitrary(w, b"x" * (E.MAX_BYTES + extra))
    calls = []
    original = E.bounded_read
    def reading(st, desc, remaining):
        calls.append((desc["size"], remaining))
        return original(st, desc, remaining)
    monkeypatch.setattr(E, "bounded_read", reading)
    graph = E.Closure(w.state, MAGNET)
    if ok:
        graph.add(ref)
        assert graph.summary() == {"count": 1, "bytes": E.MAX_BYTES}
    else:
        with pytest.raises(Refused, match="8 MiB"):
            graph.add(ref)
        assert graph.bytes == 0


def test_deep_shared_dependencies_and_active_stack_cycles(inquiry, monkeypatch):
    w = inquiry
    base = arbitrary(w)
    prior = E.descriptor(w.state, base)
    for _ in range(6):
        prior = P.hold(w.state, MAGNET, W._package(w.state, MAGNET, "records", dependencies=[prior]), w.by)
    graph = E.Closure(w.state, MAGNET)
    graph.add(prior["ref"])
    graph.add(base)
    assert graph.summary()["count"] == 7
    # Real immutable hashes make a content-addressed self-cycle impossible to
    # construct. Inject only graph decoding to test the active-stack detector;
    # range/missing/digest tests exercise real bytes independently.
    original = E.native
    def cycle(st, mid, ref, raw, kind=None):
        got = original(st, mid, ref, raw, kind)
        if ref == prior["ref"]:
            got["dependencies"] = [prior]
        return got
    monkeypatch.setattr(E, "native", cycle)
    with pytest.raises(Refused) as exc:
        E.Closure(w.state, MAGNET).add(prior["ref"])
    assert exc.value.refusal["code"] == "dependency-cycle"


def test_originals_deduplicate_version_digest_and_range_with_contradictions(inquiry):
    w = inquiry
    obj = json.loads(held.read(w.root, w.batch["digest"]))
    source = obj["page"]["sources"][0]
    row = source["results"][0]
    sel = {"batch": w.batch["ref"], "source": source["key"], "item": row["id"],
           "version": row["version"], "start": 0, "end": 8, "stance": "supporting"}
    got = E.originals({w.batch["ref"]: obj}, [sel, {**sel, "stance": "contradicting"}])
    assert len(got) == 1 and got[0]["stances"] == ["supporting", "contradicting"]
    assert len(E.deduplicate(got + got)) == 1


def test_reconcile_pending_then_incidental_owner_id_declared_and_counted(inquiry):
    w = inquiry
    p = prepare(w)
    extra = arbitrary(w)
    req, _, agent, _ = bind(w, p, more=f" Also consider {extra}")
    assert qualify(w, p)["status"] == "pending"
    live(w, req, agent)
    unmatched = qualify(w, p)
    assert unmatched["status"] == "unqualified"
    assert unmatched["reachable_not_declared"] == [{"ref": extra, "because": "named-by-owner", "turn": w.cv._act(req)["turn"]}]
    check = qualify(w, p, declared_context=[extra])
    assert check["status"] == "qualified"
    assert check["closure"]["count"] == p["closure"]["count"] + 1
    assert qualify(w, p)["status"] == "qualified"  # explicit declaration retained


@pytest.mark.parametrize("reach", ["conversation", None])
def test_bind_refuses_broader_reach(inquiry, reach):
    w = inquiry
    p = prepare(w)
    req, _, _, _ = request(w, p, reach=reach)
    with pytest.raises(Refused, match="work reach"):
        cmd(w, "bind", p["perspective"], intent=p["intent"], request=req)


def test_bind_refuses_missing_actual_attachment_and_unrelated_request_key(inquiry):
    w = inquiry
    p = prepare(w)
    bad = {**p, "parts": p["parts"][:-1]}
    req, _, _, _ = request(w, bad)
    with pytest.raises(Refused, match="file part"):
        cmd(w, "bind", p["perspective"], intent=p["intent"], request=req)


def test_both_directions_required_unavailable_and_return_growth(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, run = live(w, req, agent)
    assert qualify(w, p)["status"] == "qualified"
    # Purge leaves original manifest intact and cannot substitute current text.
    artifacts.purge(w.corpus, w.cv, w.batch["ref"], by=w.by, because="fixture purge")
    no = qualify(w, p)
    assert no["status"] == "unqualified" and w.batch["ref"] in no["required_unavailable"]


def test_only_producing_run_outputs_are_excluded_prior_returns_are_inputs(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, first = live(w, req, agent)
    produced = artifacts.hold(w.corpus, w.cv, b"first output", act=artifacts.RETURNED, actor=agent,
        source="fixture-return", door="worker-return", execution=instance, caused_by=req)["admission"]
    assert qualify(w, p)["status"] == "qualified"
    second_instance, second = live(w, req, agent, instance=instance)
    check = qualify(w, p)
    assert check["status"] == "unqualified"
    assert any(x["ref"] == produced and x["because"] == "returned-under" for x in check["reachable_not_declared"])
    assert first != second


def test_finalize_freezes_exact_answer_and_rechecks_before_display_and_reuse(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, run = live(w, req, agent)
    a = answer(w, req, agent, instance, run)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=instance, answer=a)
    desc = frozen["answer"]
    obj = E.native(w.state, MAGNET, desc["ref"], held.read(w.root, desc["digest"]), "answer")
    assert obj["answer"] == a and obj["request"] == req and obj["manifest"] == p["manifest"]
    assert obj["parts"] == w.corpus.read([a])[0]["body"]["parts"]
    assert not w.corpus.stands(a)["stands"]
    # New owner-qualified prior synthesis carries all inherited original inputs.
    nextp = prepare(w, priors=[desc["ref"]])
    refs = {a["ref"] for a in nextp["artifacts"]}
    assert p["manifest"]["ref"] in refs and w.batch["ref"] in refs and desc["ref"] in refs
    graph = E.Closure(w.state, MAGNET)
    graph.add(nextp["manifest"]["ref"])
    assert len(graph.objects[nextp["manifest"]["ref"]]["originals"]) == 1
    assert not w.corpus.operational(act="material-recorded", about=a)


def test_wrong_brain_and_late_answer_refuse(inquiry, monkeypatch):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    old, first = live(w, req, agent)
    a = answer(w, req, agent, old, first)
    live(w, req, agent)
    with pytest.raises(Refused, match="late"):
        cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=old, answer=a)
    with pytest.raises(Refused, match="Brain"):
        cmd(w, "reconcile", p["perspective"], brain="wrong@instance", intent=p["intent"], purpose="display")


def test_unqualified_reply_stays_ordinary_and_receipt_is_durable(inquiry):
    w = inquiry
    p = prepare(w)
    extra = arbitrary(w)
    req, _, agent, _ = bind(w, p, more=" " + extra)
    instance, run = live(w, req, agent)
    a = answer(w, req, agent, instance, run)
    result = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=instance, answer=a)
    assert result["refused"] and result["answer"] is None
    assert w.corpus.read([a])[0]["body"]["parts"][0]["text"] == "A provisional answer."
    assert W.intent_read(w.state, MAGNET, p["perspective"], p["intent"])["answers"] == []
    assert result["receipt"]["receipt"]["ref"]


@pytest.mark.parametrize("headers,owner,status", [([], False, 401),
    ([["X-Mentis-Worker", "forged"]], True, 403),
    ([["X-Mentis-Brain", "wrong@instance"]], True, 409)])
def test_existing_owner_worker_brain_doors(inquiry, headers, owner, status):
    w = inquiry
    # Avoid duplicate Brain headers: the wrong Brain is the actual sent value.
    chosen = [*JSON_HEADERS, *headers]
    if not any(k == "X-Mentis-Brain" for k, v in headers):
        chosen.append(["X-Mentis-Brain", brain_key(w.corpus)])
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives", chosen,
        P.encoded({"brain": brain_key(w.corpus), "op": "door", "name": "No", "question": "No"}), owner=owner)
    assert got["status"] == status, got


def test_http_requires_brain_and_uses_recorded_owner(inquiry):
    w = inquiry
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives", JSON_HEADERS,
        P.encoded({"brain": brain_key(w.corpus), "op": "no-header", "name": "No", "question": "No"}))
    assert got["status"] == 409
    got = owner_http(w, "", {"name": "HTTP inquiry", "question": "Actual text"})
    assert got["status"] == 200, got
    result = json.loads(got["body"])
    assert w.corpus.read([result["event"]["post"]])[0]["attributed_to"] == w.by
    get = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives/{result['perspective']}/history?limit=1",
               JSON_HEADERS, b"", method="GET")
    assert get["status"] == 200 and json.loads(get["body"])["next"]


def test_collection_history_route_patch_is_delegated_without_c_owned_edits(inquiry, monkeypatch):
    w = inquiry
    import mentis.magnet.collection as collection
    seen = []
    monkeypatch.setattr(collection, "read", lambda st, mid, **kw: seen.append((mid, kw)) or {"ok": 1})
    monkeypatch.setattr(collection, "history", lambda st, mid, **kw: seen.append((mid, kw)) or {"ok": 1}, raising=False)
    for suffix in ("collection?batch=adm-history123&digest=abc", "collection/history?limit=2&cursor=stable"):
        got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/{suffix}", JSON_HEADERS, b"", method="GET")
        assert got["status"] == 200
    assert seen == [(MAGNET, {"batch": "adm-history123", "digest": "abc"}),
                    (MAGNET, {"limit": "2", "cursor": "stable"})]


def test_actual_fake_execution_dispatch_records_delivery_and_reconciles(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    from mentis.web import dispatch as D
    result = D.dispatch(w.state, **w.sent[-1])
    assert result["ok"], result
    check = qualify(w, p)
    assert check["status"] == "qualified", check
    assert check["source"] in ("live-grant", "recorded-dispatch")
    assert w.corpus.deliveries(participant=agent)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"],
                 execution=result["instance"], answer=result["reply"])
    assert frozen["answer"] and frozen["receipt"]["status"] == "qualified"


def test_existing_worker_read_artifact_reconstructs_attached_exact_history(inquiry):
    w = inquiry
    c = create(w, words="First exact question α")
    cmd(w, "question", c["perspective"], text="Second exact wording β")
    current = P.state(w.state, MAGNET, c["perspective"])
    p = cmd(w, "prepare", c["perspective"], question=current["question"]["ref"],
            batches=[w.batch["ref"]], selections=[], continuation=True)
    req, _, agent, _ = bind(w, p)
    from tests.test_magnet_mini_request import worker_read
    world = {"state": w.state, "cv": w.cv, "base": f"http://127.0.0.1:{w.alone}"}
    status, got = worker_read(world, req, P.home(w.state, MAGNET), agent, p["records"]["ref"])
    assert status == 200, got
    records = json.loads(base64.b64decode(got["bytes_b64"]))
    assert records["perspective"] == c["perspective"]
    questions = [e["data"]["text"] for e in records["events"] if e["event"] == "question"]
    assert questions == ["First exact question α", "Second exact wording β"]
    for dep in records["dependencies"]:
        status, got = worker_read(world, req, P.home(w.state, MAGNET), agent, dep["ref"])
        assert status == 200, got


def test_governing_extra_requires_explicit_declaration_and_new_receipts(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    extra = arbitrary(w)
    governing = w.cv.define_persona("Governing with evidence", "Use the actual held example.")
    w.corpus.write(body={"role": "reference", "label": "fixture example"}, attributed_to=w.by,
                   link={"from": governing, "to": extra, "relation": "draws-on"})
    live(w, req, agent, delivered=[governing])
    first = qualify(w, p)
    assert first["status"] == "unqualified"
    assert any(a["ref"] == extra and a["because"] == "drawn-on-by-governed" for a in first["reachable_not_declared"])
    second = qualify(w, p, declared_context=[extra])
    assert second["status"] == "qualified" and second["receipt"] != first["receipt"]


def test_unknown_resumed_delivery_stays_pending_instead_of_recomposing(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent, delivered=[])
    assert qualify(w, p)["status"] == "pending"
    w.state.agents.authority.revoke(execution)
    assert qualify(w, p)["status"] == "pending"


def test_zero_original_support_is_explicitly_unsupported(inquiry):
    w = inquiry
    raw = artifact_of(w, op="no-original-text")
    w.batch = ask_commit(w, raw)["body"]["artifact"]
    p = prepare(w)
    obj = json.loads(held.read(w.root, p["manifest"]["digest"]))
    assert obj["originals"] == [] and obj["support"] == "unsupported"


@pytest.mark.parametrize("extra_count,ok", [(27, True), (28, False)])
def test_prepared_closure_counts_mandatory_manifest_snapshot_definition(inquiry, extra_count, ok):
    w = inquiry
    extra = [arbitrary(w, f"context {i}".encode()) for i in range(extra_count)]
    if ok:
        p = prepare(w, declared_context=extra)
        assert p["closure"]["count"] == 32
        assert p["closure"]["bytes"] == sum(a["size"] for a in p["artifacts"])
    else:
        with pytest.raises(Refused) as exc:
            prepare(w, declared_context=extra)
        assert exc.value.refusal["code"] == "reference-limit"


def child(w, parent, parent_agent, parts, *, returns=True):
    recipient = w.cv.create_participant("@NativeChild" + uuid.uuid4().hex[:5])
    cid = w.cv._act(parent)["conversation"]
    turn = w.cv.say(cid, parent_agent, [{"type": "text", "text": "Continue from the immutable Perspective package"},
                                      *parts], written_by="codex/native-parent")
    exp = w.cv.expect(turn, of=recipient, kind="result", by=parent_agent, caused_by=parent,
                      detail={"reach": "work", "returns_to": parent_agent if returns else None})
    w.cv.record_act(actor=parent_agent, act="work-delegated", turn=turn, conversation=cid,
                    caused_by=parent, about=[exp], detail={"reach": "work", "return_expected": returns})
    return exp, recipient


@pytest.mark.parametrize("attach", [True, False])
def test_native_descendant_reconciliation_requires_real_package_parts(inquiry, attach):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    kid, recipient = child(w, req, agent, p["parts"] if attach else [])
    execution, run = live(w, kid, recipient)
    check = qualify(w, p, execution=execution)
    assert check["request"] == kid
    if attach:
        assert check["status"] == "qualified", check
        a = answer(w, kid, recipient, execution, run)
        out = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=execution, answer=a)
        assert out["answer"]
        obj = json.loads(held.read(w.root, out["answer"]["digest"]))
        assert obj["request"] == kid and obj["bound_request"] == req
    else:
        assert check["status"] == "unqualified"
        assert any(e["code"] == "continuation-parts-missing" for e in check["errors"])


def test_explicit_reference_and_waited_child_returns_remain_undeclared_extras(inquiry):
    w = inquiry
    p = prepare(w)
    extra = arbitrary(w, b"referenced artifact")
    cv = P.home(w.state, MAGNET)
    referenced = w.cv.say(cv, w.by, [{"type": "file", "ref": extra, "media_type": "text/plain"}])
    req, _, agent, _ = bind(w, p, extra_parts=[{"type": "turn", "ref": referenced}])
    execution, run = live(w, req, agent)
    check = qualify(w, p)
    assert any(e["ref"] == extra and e["because"] == "referenced" for e in check["reachable_not_declared"])
    kid, recipient = child(w, req, agent, p["parts"])
    kid_execution, kid_run = live(w, kid, recipient)
    returned = artifacts.hold(w.corpus, w.cv, b"waited child return", act=artifacts.RETURNED,
        actor=recipient, source="child", door="worker-return", execution=kid_execution,
        conversation=cv, caused_by=kid)["admission"]
    answer(w, kid, recipient, kid_execution, kid_run)
    after = qualify(w, p)
    assert any(e["ref"] == returned and e["because"] == "returned-by-child"
               for e in after["reachable_not_declared"]), after


def test_execution_authored_brief_does_not_confer_owner_token_reach(inquiry):
    w = inquiry
    p = prepare(w)
    extra = arbitrary(w)
    req, _, agent, _ = bind(w, p)
    kid, recipient = child(w, req, agent, p["parts"] + [{"type": "text", "text": f"Execution prose {extra}"}])
    instance, run = live(w, kid, recipient)
    check = qualify(w, p, execution=instance)
    assert extra not in {a["ref"] for a in check["available"]}
    assert check["status"] == "qualified"


def test_frozen_answer_output_attachment_becomes_an_input_on_reuse(inquiry):
    w = inquiry
    p = prepare(w)
    req, post, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    result = artifacts.hold(w.corpus, w.cv, b"produced evidence", act=artifacts.RETURNED,
        actor=agent, source="run", door="worker-return", execution=execution,
        conversation=P.home(w.state, MAGNET), caused_by=req)["admission"]
    a = w.cv.say(P.home(w.state, MAGNET), agent, [text("Provisional answer"),
        {"type": "file", "ref": result, "media_type": "text/plain"}], replies_to=post)
    w.cv.record_act(actor=agent, act="turn-said", conversation=P.home(w.state, MAGNET), turn=a,
                    execution=execution, caused_by=req)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=execution, answer=a)
    assert frozen["receipt"]["status"] == "qualified"
    p2 = prepare(w, priors=[frozen["answer"]["ref"]])
    assert result in {a["ref"] for a in p2["artifacts"]}


def test_reuse_counts_context_declared_after_answer_freeze(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    a = answer(w, req, agent, execution, run)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=execution, answer=a)
    kid, recipient = child(w, req, agent, p["parts"])
    kid_execution, kid_run = live(w, kid, recipient)
    returned = artifacts.hold(w.corpus, w.cv, b"late waited input", act=artifacts.RETURNED,
        actor=recipient, source="child", door="worker-return", execution=kid_execution,
        conversation=P.home(w.state, MAGNET), caused_by=kid)["admission"]
    answer(w, kid, recipient, kid_execution, kid_run)
    assert qualify(w, p)["status"] == "unqualified"
    assert qualify(w, p, declared_context=[returned])["status"] == "qualified"
    p2 = prepare(w, priors=[frozen["answer"]["ref"]])
    assert returned in {a["ref"] for a in p2["artifacts"]}
    manifest = json.loads(held.read(w.root, p2["manifest"]["digest"]))
    receipt = manifest["reuse_receipts"][0]["receipt"]["ref"]
    assert receipt in {a["ref"] for a in p2["artifacts"]}


def test_owner_correction_blocks_grounded_operations_without_audience_waiver(inquiry, monkeypatch):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    a = answer(w, req, agent, execution, run)
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    before = w.corpus.advance()
    assert P.listing(w.state, MAGNET)["grounded_answers"] is False
    for verb, body in [("prepare", {"question": p["question"]["ref"], "batches": [w.batch["ref"]], "selections": []}),
                       ("finalize", {"intent": p["intent"], "execution": execution, "answer": a})]:
        got = owner_http(w, f"/{p['perspective']}/{verb}", body)
        assert got["status"] == 422
        assert json.loads(got["body"])["code"] == "grounded-answers-blocked"
    assert w.corpus.advance() == before
    assert w.corpus.read([a])  # ordinary reply is preserved
    cmd(w, "question", p["perspective"], text="Lifecycle still records exact questions")
