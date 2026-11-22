"""Result navigation reads real causal/provenance records, never prose guesses."""
from __future__ import annotations

import copy
import json

import pytest

from mentis import artifacts
from mentis.conversation import text
from mentis.operational import current_work as cw
from mentis.operational import result_destinations as rd
from mentis.operational import work_overview as wo
from mentis.spine import held
from tests._loop import a_conversation, world  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_models():
    cw.forget()
    yield
    cw.forget()


def ask(w, words="Make mockups", parent=None):
    cv, who = w["cv"], w["who"]["@brian"]
    if "results_cid" not in w:
        w["results_cid"] = a_conversation(w, "Design generations")
    cid = w["results_cid"]
    turn = cv.say(cid, who, [text(words)])
    exp = cv.expect(turn, of=who, kind="result", by=who, conversation=cid,
                    caused_by=parent)
    return exp


def delegate(w, parent, child):
    return w["cv"].record_act(actor=w["who"]["@brian"], act="work-delegated",
                              conversation=w["results_cid"], caused_by=parent,
                              about=[child], detail={})


def result(w, exp, count=1, *, turn=True, generation=1):
    cv, who, cid = w["cv"], w["who"]["@brian"], w["results_cid"]
    execution = f"result-{generation}-{exp}"
    start = cv.record_act(actor=who, act="execution-started", conversation=cid,
                          execution=execution, caused_by=exp, detail={})
    refs, blobs = [], []
    for n in range(count):
        b = artifacts.hold(cv.corpus, cv, f"generation {generation}: {n}".encode(),
                           act="artifact-returned", actor=who,
                           source="fixture", door="worker-return",
                           claimed_name=f"gen-{generation}-{n}.md",
                           claimed_media_type="text/markdown", execution=execution,
                           conversation=cid, caused_by=exp)
        refs.append(b["admission"])
        blobs.append(b)
    reply = cv.say(cid, who, [text(f"Generation {generation} returned")]) if turn else None
    ret = cv.record_act(actor=who, act="result-returned", conversation=cid,
                        turn=reply, execution=execution, caused_by=start,
                        detail={"returned_artifacts": refs})
    return {"refs": refs, "blobs": blobs, "reply": reply, "act": ret,
            "start": start, "execution": execution}


def claim(w, exp, refs, turn=None):
    cv = w["cv"]
    return cv.record_act(actor=w["who"]["@brian"], act="outcome-claimed",
                         conversation=w["results_cid"], turn=turn,
                         caused_by=exp, detail={"reply_turn": turn,
                         "result": "partly", "summary": "designs", "results": refs})


def index(w, exp):
    return rd.structural(wo._Ctx(w["cv"]), w["cv"]._act(exp))


def items(idx):
    return [i for g in idx["groups"] for i in g["items"]]


def test_raw_arrays_recovery_dedup_and_exact_claim_source(world):
    exp = ask(world)
    r = result(world, exp, 13)
    cv = world["cv"]
    cv.record_act(actor=world["who"]["@brian"], act="result-recovered",
                  conversation=world["results_cid"], turn=r["reply"],
                  execution=r["execution"], caused_by=r["start"],
                  detail={"returned_artifacts": r["refs"]})
    update = cv.say(world["results_cid"], world["who"]["@brian"], [text("carrier update")])
    claim(world, exp, [r["refs"][-1]], update)
    idx = index(world, exp)
    assert len(items(idx)) == 13
    assert [i["ref"] for i in items(idx)] == r["refs"]
    chosen = items(idx)[-1]
    assert chosen["source"]["turn"] == r["reply"]
    assert [b["kind"] for b in chosen["basis"]] == [
        "returned-by-run", "returned-by-run", "authored-result-ref"]
    assert {u["turn"] for u in idx["update_turns"]} == {r["reply"], update}
    assert not any("primary" in i for i in items(idx))


