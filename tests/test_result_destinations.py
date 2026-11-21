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
    cid = w.setdefault("results_cid", a_conversation(w, "Design generations"))
    turn = cv.say(cid, who, [text(words)])
    exp = cv.expect(turn, of=who, kind="result", by=who, conversation=cid,
                    caused_by=parent)
    return exp


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
    r = result(world, follow)
    other = result(world, unrelated)
    cv, who = world["cv"], world["who"]["@brian"]
    cv.record_act(actor=who, act="follow-up-attached", conversation=world["results_cid"],
                  caused_by=exp, about=[follow], detail={"request": follow})
    cv.await_work(exp, unrelated, by=who, because="awaiting is not delegation")
    idx = index(world, exp)
    assert [i["ref"] for i in items(idx)] == r["refs"]
    assert other["refs"][0] not in {i["ref"] for i in items(idx)}
    assert follow in idx["deps"]


def test_foreign_restricted_and_malformed_claims_never_prefetch_or_gain_action(world, monkeypatch):
    exp, other = ask(world), ask(world, "restricted other work")
    r = result(world, other)
    cv = world["cv"]
    update = cv.say(world["results_cid"], world["who"]["@brian"], [text("claim")])
    claim(world, exp, r["refs"] + ["adm-123", r["refs"][0] + "00", "https://x/"], update)
    monkeypatch.setattr(artifacts, "describe", lambda *a, **k: pytest.fail("foreign prefetch"))
    idx = index(world, exp)
    out = rd.enrich(cv, rd.page(idx, work=exp, brain="brain@one"))
    assert len(items(out)) == 1
    i = items(out)[0]
    assert not i["actionable"] and i["source"] is None
    assert "artifact" not in i and i["reason"] == rd.UNVERIFIED


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
