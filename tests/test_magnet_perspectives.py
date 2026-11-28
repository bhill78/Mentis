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
    # Construct the historic request directly in this disposable fixture. The
    # new managed request door intentionally refuses this retired generated-work
    # adapter, even while the fixture enables the old Perspective helpers.
    status, out, _ = commands.write_post(w.state,
        {**{k: v for k, v in body.items() if k != "from"}, "conversation": P.home(w.state, MAGNET)},
        written_by=lambda: "unattributed-local-request", _request=True)
    assert status == 200, out
    return out["expectations"][0], out["post"], agent, body


def managed_request(w, prepared, *, more="", extra_parts=(), reach="work"):
    """The same Perspective request THROUGH THE MANAGED DOOR, so it carries a
    verified managed context and can actually be dispatched.

    The one difference from `request` above is what the agent is told: no
    `work` override on the dispatch spec. That override is the retired
    generated-work adapter, which the door refuses outright
    (`invalid-managed-intent`), and under this boundary the agent is handed the
    message itself rather than text composed for it.
    """
    agent = w.cv.create_participant("@Perspective" + uuid.uuid4().hex[:6])
    words = prepared["text"] + more
    body = {"from": {"magnet": MAGNET}, "author": w.by,
        "text": words, "parts": [{"type": "text", "text": words}, *prepared["parts"], *extra_parts],
        "op": prepared["request_op"], "action": "ask-participant", "addressed_to": [agent],
        "topics": [prepared["perspective"]],
        "dispatch": [{"participant": agent, "runtime": "codex", "reach": reach}]}
    status, out, _ = commands.agent_request(
        w.state, body, written_by=lambda: "unattributed-local-request",
        brain=brain_key(w.corpus))
    assert status == 200, out
    return out["expectations"][0], out["post"], agent, body


def bind(w, prepared, **kwargs):
    req, post, agent, body = request(w, prepared, **kwargs)
    cmd(w, "bind", prepared["perspective"], intent=prepared["intent"], request=req)
    return req, post, agent, body


def managed_bind(w, prepared, **kwargs):
    req, post, agent, body = managed_request(w, prepared, **kwargs)
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


def answer(w, req, agent, execution, run, words="A provisional answer.", said=None):
    """A reply by the producing run, with the `turn-said` act that proves it.

    `said` is what the reply boundary records on that act about which
    characters of the reply the run itself wrote (`said_span`, `appended`);
    `None` is a reply recorded before the boundary existed."""
    exp = w.cv._act(req)
    post = w.cv.say(exp["conversation"], agent, [text(words)], replies_to=exp["turn"])
    w.cv.record_act(actor=agent, act="turn-said", conversation=exp["conversation"], turn=post,
                    execution=execution, caused_by=req, detail=said)
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


# ---------------------------------------------------------------------------
# THE BOOKKEEPING A REFRESH LEAVES IN THE OWNER'S OWN CONVERSATION
# (owner ent-de11a0235181). A Perspective is reconciled afresh every time the
# panel draws it, and each one appended a held receipt and a RECORD_ONLY post.
# Measured on TEST's `mag-265878e92e5c987c`: 74 recorded receipts holding 13
# distinct outcomes, 61 of its 130 Conversation units saying nothing the rest
# do not. These pin the source-end rule -- an outcome already recorded is that
# reconciliation's answer -- and that a Magnet recorded the old way still reads.


def _receipts(w, p):
    return W._receipt_rows(w.state, MAGNET, p["perspective"], p["intent"])


def _events(w, p, verb=None):
    rows = P.history(w.state, MAGNET, p["perspective"], limit=100)["events"]
    return [r for r in rows if verb is None or r["event"] == verb]


def test_an_identical_reconciliation_records_no_second_receipt_or_post(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    live(w, req, agent)
    first = qualify(w, p)
    assert first["status"] == "qualified"
    held_before, posts_before = len(_receipts(w, p)), {r["post"] for r in _events(w, p)}
    for _ in range(8):
        again = qualify(w, p)
        # The reconciliation is still done in full: the same facts, the same
        # answer, and the receipt it is already recorded under.
        assert again["status"] == "qualified"
        assert again["receipt"] == first["receipt"]
        assert again["available"] == first["available"]
    assert len(_receipts(w, p)) == held_before
    assert {r["post"] for r in _events(w, p)} == posts_before
    # A CHANGED OUTCOME IS STILL RECORDED, which is the whole point of the
    # record: a purge the owner can see makes a new receipt and a new post.
    artifacts.purge(w.corpus, w.cv, w.batch["ref"], by=w.by, because="fixture purge")
    changed = qualify(w, p)
    assert changed["status"] == "unqualified" and changed["receipt"] != first["receipt"]
    assert len(_receipts(w, p)) == held_before + 1
    assert len({r["post"] for r in _events(w, p)}) == len(posts_before) + 1


def test_a_perspective_recorded_under_the_old_shape_still_reads(inquiry):
    """Old history is read, never re-recorded (AGENTS.md: append-only)."""
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    first = qualify(w, p)
    # The receipt's own recorded fields: `receipt` is the held artifact and
    # `brain` is what the owner door adds to every reply, neither is data.
    data = {k: v for k, v in first.items() if k not in ("receipt", "brain")}
    # Recorded exactly as the old shape recorded it: one held receipt and one
    # post per reconciliation, each identical to the one before.
    olds = []
    for _ in range(5):
        snap = P.hold(w.state, MAGNET, W._package(w.state, MAGNET, "receipt",
            perspective=p["perspective"], **data), w.by, name="receipt")
        P.event(w.state, MAGNET, p["perspective"], "reconciled", data, w.by,
                snapshot=snap, written_by="fixture-owner")
        olds.append(snap)
    # Every stage lookup still finds its stage, by the same route as before.
    assert P.state(w.state, MAGNET, p["perspective"], detail=True)["current_question"]["text"]
    assert W.binding(w.state, MAGNET, p["perspective"], p["intent"])["request"] == req
    read = W.intent_read(w.state, MAGNET, p["perspective"], p["intent"])
    assert read["prepared"]["manifest"] == p["manifest"]
    assert read["binding"]["request"] == req
    rows = _events(w, p)
    assert len(_events(w, p, "reconciled")) == 6
    assert len({r["post"] for r in rows}) == len(rows)
    # And the new rule READS that old history: the newest identical receipt is
    # the answer, and no seventh is appended to it.
    again = qualify(w, p)
    assert again["receipt"] == olds[-1] and again["status"] == "qualified"
    assert len(_events(w, p, "reconciled")) == 6
    # A frozen answer still carries a receipt and still verifies.
    a = answer(w, req, agent, execution, run)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=execution, answer=a)
    assert frozen["receipt"]["status"] == "qualified"
    obj = E.native(w.state, MAGNET, frozen["answer"]["ref"],
                   held.read(w.root, frozen["answer"]["digest"]), "answer")
    assert obj["receipt"]["ref"] == frozen["receipt"]["receipt"]["ref"]