def test_long_multigeneration_thread_and_older_results_remain_retrievable(world):
    exp = ask(world)
    cv, cid, who = world["cv"], world["results_cid"], world["who"]["@brian"]
    expected = []
    for generation in range(25):
        cv.say(cid, who, [text("routing review and status")])
        expected.append(result(world, exp, 6, generation=generation))
        cv.say(cid, who, [text("not a mapped update")])
    for n in range(50):
        cv.say(cid, who, [text(f"later unrelated reply {n}")])
    idx = index(world, exp)
    compact = rd.page(idx, work=exp, brain="brain@one", compact=True)
    assert len(compact["groups"]) == 8
    assert compact["omitted_groups"] == 17
    assert compact["omitted_group_items"] == 102
    assert all(g["total_items"] == 6 and g["omitted_items"] == 2 for g in compact["groups"])
    assert compact["groups"][0]["id"] == expected[-1]["reply"]
    found, cursor = [], None
    while True:
        page = rd.page(idx, work=exp, brain="brain@one", results_before=cursor)
        found += [g["id"] for g in page["groups"]]
        cursor = page["next_results_before"]
        if not cursor:
            break
    assert found == [r["reply"] for r in reversed(expected)]
    assert len(idx["update_turns"]) == 25


def test_unplaced_return_is_explicit(world):
    exp = ask(world)
    r = result(world, exp, turn=False)
    g = index(world, exp)["groups"][0]
    assert g["id"] == r["act"] and g["source"] is None and g["unplaced"]


def test_attachment_requires_real_parts_and_submission_provenance(world):
    exp = ask(world)
    cv, cid, who = world["cv"], world["results_cid"], world["who"]["@brian"]
    r = result(world, exp)
    attached = artifacts.hold(cv.corpus, cv, b"attached", act="artifact-submitted",
                              actor=who, source="fixture", door="human-ingress",
                              conversation=cid)
    reply = cv.say(cid, who, [text(r["refs"][0]),
                             {"type": "file", "ref": attached["admission"]}])
    # hold came before the Turn; the actual ingress writer records submissions
    # after that Turn exists, in the same transaction.
    artifacts.record_submissions(cv.corpus, cv, [{**attached, "name": "attached.md"}], author=who,
                                 conversation=cid, turn=reply)
    claim(world, exp, [], reply)
    idx = index(world, exp)
    file = next(i for i in items(idx) if i["ref"] == attached["admission"])
    assert file["actionable"] and file["basis"][0]["kind"] == "attached-to-turn"
    assert file["source"]["turn"] == reply
    assert sum(i["ref"] == r["refs"][0] for i in items(idx)) == 1


def test_attached_followup_includes_earlier_returns_but_await_does_not(world):
    exp, follow, unrelated = ask(world), ask(world, "follow-up"), ask(world, "other")
    cv, who = world["cv"], world["who"]["@brian"]
    cv.await_work(exp, unrelated, by=who, because="awaiting is not delegation")
    r = result(world, follow)
    other = result(world, unrelated)
    cv.record_act(actor=who, act="follow-up-attached", conversation=world["results_cid"],
                  caused_by=exp, about=[follow], detail={"request": follow})
    idx = index(world, exp)
    assert [i["ref"] for i in items(idx)] == r["refs"]
    assert other["refs"][0] not in {i["ref"] for i in items(idx)}
    assert follow in idx["deps"]


def test_foreign_restricted_and_malformed_claims_never_prefetch_or_gain_action(world, monkeypatch):
    exp, other = ask(world), ask(world, "restricted other work")
    r = result(world, other)
    cv = world["cv"]
    artifacts.restrict(cv, other, by=world["who"]["@brian"], because="private sibling")
    update = cv.say(world["results_cid"], world["who"]["@brian"], [text("claim")])
    claim(world, exp, r["refs"] + ["adm-123", r["refs"][0] + "00", "https://x/"], update)
    grant = {"expectation": exp, "conversation": world["results_cid"],
             "execution": "projection-reader"}
    allowed, why = artifacts.reachable(cv.corpus, cv, grant, r["refs"][0])
    assert allowed is None and why
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("foreign prefetch"))
    idx = index(world, exp)
    out = rd.enrich(cv, rd.page(idx, work=exp, brain="brain@one"))
    assert len(items(out)) == 1
    i = items(out)[0]
    assert not i["actionable"] and i["source"] is None
    assert "artifact" not in i and i["reason"] == rd.UNVERIFIED
    # The owner projection does not change the existing execution reach.
    assert artifacts.restriction_of(cv, other) == other


