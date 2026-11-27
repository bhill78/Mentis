"""Part A: a Magnet-scoped execution reads its own collection, and nothing else.

THE OWNER'S CORRECTION UNDER TEST (`ent-d85254fe5e1b`, Turn #277): a Magnet's
configured sources determine its collection scope, and a Perspective must not
silently use unrelated Brain records or acquired files merely because its agent
can technically reach them. That enforcement did not exist, which is the only
reason `perspectives.GROUNDED_ANSWERS_ENABLED` was `False`. It exists now
(`mentis.magnet.scope`), and this is the suite that says so.

EVERYTHING HERE GOES THROUGH THE REAL DOOR. A real fixture Brain, a real
recorded collection batch committed through the real activation route, a real
managed exchange through `/fluid/api/requests`, a real grant minted by the real
`Authority`, and every read asked over HTTP at `/api/worker`. Nothing calls
`scope.why_not` as a function to decide whether a read is refused: what is
asserted is what the door answered.

WHAT IT PROVES, in the order the hand-off names:
  (i)   it reads that Magnet's batch rows and the posts of its own Conversation;
  (ii)  another Conversation, an unrelated record and a collection outside the
        Magnet's configured sources are each refused at the door, in its words;
  (iii) an unauthorized exchange cannot reach outside;
  (iv)  an authorization does not survive into the next exchange;
  (v)   a synthesis run cannot be authorized wider at all.
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from mentis import artifacts
from mentis.conversation import text as text_part
from mentis.conversation.owner import _owner
from mentis.execution import RunResult
from mentis.fluid import commands, message_context as MC
from mentis.fluid.inspect import brain_key
from mentis.magnet import perspectives as P, scope as S
from mentis.web import dispatch as D
from mentis.worker import CAPABILITY_HEADER
from tests.test_magnet_activation import (MAGNET, JSON_HEADERS, world, built,  # noqa: F401
                                          artifact_of, define_from, ask_commit, send)

OUTSIDE_COLLECTION = "col-outside000"
CONFIGURED_COLLECTION = "col-configured"


# -- the world: a Magnet with a real batch, in its own Conversation -----------


@pytest.fixture
def magnet(world, monkeypatch):
    """A Magnet with one committed collection batch and its own Conversation,
    whose definition configures one collection as a source.

    Dispatch is CAPTURED rather than run: every test here mints the grant the
    real seam computes and asks the real door under it, so no run has to
    perform. The one test of the seam itself dispatches for real.
    """
    w = world
    import mentis.web as web
    w.sent = []
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: w.sent.append(kw))
    raw = artifact_of(w, op="scope-batch")
    define_from(w, raw)
    answer = ask_commit(w, raw)["body"]
    assert answer["state"] == "complete", answer
    w.batch = answer["artifact"]
    w.cid = answer["conversation"]
    w.owner = _owner(w.cv)
    # The definition keeps everything the commit wrote, and gains one
    # configured collection: what a configured source read is held against.
    config = json.loads(w.definition_path.read_text(encoding="utf-8"))
    config["sources"] = [*config.get("sources", ()),
                         {"kind": "file", "collection": CONFIGURED_COLLECTION}]
    w.define(config)
    commands._magnet_config.cache_clear() if hasattr(
        commands._magnet_config, "cache_clear") else None
    return w


def elsewhere(w):
    """A Conversation that is not this Magnet's, with a post and a Participant
    of its own: the 'another Conversation' and 'unrelated record' of (ii)."""
    cid = w.cv.open_conversation("Somewhere else entirely")
    who = w.cv.create_participant("@Stranger" + uuid.uuid4().hex[:6])
    post = w.cv.say(cid, who, [text_part("nothing here is this Magnet's")])
    return {"conversation": cid, "participant": who, "post": post}


# -- a managed exchange, and the grant a run carrying it is dispatched with ----


def exchange(w, *, words="what arrived in the collection?", selector=None,
             dispatch=True, agent=None, reach="conversation"):
    """One managed exchange in the Magnet's own Conversation, sent through the
    real request door. Returns the asking Turn, its expectation and the frozen
    managed context the door recorded."""
    agent = agent or w.cv.create_participant("@ScopeAgent" + uuid.uuid4().hex[:6])
    body = {"from": {"magnet": MAGNET}, "author": w.owner, "text": words,
            "parts": [{"type": "text", "text": words}],
            "op": "scope-exchange-" + uuid.uuid4().hex[:8]}
    if selector is not None:
        body["magnet_context"] = selector
    if dispatch:
        body.update(action="ask-participant", addressed_to=[agent],
                    dispatch=[{"participant": agent, "runtime": "codex",
                               "reach": reach}])
    else:
        body["action"] = "record-only"
    got = send(w.alone, "/fluid/api/requests",
               [*JSON_HEADERS, ["X-Mentis-Brain", brain_key(w.corpus)]],
               json.dumps(body).encode("utf-8"))
    assert got["status"] == 200, got["body"]
    answer = json.loads(got["body"])
    routed = w.corpus.operational(act=MC.ROUTED, turn=answer["post"])[0]
    return {"turn": answer["post"], "agent": agent,
            "expectation": (answer.get("expectations") or [None])[0],
            "managed": (routed["detail"] or {}).get("managed_context")}


def granted(w, ex, *, scope=None, operations=("respond",)):
    """The grant a run carrying this exchange is dispatched with, minted by the
    real `Authority` with the scope the real dispatch seam computes."""
    authority = w.state.agents.authority
    instance = "magnet-run-" + uuid.uuid4().hex[:8]
    authority.authorise_for(instance, dict(
        scope=scope or D._magnet_scope(ex["managed"]),
        operations=list(operations), expectation=ex["expectation"],
        conversation=w.cid, participant=ex["agent"], runtime="claude"))
    return instance, authority._grant(instance, w.state.path)


def door(w, token, op, **args):
    """One call at the real `/api/worker` door, under that grant."""
    got = send(w.alone, "/api/worker",
               [["Content-Type", "application/json"], [CAPABILITY_HEADER, token]],
               json.dumps({"corpus": w.state.path, "op": op,
                           "args": args}).encode("utf-8"), owner=False, half_close=False)
    return got["status"], json.loads(got["body"] or b"{}")


def refused(answer) -> str:
    assert answer.get("kind") == "PermissionError", answer
    return answer["error"]


# -- the dispatch seam --------------------------------------------------------


def test_the_dispatch_seam_confines_a_magnet_exchange(magnet, monkeypatch):
    """A run carrying a Magnet exchange is dispatched Magnet-scoped, and a run
    carrying a Perspective question is dispatched synthesis-scoped. Read off
    the grant the run ACTUALLY held, while it held it."""
    w = magnet
    import mentis.web as web
    svc = w.state.agents
    grants: list[dict] = []

    def stop(spec):
        grants.append(svc.authority.grant_for(
            svc.authority.grant_of(spec.run_id), w.state.path))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=False,
                         error_kind="test_stop", error="stopped once granted",
                         started_at=now, finished_at=now)

    for backend in svc.execution.backends():
        svc.execution.script = {**(svc.execution.script or {}),
                                backend["id"]: stop}
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(w.state, **kw))
    exchange(w)
    assert grants and grants[0], grants
    assert grants[0]["scope"] == "magnet:" + MAGNET
    assert S.parsed(grants[0]["scope"]).kind == S.CONVERSATION

    # A SYNTHESIS RUN IS A DIFFERENT SCOPE, decided from the frozen context.
    said = {"version": 1, "mode": "ordinary", "perspective": None,
            "references": [], "configuration_digest": "0" * 64}
    assert D._magnet_scope({"magnet": MAGNET, "selector": said}) == "magnet:" + MAGNET
    with_question = {**said, "perspective": {"id": "ent-x", "question_ref": "adm-y",
                                             "question_digest": "0" * 64}}
    assert D._magnet_scope({"magnet": MAGNET, "selector": with_question}) == (
        "magnet-synthesis:" + MAGNET)
    # NOT A MAGNET REQUEST AT ALL: nothing changes.
    assert D._magnet_scope(None) is None
    # AN UNREADABLE MAGNET ID STILL CONFINES: it never falls back to worker.
    broken = D._magnet_scope({"magnet": None, "selector": said})
    assert S.parsed(broken) is not None and S.parsed(broken).magnet is None


def test_a_magnet_scoped_grant_is_never_mirrored_to_the_rust_front(magnet):
    """What this execution may read is decided per target, in Python, at the
    door. The front's moved reads (`resolve`, `history`, `find`) would answer
    one from the ordinary worker set, so the front must hold nothing of this
    grant and forward it (AGENTS.md: a grant Rust doesn't hold is forwarded)."""
    from mentis.mirror import mirrored
    ordinary = {"corpus": "c", "scope": "organising", "operations": ["respond"]}
    assert mirrored(ordinary) is not None
    for scope in ("magnet:" + MAGNET, "magnet-synthesis:" + MAGNET, "magnet:"):
        assert mirrored({**ordinary, "scope": scope}) is None, scope


# -- (i) what it may read -----------------------------------------------------


def test_it_reads_its_own_batch_and_its_own_conversations_posts(magnet):
    """(i) The Magnet's recorded collection batch, and the posts of its own
    Conversation, including the asking Turn of this exchange."""
    w = magnet
    ex = exchange(w)
    _, token = granted(w, ex, scope="magnet:" + MAGNET)

    status, got = door(w, token, "read_artifact", ref=w.batch["ref"])
    assert status == 200, got
    assert got["ref"] == w.batch["ref"] and got["digest"] == w.batch["digest"]
    assert got["door"] == "magnet-extract"

    status, got = door(w, token, "resolve", ref=ex["turn"])
    assert status == 200 and got["known"] is True, got

    status, got = door(w, token, "history", conversation=w.cid)
    assert status == 200 and got.get("conversation") == w.cid, got

    status, got = door(w, token, "orient", conversation=w.cid)
    assert status == 200 and "refused" not in got, got


# -- (ii) what is refused at the door, in its words ---------------------------


def test_another_conversation_and_an_unrelated_record_are_refused(magnet):
    """(ii) first half: a Conversation that is not this Magnet's, a post in it,
    and a Participant that is nowhere near it."""
    w = magnet
    other = elsewhere(w)
    ex = exchange(w)
    _, token = granted(w, ex, scope="magnet:" + MAGNET)

    for ref in (other["conversation"], other["post"], other["participant"]):
        status, got = door(w, token, "resolve", ref=ref)
        assert status == 403, (ref, status, got)
        words = refused(got)
        assert f"outside Magnet {MAGNET}'s collection scope" in words
        assert "ent-d85254fe5e1b" in words
        assert "Report what you could not read" in words
        assert got["refusal"]["boundary"] == "place"
        assert got["refusal"]["op"] == "resolve"

    status, got = door(w, token, "history", conversation=other["conversation"])
    assert status == 403 and "collection scope" in refused(got)
    # A Participant's history crosses Conversations, so it is refused as such.
    status, got = door(w, token, "history", participant=other["participant"])
    assert status == 403 and "crosses Conversations" in refused(got)
    # `orient` with no Conversation would list what else this Brain holds.
    status, got = door(w, token, "orient")
    assert status == 403 and "own Conversation" in refused(got)


def test_a_brain_wide_read_is_refused_not_narrowed(magnet):
    """A read that cannot be pointed at one Magnet is refused by the door's own
    scope table (`permitted`), with the door's own words. `delegate` among
    them: a child's grant is minted from its own request, so delegating would
    be a way around this confinement."""
    w = magnet
    ex = exchange(w)
    _, token = granted(w, ex, scope="magnet:" + MAGNET,
                       operations=["respond", "open_topic", "coordinate"])
    for op in ("find", "recall", "governed", "work_overview", "brief",
               "owner_decisions", "delegate", "open_topic", "record_material"):
        status, got = door(w, token, op, q="anything", work="anything")
        assert status == 403, (op, status, got)
        words = refused(got)
        assert f"{op!r} is not admissible for this execution" in words
        assert f"scope 'magnet:{MAGNET}'" in words
    # ...and it can still answer the owner, which is the point of narrowing
    # rather than refusing the whole run.
    assert "respond" in json.loads(json.dumps(list(
        __import__("mentis.worker", fromlist=["permitted"]).permitted(
            "magnet:" + MAGNET, ["respond"]))))


def test_an_unauthorized_exchange_cannot_reach_outside(magnet):
    """(iii) Configured sources are readable; anything else is not, and the
    refusal says an authorization is the owner's own act on one exchange."""
    w = magnet
    ex = exchange(w)
    _, token = granted(w, ex, scope="magnet:" + MAGNET)

    status, got = door(w, token, "sources", collection=OUTSIDE_COLLECTION)
    assert status == 403, got
    words = refused(got)
    assert f"collection {OUTSIDE_COLLECTION!r} is not a configured source" in words
    assert CONFIGURED_COLLECTION in words
    assert "does not carry into the next exchange" in words

    for op, args in (("read_source", {"collection": OUTSIDE_COLLECTION,
                                      "path": "a.txt"}),
                     ("source_history", {"collection": OUTSIDE_COLLECTION,
                                         "path": "a.txt"}),
                     ("source_links", {"collection": OUTSIDE_COLLECTION,
                                       "path": "a.txt"}),
                     ("search_sources", {"q": "anything",
                                         "collection": OUTSIDE_COLLECTION})):
        status, got = door(w, token, op, **args)
        assert status == 403, (op, got)
        assert "is not a configured source" in refused(got)

    # A SOURCE READ THAT NAMES NO COLLECTION reads across this Brain's acquired
    # material, so it is refused and told which collections it may name.
    for op, args in (("sources", {}), ("search_sources", {"q": "anything"})):
        status, got = door(w, token, op, **args)
        assert status == 403, (op, got)
        assert "configured source collections" in refused(got)
        assert CONFIGURED_COLLECTION in refused(got)

    # THE CONFIGURED ONE IS NOT REFUSED AT THE DOOR. The collection is declared
    # nowhere in this fixture, so the source read answers its own refusal --
    # which is exactly the difference being asserted: 200 with the read's
    # answer, never 403 with the door's.
    status, got = door(w, token, "sources", collection=CONFIGURED_COLLECTION)
    assert status == 200, got
    assert got.get("kind") != "PermissionError"


# -- the owner's per-exchange authorization -----------------------------------


def authorize(w, ex, opens, *, by=None):
    return S.authorize(w.state, MAGNET, turn=ex["turn"], opens=opens,
                       by=by or w.owner, op="auth-" + uuid.uuid4().hex[:8])


def test_an_authorization_opens_only_what_it_names(magnet):
    w = magnet
    ex = exchange(w)
    done = authorize(w, ex, [{"kind": "collection",
                              "collection": OUTSIDE_COLLECTION}])
    assert done["opens"] == [{"kind": "collection",
                              "collection": OUTSIDE_COLLECTION}]
    _, token = granted(w, ex, scope="magnet:" + MAGNET)

    # The one it named is open...
    status, got = door(w, token, "sources", collection=OUTSIDE_COLLECTION)
    assert status == 200, got
    # ...and nothing else is.
    status, got = door(w, token, "sources", collection="col-another0000")
    assert status == 403 and "is not a configured source" in refused(got)
    # It opens no Brain record either: the authorization is about sources.
    other = elsewhere(w)
    status, got = door(w, token, "resolve", ref=other["post"])
    assert status == 403 and "collection scope" in refused(got)

    # AND THE RECORD SHOWS WHAT THE ANSWER REACHED.
    told = S.provenance(w.cv, MAGNET, turn=ex["turn"])
    assert told["outside_authorized"] == [{"kind": "collection",
                                           "collection": OUTSIDE_COLLECTION}]
    assert told["explored_outside"] is True
    assert {"what": "sources", "collection": OUTSIDE_COLLECTION} in told[
        "outside_reads"]
    assert told["grounded_in"] == "collection"


def test_an_authorization_does_not_survive_into_the_next_exchange(magnet):
    """(iv) It is the owner's act on ONE asking Turn. The next exchange is a
    different Turn, and is unauthorized again with no further act."""
    w = magnet
    first = exchange(w)
    authorize(w, first, [{"kind": "collection",
                          "collection": OUTSIDE_COLLECTION}])
    _, token = granted(w, first, scope="magnet:" + MAGNET)
    assert door(w, token, "sources", collection=OUTSIDE_COLLECTION)[0] == 200

    later = exchange(w, words="and what about this?")
    assert later["turn"] != first["turn"]
    _, next_token = granted(w, later, scope="magnet:" + MAGNET)
    status, got = door(w, next_token, "sources", collection=OUTSIDE_COLLECTION)
    assert status == 403, got
    assert "is not a configured source" in refused(got)
    assert S.provenance(w.cv, MAGNET, turn=later["turn"]) == {
        "grounded_in": "collection", "outside_authorized": [],
        "outside_reads": [], "explored_outside": False}


def test_only_the_owner_authorizes_and_never_an_execution(magnet):
    """An agent cannot authorize itself: the act is the owner's own, on the
    owner's own asking Turn, and an act an execution wrote opens nothing."""
    w = magnet
    ex = exchange(w)
    imposter = w.cv.create_participant("@Imposter" + uuid.uuid4().hex[:6])
    with pytest.raises(S.Refused) as got:
        authorize(w, ex, [{"kind": "collection",
                           "collection": OUTSIDE_COLLECTION}], by=imposter)
    assert "only the recorded owner authorizes" in str(got.value)

    # An act in the owner's name that an EXECUTION wrote opens nothing: the
    # door reads `execution` off the act, not the actor alone.
    w.cv.record_act(actor=w.owner, act=S.AUTHORIZED, conversation=w.cid,
                    turn=ex["turn"], execution="some-execution",
                    detail={"magnet": MAGNET, "turn": ex["turn"],
                            "opens": [{"kind": "collection",
                                       "collection": OUTSIDE_COLLECTION}]})
    _, token = granted(w, ex, scope="magnet:" + MAGNET)
    status, got = door(w, token, "sources", collection=OUTSIDE_COLLECTION)
    assert status == 403 and "is not a configured source" in refused(got)

    # An authorization on another Magnet's exchange, or on another Turn, is
    # not this exchange's.
    other = elsewhere(w)
    for turn, why in ((other["post"], "this Magnet's own Conversation"),):
        with pytest.raises(S.Refused) as bad:
            S.authorize(w.state, MAGNET, turn=turn,
                        opens=[{"kind": S.RUNTIME_SEARCH}], by=w.owner,
                        op="auth-" + uuid.uuid4().hex[:8])
        assert why in str(bad.value)


@pytest.mark.parametrize("opens", [
    [], None, "collection", [{"kind": "anything"}], [{"kind": "collection"}],
    [{"kind": "collection", "collection": ""}],
    [{"kind": S.RUNTIME_SEARCH, "collection": "col-x"}],
    [{"kind": "collection", "collection": "col-x"},
     {"kind": "collection", "collection": "col-x"}],
    [{"kind": S.RUNTIME_SEARCH}] * 5,
])
def test_an_authorization_names_what_it_opens(magnet, opens):
    w = magnet
    ex = exchange(w)
    with pytest.raises(S.Refused):
        authorize(w, ex, opens)


# -- (v) synthesis is never widened -------------------------------------------


def test_a_synthesis_run_cannot_be_authorized_wider_at_all(magnet):
    """(v) Structural, not conventional, and in three independent places:

      * the synthesis scope's operation set holds no source read, so there is
        nothing for an authorization to open;
      * `scope.authorization` reads none for a synthesis confinement, whatever
        the record holds;
      * `Reach.outside` is empty for it, so even a forged authorization opens
        nothing.
    """
    w = magnet
    ex = exchange(w)
    authorize(w, ex, [{"kind": "collection", "collection": OUTSIDE_COLLECTION}])
    _, token = granted(w, ex, scope="magnet-synthesis:" + MAGNET)

    # Not even the configured collection: synthesis is grounded in the
    # collected rows, so it reads no live collection at all.
    for collection in (OUTSIDE_COLLECTION, CONFIGURED_COLLECTION):
        for op in S.OUTSIDE_READS:
            status, got = door(w, token, op, collection=collection,
                               path="a.txt", q="anything")
            assert status == 403, (op, collection, got)
            assert f"{op!r} is not admissible for this execution" in refused(got)
            assert f"scope 'magnet-synthesis:{MAGNET}'" in refused(got)

    # It still reads what it is grounded in.
    assert door(w, token, "read_artifact", ref=w.batch["ref"])[0] == 200
    assert door(w, token, "resolve", ref=ex["turn"])[0] == 200

    # The authorization is not read for it, and opens nothing in it.
    synthesis = S.Confinement(S.SYNTHESIS, MAGNET)
    assert S.authorization(w.cv, synthesis, ex["turn"]) == ()
    forged = S.Reach(S.SYNTHESIS, MAGNET, w.cid, ex["turn"], frozenset(),
                     ({"kind": "collection", "collection": OUTSIDE_COLLECTION},),
                     frozenset())
    assert forged.outside == frozenset()
    assert forged.readable_collections == frozenset()
    # And its provenance can never say it explored outside.
    assert S.provenance(w.cv, MAGNET, turn=ex["turn"], synthesis=True) == {
        "grounded_in": "collection", "outside_authorized": [],
        "outside_reads": [], "explored_outside": False}
    # There is no code path that hands a synthesis confinement a source read.
    assert not set(S.narrowed(synthesis, S.OUTSIDE_READS))


def test_a_confinement_that_cannot_be_confirmed_reads_nothing(magnet):
    """Fails closed. A scope that says Magnet and names none, and a Magnet
    whose own Conversation cannot be read, each refuse every read rather than
    falling through to the ordinary worker grant."""
    w = magnet
    ex = exchange(w)
    for scope in ("magnet:", "magnet:mag-nothinghere", "magnet-synthesis:"):
        _, token = granted(w, ex, scope=scope)
        status, got = door(w, token, "resolve", ref=ex["turn"])
        assert status == 403, (scope, got)
        assert "cannot be confirmed from the record" in refused(got)
        assert door(w, token, "read_artifact", ref=w.batch["ref"])[0] == 403


def test_the_explicitly_selected_references_are_in_scope(magnet):
    """The third thing a Magnet-scoped execution reads: what the owner selected
    in this exchange's `magnet_context`, by its exact recorded identity."""
    w = magnet
    said = w.cv.say(w.cid, w.owner, [text_part("the row I mean")])
    line = __import__("mentis.conversation.versions", fromlist=["lineage"]).lineage(
        w.corpus, said)
    digest = MC.digest(line["current"]["body"].get("parts") or [])
    selector = {"version": 1, "mode": "ordinary", "perspective": None,
                "configuration_digest": MC.digest(MC.definition_body(
                    commands._magnet_config(w.state, MAGNET))),
                "references": [{"kind": "post", "ref": said,
                                "version": line["current"]["id"],
                                "digest": digest}]}
    ex = exchange(w, selector=selector)
    assert (ex["managed"]["selector"]["references"][0]["ref"]) == said
    _, token = granted(w, ex, scope="magnet:" + MAGNET)
    status, got = door(w, token, "resolve", ref=said)
    assert status == 200 and got["known"] is True, got
    assert S.reach(__import__("mentis.web", fromlist=["_surface"])._surface(
        w.state), S.parsed("magnet:" + MAGNET),
        {"expectation": ex["expectation"]}).selected >= {said}


def test_an_acquired_image_outside_the_configured_sources_is_refused(magnet):
    """`read_artifact` serves acquired images wherever `read_source` would, so
    the same collection rule applies to it. An artifact that is neither this
    Magnet's own material, nor acquired from a readable collection, nor held in
    its own Conversation, is refused."""
    w = magnet
    ex = exchange(w)
    _, token = granted(w, ex, scope="magnet:" + MAGNET)
    other = elsewhere(w)
    held = artifacts.hold(w.corpus, w.cv, b'{"not":"this magnet"}',
                          act=artifacts.SUBMITTED, actor=other["participant"],
                          source="somewhere-else", door="test",
                          claimed_name="elsewhere.json",
                          claimed_media_type="application/json")
    status, got = door(w, token, "read_artifact", ref=held["admission"])
    assert status == 403, got
    assert f"outside Magnet {MAGNET}'s collection scope" in refused(got)

    # THIS MAGNET'S OWN PERSPECTIVE MATERIAL IS IN SCOPE, and whatever still
    # refuses it is not this boundary. NARROWING ONLY: the gate says nothing
    # about it, and the ordinary reach rules answer as they always did -- which
    # is where Part B's read-side widening (`opr-d4b617de6850`) lands, not
    # here. The distinction is the whole claim of this part, so it is asserted
    # rather than assumed.
    from mentis.web import _surface
    own = P.hold(w.state, MAGNET, {"its": "own"}, w.owner)
    confined, grant = S.parsed("magnet:" + MAGNET), {"expectation": ex["expectation"]}
    assert S.why_not(_surface(w.state), confined, grant, "read_artifact",
                     {"ref": own["ref"]}) is None
    assert S.why_not(_surface(w.state), confined, grant, "read_artifact",
                     {"ref": held["admission"]}) is not None
    status, got = door(w, token, "read_artifact", ref=own["ref"])
    if status == 403:
        assert "collection scope" not in refused(got), got
        assert got.get("refusal", {}).get("boundary") != "place", got


def test_the_gate_only_ever_refuses(magnet):
    """Narrowing only. Every operation the narrowed set admits is either
    refused by the gate or left exactly as the ordinary rules answered it:
    nothing here can admit a read the ordinary rules would refuse."""
    from mentis.worker import permitted
    ordinary = set(permitted("organising", ["respond", "open_topic",
                                            "coordinate"]))
    for synthesis in (False, True):
        confined = S.parsed(S.scope_name(MAGNET, synthesis=synthesis))
        may = set(permitted(S.scope_name(MAGNET, synthesis=synthesis),
                            ["respond", "open_topic", "coordinate"]))
        assert may <= ordinary, may - ordinary
        assert may <= set(S.MAY_CALL) | set(S.OUTSIDE_READS)
        assert S.narrowed(confined, ()) == ()