def test_a_purged_receipt_is_not_reused_and_does_not_block_a_valid_prior(inquiry):
    """A receipt is an INPUT, not only a report, and the owner may purge one.

    An identical outcome says nothing about the custody of the artifact the
    outcome was recorded under: `_prepare` adds the receipt it is handed to the
    next Perspective's input closure, so handing back a purged Admission would
    refuse a reuse whose facts are perfectly qualified (independent review of
    31c3c39d, F1). The purge stays the record's last word on that Admission;
    the freshly computed outcome is recorded under a usable receipt instead.
    """
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    a = answer(w, req, agent, execution, run)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"],
                 execution=execution, answer=a)
    reuse = dict(intent=p["intent"], execution=execution, purpose="reuse")
    first = cmd(w, "reconcile", p["perspective"], **reuse)
    assert first["status"] == "qualified"
    assert cmd(w, "reconcile", p["perspective"], **reuse)["receipt"] == first["receipt"]
    held_before = len(_receipts(w, p))
    artifacts.purge(w.corpus, w.cv, first["receipt"]["ref"], by=w.by, because="fixture purge")
    assert artifacts.describe(w.corpus, first["receipt"]["ref"])["state"] == "purged"
    # Reconciled afresh: the same qualified facts, under a receipt that is
    # actually readable, recorded because the purged one cannot serve.
    again = cmd(w, "reconcile", p["perspective"], **reuse)
    assert again["status"] == "qualified"
    assert again["receipt"]["ref"] != first["receipt"]["ref"]
    assert len(_receipts(w, p)) == held_before + 1
    E.Closure(w.state, MAGNET).add(again["receipt"]["ref"], again["receipt"])
    # Which is what the purged receipt would otherwise have refused: the valid
    # prior answer is still reusable as an immutable input.
    nextp = prepare(w, priors=[frozen["answer"]["ref"]])
    assert frozen["answer"]["ref"] in {d["ref"] for d in nextp["artifacts"]}


def test_a_receipt_whose_bytes_are_gone_is_not_reused(inquiry):
    """The missing-bytes variant of the same rule, not only the purged one.

    `_still_an_input` is the consumer's own door (`E.Closure.add`), so a
    receipt the record calls held but whose bytes are not there is not handed
    on either; the outcome is recorded again under one that can be read.
    """
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    live(w, req, agent)
    first = qualify(w, p)
    assert first["status"] == "qualified"
    assert qualify(w, p)["receipt"] == first["receipt"]
    path = held.path(w.root, first["receipt"]["digest"])
    raw = path.read_bytes()
    path.unlink()
    assert artifacts.describe(w.corpus, first["receipt"]["ref"],
                              verify=False)["state"] == "held-but-missing"
    try:
        again = qualify(w, p)
    finally:
        if not path.exists():
            path.write_bytes(raw)
    assert again["status"] == "qualified"
    assert again["receipt"]["ref"] != first["receipt"]["ref"]
    assert len(_events(w, p, "reconciled")) == 2
    E.Closure(w.state, MAGNET).add(again["receipt"]["ref"], again["receipt"])


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


# ---------------------------------------------------------------------------
# WHICH CHARACTERS OF THE FROZEN ANSWER THE RUN WROTE (independent review F1,
# `ent-c0eebf657ffb`).
#
# The reply boundary measures it where the reply is written and records it on
# that reply's `turn-said` act (`tests/test_dispatch_answer_boundary.py`).
# `finalize` froze the reply's parts WITHOUT it, so the surface drawing the
# answer still had to recognise Mentis's claim trailer by its wording. These
# check that the boundary reaches the frozen package and the `answered` event
# the history returns, that slicing by it gives the run's own words, and that
# nothing is invented where the record holds none.

SAID = "The collection's strongest theme is how observations become useful."
TRAILER = "Claim by @Agent: met — Answered it. (the agent's claim; what Mentis recorded is shown with the work)"
REPLY = f"{SAID}\n\n{TRAILER}"
BOUNDARY = {"said_span": {"part": 0, "start": 0, "end": len(SAID)},
            "appended": [{"part": 0, "start": len(SAID), "end": len(REPLY),
                          "what": "outcome-claim"}]}


def _frozen(w, desc):
    return E.native(w.state, MAGNET, desc["ref"], held.read(w.root, desc["digest"]), "answer")