@pytest.mark.parametrize("other_viewer", [False, True])
def test_real_answers_of_cache_keeps_structure_only(world, other_viewer):
    from mentis.conversation.shared_answer import answers_of
    exp = ask(world)
    r = result(world, exp)
    cv = world["cv"]
    viewer = world["steward"] if other_viewer else world["who"]["@brian"]
    cache, computed = answers_of(world["state"]), []
    def compute():
        computed.append(True)
        return wo.overview(cv, viewer=viewer, runtime={}, limit=1,
                           conversation=world["results_cid"])
    def read():
        structural = cache.get("api/work", compute, version=lambda: cv.corpus.steady)
        return rd.overview(cv, structural), structural
    first, cached = read()
    before, steady = copy.deepcopy(cached), cv.corpus.steady
    assert items(first["items"][0]["result_summary"])[0]["available"]
    held.path(cv.corpus.root, r["blobs"][0]["digest"]).unlink()
    second, reused = read()
    assert computed == [True] and reused is cached and cached == before
    assert cv.corpus.steady == steady
    assert not items(second["items"][0]["result_summary"])[0]["available"]


def test_explicit_post_reference_and_nonopenable_act_use_inspection(world):
    exp = ask(world)
    r = result(world, exp)
    claim(world, exp, [r["reply"], r["start"]])
    out = rd.enrich(world["cv"], rd.page(index(world, exp), work=exp, brain="brain@one"))
    post = next(i for i in items(out) if i["ref"] == r["reply"])
    run = next(i for i in items(out) if i["ref"] == r["start"])
    assert post["actionable"] and post["inspection"]["opens"] == "post"
    assert post["association"] == "referenced"
    assert not run["actionable"] and run["inspection"]["state"] == "ok"
    assert run["inspection"]["opens"] is None


def test_raw_array_without_its_production_relation_is_not_provenance(world, monkeypatch):
    exp, other = ask(world), ask(world, "other")
    r = result(world, other)
    cv = world["cv"]
    cv.record_act(actor=world["who"]["@brian"], act="result-returned",
                  caused_by=exp, conversation=world["results_cid"],
                  detail={"returned_artifacts": r["refs"]})
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("unproven prefetch"))
    assert not items(rd.enrich(cv, rd.page(index(world, exp), work=exp,
                                         brain="brain@one")))[0]["actionable"]


@pytest.mark.parametrize("change", ["missing", "corrupt", "purged"])
def test_request_time_availability_moves_without_structural_cache_expiry(world, change):
    exp = ask(world)
    r = result(world, exp)
    cv = world["cv"]
    idx = index(world, exp)
    # This is precisely the required answers_of seam: reuse the same structural
    # answer while enriching each HTTP read outside that cache.
    cached = {"items": [{"expectation": exp, "_result_index": idx}]}
    before = copy.deepcopy(cached)
    first = rd.overview(cv, cached)
    assert items(first["items"][0]["result_summary"])[0]["available"]
    blob = r["blobs"][0]
    path = held.path(cv.corpus.root, blob["digest"])
    if change == "missing":
        path.unlink()
    elif change == "corrupt":
        path.write_bytes(b"corrupted different size")
    else:
        artifacts.purge(cv.corpus, cv, blob["admission"],
                        by=world["who"]["@brian"], because="fixture")
    second = rd.overview(cv, cached)
    item = items(second["items"][0]["result_summary"])[0]
    assert not item["available"] and not item["actionable"]
    assert item["artifact"]["state"] == {
        "missing": "held-but-missing", "corrupt": "held-but-corrupt", "purged": "purged"}[change]
    assert "url" not in item["artifact"] and item["reason"]
    assert cached == before
    assert index(world, exp) == idx


def test_unreadable_is_visible_not_empty(world, monkeypatch):
    exp = ask(world)
    result(world, exp)
    idx = index(world, exp)
    def fail(*a, **k):
        raise OSError("descriptor temporarily unreadable")
    monkeypatch.setattr(artifacts, "describe", fail)
    out = rd.enrich(world["cv"], rd.page(idx, work=exp, brain="brain@one"))
    assert items(out)[0]["artifact"]["state"] == "unreadable"
    assert "temporarily unreadable" in items(out)[0]["reason"]


def synthetic(groups=22, count=25):
    return {"groups": [{"id": f"g-{g}", "source": None, "unplaced": True,
                        "items": [{"ref": f"adm-{g * count + n:012x}", "kind": "artifact",
                                   "actionable": True, "basis": [], "source": None}
                                  for n in range(count)]} for g in range(groups)],
            "update_turns": [], "deps": []}


def test_bounded_descriptors_and_item_continuation(world, monkeypatch):
    idx, calls = synthetic(), []
    def describe(corpus, ref, **kw):
        assert kw == {"verify": "cached"}
        calls.append(ref)
        return {"ref": ref, "state": "held"}
    monkeypatch.setattr(artifacts, "describe", describe)
    p = rd.page(idx, work="w", brain="brain@one")
    rd.enrich(world["cv"], p)
    assert len(calls) == 400
    calls.clear()
    g = p["groups"][0]
    rest = rd.page(idx, work="w", brain="brain@one", result_group=g["id"],
                   items_after=g["next_items_after"])
    rd.enrich(world["cv"], rest)
    assert len(calls) == 5 and rest["groups"][0]["next_items_after"] is None
    assert g["total_items"] == 25 and g["omitted_items"] == 5
    calls.clear()
    rd.enrich(world["cv"], rd.page(idx, work="w", brain="brain@one", compact=True))
    assert len(calls) == 32


@pytest.mark.parametrize("foreign", ["work", "instance", "structure", "malformed"])
def test_cursor_mismatch_requires_explicit_refresh(foreign):
    idx = synthetic()
    page = rd.page(idx, work="w", brain="brain@one")
    token, work, brain = page["next_results_before"], "w", "brain@one"
    if foreign == "work":
        work = "other"
    elif foreign == "instance":
        brain = "brain@two"
    elif foreign == "structure":
        idx["groups"].reverse()
    else:
        token = "broken"
    with pytest.raises(rd.RefreshResults, match="refresh"):
        rd.page(idx, work=work, brain=brain, results_before=token)


def test_descriptor_dedup_is_per_answer(world, monkeypatch):
    idx = synthetic(groups=2, count=1)
    idx["groups"][1]["items"][0]["ref"] = idx["groups"][0]["items"][0]["ref"]
    calls = []
    monkeypatch.setattr(artifacts, "describe", lambda c, ref, **k: (
        calls.append(ref) or {"ref": ref, "state": "held"}))
    rd.enrich(world["cv"], rd.page(idx, work="w", brain="brain@one"))
    assert len(calls) == 1


def test_work_limit_precedes_all_descriptor_work_and_detail_preserves_fields(world, monkeypatch):
    exp = ask(world)
    result(world, exp)
    cv = world["cv"]
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("omitted Work read"))
    out = rd.overview(cv, wo.overview(cv, viewer=world["who"]["@brian"],
                                     runtime={}, limit=0))
    assert out["items"] == []
    monkeypatch.undo()
    old = wo.detail(cv, exp, viewer=world["who"]["@brian"], runtime={})
    original = copy.deepcopy(old)
    new = rd.detail(cv, old)
    assert old == original and "_result_index" not in new
    assert {k: v for k, v in new.items() if k != "result_groups"} == {
        k: v for k, v in old.items() if k != "_result_index"}