def test_finalize_carries_the_reply_boundary_into_the_frozen_answer(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, run = live(w, req, agent)
    a = answer(w, req, agent, instance, run, words=REPLY, said=BOUNDARY)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=instance, answer=a)
    obj = _frozen(w, frozen["answer"])

    # The parts are still frozen verbatim: nothing is edited out of the record.
    assert obj["parts"] == w.corpus.read([a])[0]["body"]["parts"]
    # And the boundary is frozen WITH them, so a reader that verifies the
    # package by size and digest has the offsets too.
    assert obj["said_span"] == BOUNDARY["said_span"]
    assert obj["appended"] == BOUNDARY["appended"]
    # Read as a reader reads it: the run's own words, and Mentis's apart.
    whole = obj["parts"][0]["text"]
    span, added = obj["said_span"], obj["appended"][0]
    assert whole[span["start"]:span["end"]] == SAID
    assert whole[added["start"]:added["end"]].strip() == TRAILER
    assert "Claim by" not in whole[span["start"]:span["end"]]

    # The `answered` event the Perspective's history returns says it too, so a
    # reader that has not fetched the package knows the boundary is there.
    assert frozen["event"]["data"]["said_span"] == BOUNDARY["said_span"]
    said = next(e for e in reversed(P.history(w.state, MAGNET, p["perspective"],
                                              limit=100)["events"])
                if e["event"] == "answered")
    assert said["data"]["said_span"] == BOUNDARY["said_span"]
    assert said["data"]["appended"] == BOUNDARY["appended"]


def test_an_answer_recorded_without_the_boundary_claims_none(inquiry):
    # Every answer frozen before the boundary existed. Nothing is inferred
    # from the words, so a reader still has only what the record says.
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, run = live(w, req, agent)
    a = answer(w, req, agent, instance, run, words=REPLY)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=instance, answer=a)
    obj = _frozen(w, frozen["answer"])
    assert obj["parts"][0]["text"] == REPLY
    assert "said_span" not in obj and "appended" not in obj
    assert "said_span" not in frozen["event"]["data"]
    assert "appended" not in frozen["event"]["data"]


@pytest.mark.parametrize("said,why", [
    ({"said_span": {"part": 0, "start": 0, "end": len(REPLY) + 1}}, "past the end"),
    ({"said_span": {"part": 1, "start": 0, "end": 1}}, "a part that is not there"),
    ({"said_span": {"part": 0, "start": 5, "end": 2}}, "inside out"),
    ({"said_span": {"part": 0, "start": "0", "end": 3}}, "not characters at all"),
    ({"appended": [{"part": 0, "start": 0, "end": len(REPLY) + 9}]}, "an appended span past the end"),
    ({"appended": {"part": 0, "start": 0, "end": 3}}, "appended is not a list"),
])
def test_a_boundary_that_does_not_fit_the_frozen_parts_is_dropped(inquiry, said, why):
    # The package verifies by size and digest, which says the bytes are the
    # frozen ones and nothing about whether an offset addresses them. An
    # offset that does not fit is dropped, never adjusted to fit.
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    instance, run = live(w, req, agent)
    a = answer(w, req, agent, instance, run, words=REPLY, said=said)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"], execution=instance, answer=a)
    obj = _frozen(w, frozen["answer"])
    assert "said_span" not in obj and "appended" not in obj, why


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


def test_perspective_router_owns_only_perspective_detail(inquiry):
    w = inquiry
    c = create(w, words="Exact saved question \u03b1 \U0001f642")
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives/{c['perspective']}",
               JSON_HEADERS, b"", method="GET")
    assert got["status"] == 200, got
    assert json.loads(got["body"])["current_question"] == {
        "text": "Exact saved question \u03b1 \U0001f642", "revision": c["question"]["ref"]}


def test_actual_fake_execution_dispatch_records_delivery_and_reconciles(inquiry):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = managed_bind(w, p)
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
                       ("finalize", {"intent": p["intent"], "execution": execution, "answer": a}),
                       ("reconcile", {"intent": p["intent"], "purpose": "display"})]:
        got = owner_http(w, f"/{p['perspective']}/{verb}", body)
        assert got["status"] == 422
        assert json.loads(got["body"])["code"] == "grounded-answers-blocked"
    assert w.corpus.advance() == before
    assert w.corpus.read([a])  # ordinary reply is preserved
    cmd(w, "question", p["perspective"], text="Lifecycle still records exact questions")


def test_current_question_detail_is_latest_beyond_history_page_and_survives_reopen(inquiry):
    w = inquiry
    c = create(w)
    topic = c["perspective"]
    definition = w.definition_path.read_bytes()
    for i in range(103):
        cmd(w, "challenge", topic, text=f"History row {i}")
    first = P.history(w.state, MAGNET, topic, limit=100)
    exact = "  Revised hypothesis \u00e9\u03b1\U0001f642\nsecond line  "
    revision = cmd(w, "question", topic, text=exact)
    assert first["next"]
    assert P.route_read(w.state, MAGNET, [topic], lambda key, default=None: default)["current_question"] == {
        "text": exact, "revision": revision["question"]["ref"]}
    from mentis.web import _State
    reopened = _State(str(w.root))
    try:
        assert P.state(reopened, MAGNET, topic, detail=True)["current_question"]["text"] == exact
    finally:
        reopened.agents.close()
        reopened.corpus._store.close()
    assert w.definition_path.read_bytes() == definition and not w.sent
    original = json.loads(held.read(w.root, c["question"]["digest"]))
    assert original["text"] == "What did the original say?"