def test_late_produced_link_reprojects_only_consulting_work(world, monkeypatch):
    exp, other = ask(world), ask(world, "other")
    cv, who = world["cv"], world["who"]["@brian"]
    r = result(world, exp)
    digest, _ = held.put(cv.corpus.root, b"late provenance")
    ref = cv.corpus.admit(source="fixture", locator="sha256:" + digest,
                          content="held", payload=None, observed_at=None,
                          payload_type="text/plain", envelope={}, attributed_to=who)
    made = cv.record_act(actor=who, act="artifact-returned", caused_by=exp,
                         execution=r["execution"], about=[ref], detail={})
    cv.record_act(actor=who, act="result-returned", caused_by=r["start"],
                  execution=r["execution"], turn=r["reply"],
                  detail={"returned_artifacts": [ref]})
    monkeypatch.setattr(cw, "_window", lambda *a: None)
    kept = cw.current_work(cv)
    model = kept.current(wait=True)
    assert not next(i for i in items(model.items[exp]["_result_index"])
                    if i["ref"] == ref)["actionable"]
    before, builds = kept.stats["projected"], kept.stats["builds"]
    cv.corpus.write(body={"reason": "provenance now linked"}, attributed_to=who,
                    link={"from": made, "to": ref, "relation": "produced"})
    model = kept.current(wait=True)
    assert next(i for i in items(model.items[exp]["_result_index"])
                if i["ref"] == ref)["actionable"]
    assert kept.stats["builds"] == builds and kept.stats["projected"] - before == 1
    assert kept.reconcile() == []


def test_maintained_full_parity_purge_targeting_and_no_live_io(world, monkeypatch):
    cv = world["cv"]
    monkeypatch.setattr(cw, "_window", lambda *args: None)
    exp, other = ask(world), ask(world, "other")
    r = result(world, exp)
    result(world, other)
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("model blob I/O"))
    kept = cw.current_work(cv)
    model = kept.current(wait=True)
    assert r["refs"][0] in model.deps[exp]
    assert r["refs"][0] not in model.deps[other]
    builds, projected = kept.stats["builds"], kept.stats["projected"]
    who = world["who"]["@brian"]
    purge = cv.record_act(actor=who, act="artifact-purged", about=r["refs"], detail={})
    cv.corpus.write(body={"reason": "fixture purge"}, attributed_to=who,
                    link={"from": purge, "to": r["refs"][0], "relation": "purged"})
    kept.current(wait=True)
    assert kept.stats["builds"] == builds
    assert kept.stats["projected"] - projected == 1
    fresh = cw.CurrentWork(cv).current(wait=True)
    assert kept._model.items == fresh.items
    assert kept.reconcile() == []


def test_late_provenance_followup_claim_and_deletion_keep_full_parity(world, monkeypatch):
    from mentis.conversation import versions
    cv, who = world["cv"], world["who"]["@brian"]
    monkeypatch.setattr(cw, "_window", lambda *args: None)
    exp = ask(world)
    r = result(world, exp)
    kept = cw.current_work(cv)
    kept.current(wait=True)
    def same():
        model = kept.current(wait=True)
        fresh = cw.CurrentWork(cv).current(wait=True)
        assert model.items == fresh.items
        return model.items[exp]["_result_index"]
    child = ask(world, "delegated generation", parent=exp)
    delegate(world, exp, child)
    child_result = result(world, child, generation=2)
    idx = same()
    assert child_result["refs"][0] in {i["ref"] for i in items(idx)}
    assert child_result["reply"] not in {t["turn"] for t in idx["update_turns"]}
    follow = ask(world, "earlier returned followup")
    f = result(world, follow, generation=3)
    cv.record_act(actor=who, act="expectation-met", caused_by=follow,
                  about=[exp], detail={"carried_under": exp})
    assert f["refs"][0] in {i["ref"] for i in items(same())}
    update = cv.say(world["results_cid"], who, [text("mapped carrier outcome")])
    claim(world, exp, r["refs"], update)
    assert update in {t["turn"] for t in same()["update_turns"]}
    versions.edit(cv, r["reply"], by=who, text="edited result", because="fixture")
    assert next(g for g in same()["groups"] if g["id"] == r["reply"])["source"]
    versions.delete(cv, r["reply"], by=who, because="fixture")
    assert next(g for g in same()["groups"] if g["id"] == r["reply"])["source"] is None
    assert kept.reconcile() == []