def test_lifecycle_retry_keys_preserve_original_create_edit_and_select(inquiry):
    w = inquiry
    body = {"brain": brain_key(w.corpus), "op": "frozen-create", "name": "Original", "question": "First"}
    created = P.command(w.state, MAGNET, None, "create", body)
    topic = created["perspective"]
    assert P.command(w.state, MAGNET, None, "create", body)["replayed"]
    cmd(w, "selected", perspective=topic)
    edit = {"brain": brain_key(w.corpus), "op": "frozen-edit", "text": "Saved \u03b1"}
    revision = P.command(w.state, MAGNET, topic, "question", edit)
    other = create(w, name="Other")
    cmd(w, "selected", perspective=other["perspective"])
    before = w.corpus.advance()
    assert P.command(w.state, MAGNET, topic, "question", edit)["replayed"]
    assert w.corpus.advance() == before
    assert P.state(w.state, MAGNET, topic, detail=True)["current_question"]["revision"] == revision["question"]["ref"]
    assert P.selected(w.state, MAGNET) == other["perspective"]
    with pytest.raises(Refused):
        P.command(w.state, MAGNET, other["perspective"], "question", edit)


@pytest.mark.parametrize("purpose", ["display", "resume", "reuse", "attach"])
def test_disabled_gate_prevents_qualified_receipt_replay_and_direct_helpers(inquiry, monkeypatch, purpose):
    w = inquiry
    p = prepare(w)
    req, _, agent, _ = bind(w, p)
    execution, run = live(w, req, agent)
    a = answer(w, req, agent, execution, run)
    body = {"brain": brain_key(w.corpus), "op": "preserved-qualified", "intent": p["intent"], "purpose": purpose}
    receipt = P.command(w.state, MAGNET, p["perspective"], "reconcile", body)
    assert receipt["status"] == "qualified"
    raw = held.read(w.root, receipt["receipt"]["digest"])
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    before = w.corpus.advance()
    with pytest.raises(Refused, match="Grounded Perspective answers are unavailable"):
        P.command(w.state, MAGNET, p["perspective"], "reconcile", body)
    for verb, data in [("prepare", {}), ("reconcile", body), ("finalize", {"answer": a})]:
        with pytest.raises(Refused, match="Grounded Perspective answers are unavailable"):
            getattr(W, verb)(w.state, MAGNET, p["perspective"], data, w.by, None)
    got = owner_http(w, f"/{p['perspective']}/reconcile", body)
    assert got["status"] == 422 and json.loads(got["body"])["code"] == "grounded-answers-blocked"
    assert w.corpus.advance() == before
    assert held.read(w.root, receipt["receipt"]["digest"]) == raw
    assert P.history(w.state, MAGNET, p["perspective"])["events"]
    assert W.intent_read(w.state, MAGNET, p["perspective"], p["intent"])["grounded_answers"] is False


@pytest.mark.parametrize("field", ["grounded_answers", "enabled", "only_human", "consent", "settings"])
def test_no_http_field_enables_grounded_answers(inquiry, monkeypatch, field):
    w = inquiry
    c = create(w)
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    before = w.corpus.advance()
    got = owner_http(w, f"/{c['perspective']}/reconcile", {"intent": "old-intent", "purpose": "display", field: True})
    assert got["status"] == 422 and json.loads(got["body"])["code"] == "invalid-fields"
    assert w.corpus.advance() == before


def test_current_question_http_read_refuses_worker_credentials(inquiry):
    w = inquiry
    c = create(w)
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives/{c['perspective']}",
               [*JSON_HEADERS, ["X-Mentis-Worker", "forged"]], b"", method="GET")
    assert got["status"] == 403


def test_question_and_selection_refuse_foreign_topic_without_writes(inquiry):
    w = inquiry
    foreign = w.cv.open_conversation("Foreign", attributed_to=w.by)
    topic = w.cv.open_topic(foreign, "Not this Magnet", attributed_to=w.by)
    before = w.corpus.advance()
    for verb, target, body in [("question", topic, {"text": "Forbidden"}),
                               ("selected", None, {"perspective": topic})]:
        with pytest.raises(Refused, match="not in this Magnet"):
            cmd(w, verb, target, **body)
    assert w.corpus.advance() == before


def test_question_write_refuses_trashed_conversation_but_history_remains_readable(inquiry):
    w = inquiry
    c = create(w)
    w.cv.change_conversation_state(P.home(w.state, MAGNET), "trash", by=w.by)
    before = w.corpus.advance()
    got = owner_http(w, f"/{c['perspective']}/question", {"text": "Forbidden after trash"})
    assert got["status"] == 409
    assert json.loads(got["body"])["code"] == "conversation-in-trash"
    assert w.corpus.advance() == before
    assert P.state(w.state, MAGNET, c["perspective"], detail=True)["current_question"]["text"] == "What did the original say?"
    assert P.history(w.state, MAGNET, c["perspective"])["events"]



def test_question_first_client_name_uses_existing_create_contract(inquiry):
    w = inquiry
    question = "What should we learn from this deliberately long inquiry question?"
    derived = question[:49] + "?"
    created = cmd(w, name=derived, question=question)
    current = P.state(w.state, MAGNET, created["perspective"], detail=True)
    assert current["name"] == derived
    assert current["current_question"]["text"] == question
    before = w.corpus.advance()
    with pytest.raises(Refused, match="name must be text"):
        cmd(w, question=question)
    assert w.corpus.advance() == before


def test_rename_is_immutable_durable_and_keeps_identity_selection_and_question(inquiry):
    w = inquiry
    created = create(w, name="Created name")
    topic = created["perspective"]
    cmd(w, "selected", perspective=topic)
    config = w.definition_path.read_bytes()
    original_history = P.history(w.state, MAGNET, topic)["events"]
    original_bytes = {e["snapshot"]["digest"]: held.read(w.root, e["snapshot"]["digest"])
                      for e in original_history}
    labels = w.cv.topics(P.home(w.state, MAGNET))
    assert P.state(w.state, MAGNET, topic)["name"] == "Created name"
    exact = "  Renamed inquiry ???\nsecond line  "
    got = owner_http(w, f"/{topic}/rename", {"name": exact})
    assert got["status"] == 200, got
    renamed = json.loads(got["body"])
    row = renamed["event"]
    assert renamed["perspective"] == topic and row["event"] == "rename"
    assert row["data"] == {"name": exact}
    snapshot = json.loads(held.read(w.root, row["snapshot"]["digest"]))
    assert snapshot == {"format": P.FORMAT, "version": 1, "kind": "event",
        "brain": brain_key(w.corpus), "magnet": MAGNET, "perspective": topic,
        "event": "rename", "data": {"name": exact}}
    assert w.corpus.read([row["post"]])[0]["attributed_to"] == w.by
    assert w.cv.topics(P.home(w.state, MAGNET)) == labels
    # Even a separate edit to the mutable Topic label cannot change Perspective identity/name.
    w.cv.edit_topic(topic, by=w.by, name="Unrelated Topic label")
    cmd(w, "rename", topic, name="Newest name")
    current = P.state(w.state, MAGNET, topic, detail=True)
    assert current["name"] == "Newest name"
    assert current["current_question"] == {"text": "What did the original say?",
        "revision": created["question"]["ref"]}
    assert P.selected(w.state, MAGNET) == topic
    assert P.listing(w.state, MAGNET)["perspectives"][0]["name"] == "Newest name"
    assert P.history(w.state, MAGNET, topic)["events"][:len(original_history)] == original_history
    for digest, raw in original_bytes.items():
        assert held.read(w.root, digest) == raw
    assert P.history(w.state, MAGNET, topic)["events"][-2] == row
    from mentis.web import _State
    reopened = _State(str(w.root))
    try:
        assert P.state(reopened, MAGNET, topic)["name"] == "Newest name"
        assert P.selected(reopened, MAGNET) == topic
    finally:
        reopened.agents.close()
        reopened.corpus._store.close()
    assert w.definition_path.read_bytes() == config and not w.sent


def test_rename_replay_returns_original_without_reverting_newer_name(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    body = {"op": "stable-rename", "name": "First rename"}
    first = owner_http(w, f"/{topic}/rename", body)
    assert first["status"] == 200, first
    first = json.loads(first["body"])
    cmd(w, "rename", topic, name="Later rename")
    before = w.corpus.advance()
    replay = owner_http(w, f"/{topic}/rename", body)
    assert replay["status"] == 200, replay
    assert json.loads(replay["body"]) == {**first, "replayed": True}
    changed = owner_http(w, f"/{topic}/rename", {**body, "name": "Changed arguments"})
    assert changed["status"] == 422 and "different request" in json.loads(changed["body"])["error"]
    assert P.state(w.state, MAGNET, topic)["name"] == "Later rename"
    assert w.corpus.advance() == before


def test_rename_keeps_list_and_history_cursors_stable(inquiry):
    w = inquiry
    one, two = create(w), create(w, name="Second")
    topic = one["perspective"]
    listing = P.listing(w.state, MAGNET, limit=1)
    history = P.history(w.state, MAGNET, topic, limit=1)
    cmd(w, "rename", topic, name="ZZZ renamed first")
    cmd(w, "rename", two["perspective"], name="AAA renamed second")
    rest = P.listing(w.state, MAGNET, limit=1, cursor=listing["next"])
    assert rest["next"] is None
    assert listing["perspectives"][0]["perspective"] == topic
    assert rest["perspectives"][0]["perspective"] == two["perspective"]
    assert rest["perspectives"][0]["name"] == "AAA renamed second"
    frozen = P.history(w.state, MAGNET, topic, cursor=history["next"])
    assert frozen["through"] == history["through"] and frozen["next"] is None
    assert [e["event"] for e in frozen["events"]] == ["question"]


@pytest.mark.parametrize("same_home", [False, True])
def test_rename_refuses_another_magnets_recorded_perspective(inquiry, same_home):
    w = inquiry
    other_mid = "mag-0123456789abcdef"
    config = json.loads(w.definition_path.read_bytes())
    config["id"] = other_mid
    if not same_home:
        config["conversation"] = w.cv.open_conversation("Other Magnet", attributed_to=w.by)
    w.definition_path.with_name(other_mid + ".json").write_bytes(P.encoded(config))
    other = P.command(w.state, other_mid, None, "create", {"brain": brain_key(w.corpus),
        "op": "foreign-create", "name": "Foreign name", "question": "Foreign question"})
    before = w.corpus.advance()
    got = owner_http(w, f"/{other['perspective']}/rename", {"name": "Forbidden"})
    assert got["status"] == 422 and json.loads(got["body"])["code"] == "wrong-perspective"
    assert P.state(w.state, other_mid, other["perspective"])["name"] == "Foreign name"
    assert w.corpus.advance() == before


@pytest.mark.parametrize("body,code", [({"name": None}, "invalid-text"),
    ({"name": "  "}, "invalid-text"), ({"name": 3}, "invalid-text"),
    ({"name": "x" * (P.TEXT_MAX + 1)}, "invalid-text"),
    ({"name": "Name", "author": "forged"}, "invalid-fields"),
    ({"name": "Name", "brain": "wrong@instance"}, "wrong-brain"),
    ({"name": "Name", "op": ""}, "operation-required")])
def test_rename_validation_refuses_without_writing(inquiry, body, code):
    w = inquiry
    topic = create(w)["perspective"]
    before = w.corpus.advance()
    with pytest.raises(Refused) as exc:
        cmd(w, "rename", topic, **body)
    assert exc.value.refusal["code"] == code
    assert w.corpus.advance() == before


@pytest.mark.parametrize("headers,owner,status", [([], False, 401),
    ([["X-Mentis-Worker", "forged"]], True, 403),
    ([["X-Mentis-Brain", "wrong@instance"]], True, 409)])
def test_rename_uses_existing_owner_worker_brain_doors(inquiry, headers, owner, status):
    w = inquiry
    topic = create(w)["perspective"]
    chosen = [*JSON_HEADERS, *headers]
    if not any(k == "X-Mentis-Brain" for k, v in headers):
        chosen.append(["X-Mentis-Brain", brain_key(w.corpus)])
    before = w.corpus.advance()
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives/{topic}/rename", chosen,
        P.encoded({"brain": brain_key(w.corpus), "op": "rename-door", "name": "Forbidden"}), owner=owner)
    assert got["status"] == status, got
    assert w.corpus.advance() == before