def test_worker_overview_does_not_serialize_owner_result_structure(world, monkeypatch):
    from mentis.web import _surface
    exp = ask(world)
    result(world, exp)
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("worker blob I/O"))
    cw.current_work(world["cv"]).current(wait=True)
    answer = _surface(world["state"]).work_overview(conversation=world["results_cid"])
    serialized = json.dumps(answer)
    assert "_result_index" not in serialized
    assert "result_summary" not in serialized and "returned-by-run" not in serialized


def test_empty_routing_returns_do_not_consume_group_cap_or_create_dead_groups(world):
    """B1: eight routing/review runs must not hide four real generations."""
    exp = ask(world)
    returned = [result(world, exp, 3, generation=n) for n in range(4)]
    empty = [result(world, exp, 0, generation=n + 4) for n in range(8)]
    result(world, exp, 0, turn=False, generation=12)
    # An explicit source-only report remains an exact, inspectable result.
    cv, who, cid = world["cv"], world["who"]["@brian"], world["results_cid"]
    report = cv.say(cid, who, [text("Source-only behavioral review and test report")])
    claim(world, exp, [report], report)
    # An empty return can also carry a real submitted attachment.
    attached = artifacts.hold(cv.corpus, cv, b"review attachment", act="artifact-submitted",
                              actor=who, source="fixture", door="human-ingress",
                              conversation=cid)
    turn = cv.say(cid, who, [{"type": "file", "ref": attached["admission"]}])
    artifacts.record_submissions(cv.corpus, cv, [{**attached, "name": "review.md"}], author=who,
                                 conversation=cid, turn=turn)
    cv.record_act(actor=who, act="result-returned", caused_by=exp, turn=turn,
                  detail={"returned_artifacts": ["adm-invalid"]})
    idx = index(world, exp)
    compact = rd.page(idx, work=exp, brain="brain@one", compact=True)
    assert compact["total_groups"] == 6 and compact["omitted_groups"] == 0
    assert compact["omitted_group_items"] == 0 and len(items(compact)) == 14
    assert all(g["items"] for g in compact["groups"])
    assert {r for ret in returned for r in ret["refs"]} <= {
        i["ref"] for i in items(compact)}
    assert {r["reply"] for r in empty} <= {u["turn"] for u in idx["update_turns"]}
    enriched = rd.enrich(cv, compact)
    assert next(i for i in items(enriched) if i["ref"] == report)["actionable"]
    assert next(i for i in items(enriched)
                if i["ref"] == attached["admission"])["actionable"]