def test_rename_requires_confirmed_brain_and_writable_conversation(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    before = w.corpus.advance()
    got = send(w.alone, f"/fluid/api/magnets/{MAGNET}/perspectives/{topic}/rename", JSON_HEADERS,
        P.encoded({"brain": brain_key(w.corpus), "op": "no-brain-header", "name": "Forbidden"}))
    assert got["status"] == 409 and w.corpus.advance() == before
    w.cv.change_conversation_state(P.home(w.state, MAGNET), "trash", by=w.by)
    before = w.corpus.advance()
    got = owner_http(w, f"/{topic}/rename", {"name": "Forbidden after trash"})
    assert got["status"] == 409 and json.loads(got["body"])["code"] == "conversation-in-trash"
    assert P.state(w.state, MAGNET, topic)["name"] == "Inquiry"
    assert w.corpus.advance() == before


def test_rename_leaves_grounded_gate_before_op_validation_and_keyed_writes(inquiry, monkeypatch):
    w = inquiry
    topic = create(w)["perspective"]
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    cmd(w, "rename", topic, name="Ordinary lifecycle remains usable")
    before = w.corpus.advance()
    monkeypatch.setattr(P.anchors, "keyed", lambda *a, **kw: pytest.fail("grounded gate must precede keyed"))
    for verb in ("prepare", "reconcile", "finalize"):
        with pytest.raises(Refused) as exc:
            P.command(w.state, MAGNET, topic, verb, {"brain": brain_key(w.corpus)})
        assert exc.value.refusal["code"] == "grounded-answers-blocked"
    for read in (P.listing(w.state, MAGNET), P.history(w.state, MAGNET, topic),
                 P.route_read(w.state, MAGNET, [topic], lambda key, default=None: default)):
        assert read["disclosure"] == P.DISCLOSURE
    assert P.listing(w.state, MAGNET)["grounded_answers"] is False
    assert w.corpus.advance() == before


def test_unknown_perspective_write_help_includes_rename(inquiry):
    w = inquiry
    topic = create(w)["perspective"]
    got = owner_http(w, f"/{topic}/not-a-verb", {})
    assert got["status"] == 405
    assert "/perspectives/<topic>/question, /rename" in json.loads(got["body"])["error"]

# ---------------------------------------------------------------------------
# PART F: THE EVOLVING SUMMARY AND AN ANSWERED PERSPECTIVE ARE ONE MECHANISM
# (plan adm-43ecee5872e9 section 3; amendment adm-c38044ee5157 section 3;
# owner correction ent-d85254fe5e1b and #521 section 7).
#
# What these prove: an answer exists, is durable, cites the collected rows it
# was written from, supersedes rather than overwrites, and is grounded in the
# collection STRUCTURALLY -- no body field, authorization or grant can point it
# anywhere else, and `scope.provenance(..., synthesis=True)` is empty and false
# on every one of them.


def standing(w):
    """This Magnet's standing Perspective, created as it is created with one."""
    return cmd(w, "create", None, name=P.STANDING_NAME, question=P.STANDING_QUESTION,
               standing=True)


def recollect(w, op, add=None):
    """A second recorded collection of this Magnet, optionally with a new row."""
    def change(art):
        art["page"]["sources"][0]["results"][0].update(
            value={"parts": [{"type": "text", "text": "Original \u03b1 evidence. A shared observation."}]})
        if add is not None:
            art["page"]["sources"][0]["results"].append(add)
    raw = artifact_of(w, op=op, change=change)
    return ask_commit(w, raw)["body"]["artifact"]


NEW_ROW = {"kind": "post", "id": "ent-00000000000f", "version": "ent-00000000000f",
           "conversation": "ent-2865e11386f6", "author": "ent-b20d8e47f196",
           "at": 1795000000.0, "number": 9, "via": "home", "deleted": False,
           "value": {"parts": [{"type": "text", "text": "A newly arrived record about calibration drift."}]}}


def test_one_standing_perspective_per_magnet_however_often_it_is_created(inquiry):
    w = inquiry
    assert P.standing(w.state, MAGNET) is None
    made = standing(w)
    assert P.standing(w.state, MAGNET) == made["perspective"]
    assert made.get("standing") is True
    # A lost acknowledgement, a second surface, a different operation key: all
    # converge on the first one in the record rather than growing a second
    # evolving summary. Nothing further is written.
    before = len(w.corpus.operational(act=P.ACT, limit=10000))
    again = standing(w)
    assert again["perspective"] == made["perspective"]
    assert again["existing"] is True
    assert len(w.corpus.operational(act=P.ACT, limit=10000)) == before, \
        "an existing standing Perspective records no further Perspective event"
    # And the listing says which one it is, so no client has to search for it.
    assert P.listing(w.state, MAGNET)["standing"] == made["perspective"]
    assert P.route_read(w.state, MAGNET, [made["perspective"]],
                        lambda key, default=None: default)["standing"] == made["perspective"]
    # Creating an ordinary Perspective never makes it the standing one.
    other = create(w)
    assert P.standing(w.state, MAGNET) == made["perspective"] != other["perspective"]


def test_the_evolving_summary_is_an_answer_grounded_in_the_collection_and_nothing_else(inquiry):
    w = inquiry
    topic = standing(w)["perspective"]
    out = cmd(w, "answer", topic)
    # IT IS AN ANSWER: words that say what this Magnet has gathered, written
    # from the rows, with the records it was written from cited.
    assert out["text"].startswith("## Developments\n\n- ")
    assert "[1]" in out["text"]
    assert out["citations"][0]["n"] == 1
    assert out["citations"][0]["item"] in out["lines"][1]["cites"]
    assert out["support"] == "supported"
    assert out["basis"]["batch"] == w.batch["ref"]
    assert out["basis"]["rows"] >= 1
    assert out["method"] == W.METHOD
    assert out["written_by"] == W.WRITTEN_BY_MENTIS
    assert out["standing"] is True
    # EVERY STATEMENT NAMES THE RECORDS IT WAS WRITTEN FROM.
    assert out["lines"] and any(line["cites"] for line in out["lines"])
    rows = {r["id"] for s in json.loads(
        held.path(w.corpus.root, w.batch["digest"]).read_bytes())["page"]["sources"]
        for r in s.get("results", [])}
    for line in out["lines"]:
        assert set(line["cites"]) <= rows, "a statement cites only this collection's own rows"
    # GROUNDED STRUCTURALLY: Part A's own provenance, empty and false.
    assert out["provenance"] == {"grounded_in": "collection", "outside_authorized": [],
                                 "outside_reads": [], "explored_outside": False}
    # The immutable answer package holds the same, and names only this batch
    # and the frozen question as its inputs.
    package = E.native(w.state, MAGNET, out["answer"]["ref"],
                       E.bounded_read(w.state, E.descriptor(w.state, out["answer"]["ref"]),
                                      E.MAX_BYTES), "answer")
    assert package["provenance"] == out["provenance"]
    assert package["citations"] == out["citations"]
    assert package["text"] == out["text"]
    assert package["synthesis"] is True
    assert package["disclosure"] == P.DISCLOSURE
    manifest = E.native(w.state, MAGNET, package["manifest"]["ref"],
                        E.bounded_read(w.state, E.descriptor(w.state, package["manifest"]["ref"]),
                                       E.MAX_BYTES), "manifest")
    assert [b["ref"] for b in manifest["batches"]] == [w.batch["ref"]]
    assert manifest["direct"] == [w.batch["ref"], package["question"]["ref"]]
    assert manifest["priors"] == [] and manifest["declared_context"] == []
    assert manifest["originals"], "the exact captured ranges it was written from"
    for original in manifest["originals"]:
        for citation in original["citations"]:
            assert citation["batch"] == w.batch["ref"]
    # AND NO ARGUMENT CAN POINT IT ANYWHERE ELSE: the operation accepts a
    # question and a reason, and nothing that names a batch, source or grant.
    assert P.FIELDS["answer"] == {"text", "reason"}
    for forged in ({"batches": [w.batch["ref"]]}, {"collection": "col-other"},
                   {"declared_context": []}, {"priors": []}):
        with pytest.raises(Refused) as exc:
            cmd(w, "answer", topic, **forged)
        assert exc.value.refusal["code"] == "invalid-fields"


def test_the_answer_survives_a_reload_and_a_second_collection_supersedes_without_overwriting(inquiry):
    w = inquiry
    topic = standing(w)["perspective"]
    saved_question = P.state(w.state, MAGNET, topic, detail=True)["current_question"]["text"].encode("utf-8")
    first = cmd(w, "answer", topic)
    # SURVIVES A RELOAD: the durable history is where it lives, and the read
    # that serves the client returns it with its provenance and its basis.
    def answers():
        return [e for e in P.history(w.state, MAGNET, topic, limit=100)["events"]
                if e["event"] == "answered"]
    assert [a["data"]["text"] for a in answers()] == [first["text"]]
    assert answers()[0]["data"]["provenance"]["explored_outside"] is False
    # NOTHING NEW IS NOT RE-ANSWERED. Part E's own new-item count decides, read
    # on the server; the refusal records nothing and leaves the answer standing.
    before = w.corpus.advance()
    with pytest.raises(Refused) as exc:
        cmd(w, "answer", topic)
    assert exc.value.refusal["code"] == "nothing-new"
    assert exc.value.refusal["new_count"] == 0
    assert w.corpus.advance() == before
    assert len(answers()) == 1
    # A SECOND COLLECTION WITH A TRUE NEW ROW: a new current answer, and the
    # previous one exactly where it was recorded. Append-only, not overwritten.
    second = recollect(w, "part-f-second", add=NEW_ROW)
    again = cmd(w, "answer", topic)
    kept = answers()
    assert P.state(w.state, MAGNET, topic, detail=True)["current_question"]["text"].encode("utf-8") == saved_question
    assert len(kept) == 2
    assert kept[0]["data"]["text"] == first["text"], "the earlier answer is unchanged"
    assert kept[1]["data"]["text"] == again["text"] != first["text"]
    assert kept[0]["data"]["answer"]["ref"] != kept[1]["data"]["answer"]["ref"]
    assert again["basis"]["batch"] == second["ref"]
    assert again["basis"]["since"] == first["basis"]["batch"]
    assert again["basis"]["new_count"] >= 1
    assert NEW_ROW["id"] in again["basis"]["new"]
    assert again["text"].startswith("## Developments")
    assert "calibration drift" in again["text"], "and says what arrived, in its own words"


def test_a_question_asked_gets_a_persisted_answer_that_cites_the_collected_rows(inquiry):
    w = inquiry
    recollect(w, "part-f-asked", add=NEW_ROW)
    topic = create(w, words="What is recorded here?")["perspective"]
    out = cmd(w, "answer", topic, text="What do the records say about calibration drift?")
    assert "calibration" in out["text"] and "drift" in out["text"]
    assert "A newly arrived record about calibration drift." in out["text"]
    assert out["standing"] is False, "an ordinary question is not the evolving summary"
    assert out["provenance"]["explored_outside"] is False
    cited = {c["item"] for o in out["lines"] for c in [{"item": i} for i in o["cites"]]}
    assert NEW_ROW["id"] in cited
    # The question itself is recorded as an immutable revision, and the answer
    # names that exact revision -- not whatever is saved later.
    assert out["question"]["ref"]
    assert P.state(w.state, MAGNET, topic, detail=True)["current_question"]["text"] == \
        "What do the records say about calibration drift?"
    # ASKING AGAIN SUPERSEDES RATHER THAN OVERWRITES, even over the same rows.
    later = cmd(w, "answer", topic, text="What do the records say about calibration drift?")
    kept = [e for e in P.history(w.state, MAGNET, topic, limit=100)["events"]
            if e["event"] == "answered"]
    assert len(kept) == 2
    assert kept[0]["data"]["answer"]["ref"] != kept[1]["data"]["answer"]["ref"]
    assert kept[1]["data"]["answer"]["ref"] == later["answer"]["ref"]


def test_an_answer_the_collection_cannot_give_says_so_rather_than_answering(inquiry):
    w = inquiry
    topic = create(w, words="Anything")["perspective"]
    out = cmd(w, "answer", topic, text="What about zygomorphic frobnication of widgets?")
    assert "does not establish an answer" in out["text"]
    assert out["citations"] == []
    assert out["support"] == "unsupported", "no row supports it, and it is not labelled as if one did"
    assert out["provenance"]["explored_outside"] is False
    # And a question with nothing to search on is refused in words, not answered.
    empty = cmd(w, "answer", topic, text="the and that this with")
    assert "does not establish an answer" in empty["text"]


def test_answering_needs_a_collection_a_live_perspective_and_the_open_gate(inquiry, monkeypatch):
    w = inquiry
    topic = create(w)["perspective"]
    # A retired Perspective answers nothing until it is resumed.
    cmd(w, "retire", topic, reason="done")
    with pytest.raises(Refused) as exc:
        cmd(w, "answer", topic, text="Anything")
    assert exc.value.refusal["code"] == "retired"
    cmd(w, "resume", topic, reason="again")
    # THE GATE IS A.'S, AND PART F DOES NOT UNDO IT: with it shut, answering is
    # refused with its existing code, before any keyed write.
    monkeypatch.setattr(P, "GROUNDED_ANSWERS_ENABLED", False)
    before = w.corpus.advance()
    monkeypatch.setattr(P.anchors, "keyed", lambda *a, **kw: pytest.fail("the gate must precede keyed"))
    with pytest.raises(Refused) as exc:
        P.command(w.state, MAGNET, topic, "answer", {"brain": brain_key(w.corpus)})
    assert exc.value.refusal["code"] == "grounded-answers-blocked"
    assert w.corpus.advance() == before


def test_nothing_collected_is_said_rather_than_answered(inquiry, monkeypatch):
    w = inquiry
    topic = standing(w)["perspective"]
    from mentis.magnet import collection as C
    # A Magnet with no recorded collection: there is nothing to answer FROM,
    # and the refusal says so rather than writing an answer from anything else.
    monkeypatch.setattr(C, "read", lambda st, mid, **kw: {
        "magnet": mid, "config": {}, "activation": None, "page": None, "references": {}})
    with pytest.raises(Refused) as exc:
        cmd(w, "answer", topic)
    assert exc.value.refusal["code"] == "nothing-collected"
    assert "Collect first" in exc.value.refusal["error"]
    # An unreadable recorded collection is refused too, never substituted.
    def unreadable(st, mid, **kw):
        raise C.UnreadableCollection("the retained collection is missing or invalid")
    monkeypatch.setattr(C, "read", unreadable)
    with pytest.raises(Refused) as exc:
        cmd(w, "answer", topic)
    assert exc.value.refusal["code"] == "collection-unreadable"
    assert "no live source was substituted" in exc.value.refusal["error"]


def test_the_answer_route_is_reachable_at_the_one_perspective_door(inquiry):
    w = inquiry
    topic = standing(w)["perspective"]
    assert commands.command_of(f"magnets/{MAGNET}/perspectives/{topic}/answer") == \
        ("magnet-perspective", f"{MAGNET}/perspectives/{topic}/answer")
    got = owner_http(w, f"/{topic}/answer", {})
    assert got["status"] == 200, got
    body = json.loads(got["body"])
    assert body["provenance"] == {"grounded_in": "collection", "outside_authorized": [],
                                  "outside_reads": [], "explored_outside": False}
    assert "## Developments" in body["text"]
    # And the 405 help names it, so no client has to guess.
    assert "/answer" in json.loads(owner_http(w, f"/{topic}/not-a-verb", {})["body"])["error"]