def test_only_recorded_work_edges_include_results_and_preserve_provenance(world, monkeypatch):
    """B2: causal discovery/continuation is not delegation; pick-up is."""
    t1, t2 = ask(world, "first trunk"), ask(world, "second trunk")
    discovered = ask(world, "restricted discovered work", parent=t1)
    unrelated = ask(world, "unassigned discovery", parent=t1)
    continuation = ask(world, "separate human continuation", parent=t1)
    learning = ask(world, "separate learning evaluation", parent=t1)
    child = ask(world, "delegated child", parent=t1)
    delegate(world, t1, child)
    nested = ask(world, "delegated grandchild", parent=child)
    delegate(world, child, nested)
    follow = ask(world, "attached older follow-up")
    cv, who, cid = world["cv"], world["who"]["@brian"], world["results_cid"]
    for found in (discovered, unrelated):
        cv.record_act(actor=who, act="work-discovered", caused_by=t1,
                      about=[found], detail={})
    cv.grant_authority(continuation, [], by=who, source="continuation",
                        origin=t1, because="the human continued the earlier request")
    assert continuation in cv.continuations_of(t1)
    cv.assign(discovered, who, by=who, detail={"picked_up_under": t2})
    delegate(world, t2, discovered)
    artifacts.restrict(cv, discovered, by=who, because="restricted discovery")
    returns = {e: result(world, e, generation=n) for n, e in enumerate(
        (t1, t2, discovered, unrelated, continuation, learning, child, nested, follow))}
    cv.record_act(actor=who, act="follow-up-attached", caused_by=child,
                  about=[follow], detail={"request": follow})
    # Cyclic attachment must terminate and preserve exact owners.
    cv.record_act(actor=who, act="follow-up-attached", caused_by=follow,
                  about=[t1], detail={"request": t1})
    before = artifacts.reachable(cv.corpus, cv,
        {"expectation": child, "conversation": cid}, returns[discovered]["refs"][0])
    assert before[0] is None
    described = []
    real_describe = artifacts.describe
    def describe(corpus, ref, **kw):
        described.append(ref)
        return real_describe(corpus, ref, **kw)
    monkeypatch.setattr(artifacts, "describe", describe)
    one, two = index(world, t1), index(world, t2)
    rd.enrich(cv, rd.page(one, work=t1, brain="brain@one"))
    assert set(described) == {returns[e]["refs"][0] for e in (t1, child, nested, follow)}
    assert {i["ref"] for i in items(two)} == {
        returns[e]["refs"][0] for e in (t2, discovered)}
    for idx, expected in ((one, (t1, child, nested, follow)), (two, (t2, discovered))):
        for e in expected:
            item = next(i for i in items(idx) if i["ref"] == returns[e]["refs"][0])
            assert item["actionable"] and item["association"] == "verified"
            assert item["source"]["turn"] == returns[e]["reply"]
            assert item["basis"][0]["work"] == e
    assert artifacts.reachable(cv.corpus, cv,
        {"expectation": child, "conversation": cid}, returns[discovered]["refs"][0]) == before


def test_pickup_and_legacy_handover_invalidate_only_affected_work(world, monkeypatch):
    """B2/B3: maps expire per update; detail-only edges invalidate parents."""
    cv, who = world["cv"], world["who"]["@brian"]
    monkeypatch.setattr(cw, "_window", lambda *a: None)
    t1, t2, other = ask(world), ask(world), ask(world)
    found = ask(world, "discovered under first", parent=t1)
    follow = ask(world, "legacy follow-up")
    r, f = result(world, found), result(world, follow)
    kept = cw.current_work(cv)
    model = kept.current(wait=True)
    assert not items(model.items[t1]["_result_index"])
    builds = kept.stats["builds"]
    def same():
        model = kept.current(wait=True)
        assert model.items == cw.CurrentWork(cv).current(wait=True).items
        assert kept.stats["builds"] == builds
        return model
    projected = kept.stats["projected"]
    cv.assign(found, who, by=who, detail={"picked_up_under": t2, "taken_up": True})
    model = same()
    assert r["refs"][0] in {i["ref"] for i in items(model.items[t2]["_result_index"])}
    assert kept.stats["projected"] - projected == 3  # old/new parents and found
    assert not items(model.items[other]["_result_index"])
    cv.assign(found, who, by=who, detail={"picked_up_under": t1, "taken_up": True})
    model = same()
    assert not items(model.items[t2]["_result_index"])
    assert {i["ref"] for i in items(model.items[t1]["_result_index"])} == set(r["refs"])
    # A historical carried_under edge need not put the parent in about.
    cv.record_act(actor=who, act="expectation-met", caused_by=follow,
                  detail={"carried_under": t2})
    model = same()
    assert {i["ref"] for i in items(model.items[t2]["_result_index"])} == set(f["refs"])
    assert kept.reconcile() == []
