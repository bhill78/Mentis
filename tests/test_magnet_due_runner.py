"""THE BOUND OF THE SCHEDULED-COLLECTION PASS (`mentis.magnet.due`, Part D2/D1).

AGENTS.md asks a new background mechanism for an owner decision, a stated bound and a test of
that bound. The decision is owner request #802 (`ent-d8b83ce78ac2`) and its correction
(`ent-8a4357b5f7fc`); the bound is stated in `mentis/magnet/due.py`'s docstring and in AGENTS.md
under "Background work"; this file is the test of it. Every limit is checked by its named
constant, so raising one here does not weaken the test.

What is NOT tested here, and cannot be from Python: the processor that reads a Magnet's sources
and produces the page is Rust's (`crates/mentis-server/src/front/activate.rs`,
`handlers::magnet::activation_page`), and Python has none by design -- `activation.public` answers
`processor-unavailable`. So the collections here go through a stand-in for the front's door, and
one test sends the real unattended request to the real public activation door on a real server to
show that the door, the body and the absence of any credential are what this runner actually
sends.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from mentis.magnet import activation as X
from mentis.magnet import due as D
from mentis.web import _Handler, _State, fixture

MAGNET = "mag-a1c7e2f09b3d4e68"


# -- a Brain with Magnets in it -------------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("due-seed") / "brain"
    fixture.build(str(root))
    return root


class World:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.state = _State(str(root))
        self.corpus, self.cv = self.state.corpus, self.state.cv
        self.who = self.corpus.entries_of_kind("participant")[0]["id"]
        self.servers = []

    def define(self, mid, *, mode="scheduled", schedule="PT1H", collection=None):
        """A definition this build can run, in the mode asked for."""
        sources = [{"kind": "conversation", "conversation": self.a_conversation()}]
        for i, key in enumerate([collection] if isinstance(collection, str)
                                else list(collection or ())):
            sources.append({"kind": "file", "collection": key, "path": f"a/b{i}.txt"})
        config = {
            "id": mid, "sources": sources, "selection": {"informationTypes": ["post"]},
            "collection": ({"mode": mode, "schedule": schedule} if mode == "scheduled"
                           else {"mode": mode}),
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False, "failures": False},
            "presentation": {"renderer": "disc"},
            "activation": {"mode": "manual"},
            "processing": {"operations": [{"op": "extract"}]},
            "schema_version": 1}
        folder = self.root / "presentation" / "magnets"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{mid}.json").write_text(json.dumps(config), encoding="utf-8")
        return config

    def a_conversation(self):
        return self.corpus.entries_of_kind("contribution")[0]["id"]

    def collected_by(self, mid, who=None):
        """One recorded collection of `mid`, so the record names an author for it. The act alone:
        this is the only thing `author_of` reads, and no page is needed for it."""
        from mentis import artifacts
        who = who or self.who
        digest, _ = _held(self.corpus.root, b'{"page": {}}')
        adm = artifacts.admit_generated(self.corpus, digest, 12, source=f"magnet:{mid}",
                                        door="magnet-extract", name=f"{mid}-extract.json",
                                        media_type=X.MEDIA_TYPE, actor=who,
                                        written_by="unattributed-local-request")
        artifacts.record_generated(
            self.corpus, self.cv, adm, act=X.MAGNET_EXTRACTED, actor=who, conversation=None,
            turn=None, because="its Magnet was activated by hand",
            written_by="unattributed-local-request",
            detail={"magnet": mid, "mode": X.MODE, "operation": {"index": 0, "name": None},
                    "definition_sha256": "0" * 64,
                    "page": {"cursor": "f1.1.1.1", "state": "complete", "results": 0,
                             "statuses": {s: 0 for s in X.STATUSES}},
                    "artifact": {"ref": adm, "digest": digest, "size": 12}})
        return who

    def serve(self):
        attrs = {"state": self.state, "boot_secret": None}
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (_Handler,), attrs))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.servers.append(httpd)
        return httpd.server_address[1]

    def stop(self):
        for httpd in self.servers:
            httpd.shutdown()
            httpd.server_close()


def _held(root, raw):
    from mentis.spine import held
    return held.put(root, raw)


@pytest.fixture()
def world(built, tmp_path):
    root = tmp_path / "brain"
    shutil.copytree(built, root)
    w = World(root)
    yield w
    D.stop()
    w.stop()


class Door:
    """A stand-in for the front's activation door: what it was asked, and what it answers."""

    def __init__(self, answer=None, raises=None):
        self.asked = []
        self.answer = answer or (201, {"magnet": MAGNET, "post": "ent-aaaaaaaaaaaa",
                                       "artifact": {"ref": "adm-aaaaaaaaaaaa"}})
        self.raises = raises

    def __call__(self, mid, body):
        self.asked.append((mid, body))
        if self.raises is not None:
            raise self.raises
        return self.answer


# -- the cadence this build already stored --------------------------------------------------------

def test_an_iso_cadence_gives_one_slot_per_period_and_never_a_faster_one(world):
    hour, base = 3600.0, 1_000_000_800.0        # a boundary of both an hour and CADENCE_LEAST_S
    first = D.slot_of("PT1H", base)
    assert first == D.slot_of("PT1H", base + hour - 1)
    assert first != D.slot_of("PT1H", base + hour)
    # NO CONFIGURATION CAN ASK FOR A FASTER PASS THAN CADENCE_LEAST_S.
    short = D.slot_of("PT1S", base)
    assert short == D.slot_of("PT1S", base + D.CADENCE_LEAST_S - 1)
    assert short != D.slot_of("PT1S", base + D.CADENCE_LEAST_S)
    assert short == f"every{int(D.CADENCE_LEAST_S)}s@{int(base // D.CADENCE_LEAST_S)}"


def test_a_cron_cadence_names_the_minute_it_is_in_and_nothing_this_build_cannot_read(world):
    import datetime
    noon = datetime.datetime(2026, 11, 26, 12, 30, tzinfo=datetime.timezone.utc).timestamp()
    assert D.slot_of("0 * * * *", noon) == "cron@2026-11-26T12:00Z"
    assert D.slot_of("*/15 * * * *", noon) == "cron@2026-11-26T12:30Z"
    assert D.slot_of("0 0 * * *", noon) == "cron@2026-11-26T00:00Z"
    for bad in ("", "   ", "not a cadence", "0 0 * *", "0 0 * * * *", "99 * * * *", "P", "PTX"):
        assert D.slot_of(bad, noon) is None


# -- an idle server does nothing at all -----------------------------------------------------------

def test_an_idle_server_with_no_scheduled_magnet_does_nothing_at_all(world):
    world.define(MAGNET, mode="one-time")
    before = world.corpus.advance()
    door = Door()

    def no_sources(*a, **k):                       # nothing acquires, so nothing may be asked
        raise AssertionError("an idle pass touched acquisition")

    out = D.one_pass(world.state, activate=door, sources=type("S", (), {
        "binding_state": no_sources, "plan": no_sources, "sweep": no_sources})())
    assert out["due"] == [] and out["collected"] == [] and out["refreshed"] == []
    assert door.asked == []                        # no activation, no loopback request
    assert world.corpus.advance() == before        # nothing written


def test_a_magnet_with_no_collection_of_its_own_in_the_record_is_not_collected(world):
    world.define(MAGNET)
    door = Door()
    out = D.one_pass(world.state, activate=door, acquire=False)
    assert out["due"] == [] and door.asked == []
    assert D.author_of(world.state, MAGNET) is None


# -- it collects, twice, at its cadence -----------------------------------------------------------

def test_a_scheduled_magnet_collects_unattended_twice_at_its_cadence_and_once_per_slot(world):
    world.define(MAGNET, schedule="PT1H")
    who = world.collected_by(MAGNET)
    door = Door()
    now = 1_000_000_000.0

    first = D.one_pass(world.state, now=now, activate=door, acquire=False)
    assert first["collected"] and first["collected"][0]["magnet"] == MAGNET
    assert door.asked == [(MAGNET, {"author": who, "op": D.op_for(MAGNET, D.slot_of("PT1H", now))})]

    # THE SAME SLOT AGAIN IS NOT A SECOND COLLECTION. The record holds the key, so the pass does
    # not even ask: no timer and no state of the runner's decides this.
    world.collected_by(MAGNET)                    # the first one, as the record would hold it
    _record_outcome(world, who, door.asked[0][1]["op"], MAGNET)
    again = D.one_pass(world.state, now=now + 60, activate=door, acquire=False)
    assert again["due"] == [] and len(door.asked) == 1

    # THE NEXT SLOT IS. One collection per cadence slot, twice over two slots.
    later = now + 3600
    second = D.one_pass(world.state, now=later, activate=door, acquire=False)
    assert second["collected"] and len(door.asked) == 2
    assert door.asked[1][1]["op"] == D.op_for(MAGNET, D.slot_of("PT1H", later))
    assert door.asked[0][1]["op"] != door.asked[1][1]["op"]


def _record_outcome(world, by, op, mid):
    from mentis.conversation import anchors
    with world.corpus.atomic():
        anchors.record_outcome(world.cv, by, op, X.identity(mid), {"magnet": mid},
                               conversation=None)


# -- at most how many -----------------------------------------------------------------------------

def test_a_pass_collects_at_most_MAGNETS_MOST_magnets_and_queues_nothing(world):
    ids = [f"mag-due{i:016d}" for i in range(D.MAGNETS_MOST + 3)]
    for mid in ids:
        world.define(mid)
        world.collected_by(mid)
    door = Door()
    out = D.one_pass(world.state, activate=door, acquire=False)
    assert len(out["due"]) == D.MAGNETS_MOST
    assert len(door.asked) == D.MAGNETS_MOST
    assert out["magnets_most"] == D.MAGNETS_MOST
    # Nothing is kept for the ones left out: the next pass reads the record again.
    assert not hasattr(D, "_QUEUE")


def test_a_pass_refreshes_at_most_COLLECTIONS_MOST_collections_and_each_at_most_once(world):
    # MAGNETS_MOST Magnets, the last of them over three collections, so a pass has more bound
    # collections in front of it than COLLECTIONS_MOST allows.
    ids = [f"mag-acq{i:016d}" for i in range(D.MAGNETS_MOST)]
    for i, mid in enumerate(ids):
        world.define(mid, collection=([f"ent-col{i:09d}{n}" for n in range(3)]
                                      if i == len(ids) - 1 else f"ent-col{i:09d}0"))
        world.collected_by(mid)
    calls = {"binding_state": [], "plan": [], "sweep": []}

    class Fake:
        def binding_state(self, collection):
            calls["binding_state"].append(collection)
            return {"bound": True}

        def plan(self, collection, **kw):
            calls["plan"].append(collection)
            return {"confirm": {"plan": f"p-{collection}", "acknowledge_binding_change": False}}

        def sweep(self, collection, plan_id, **kw):
            calls["sweep"].append((collection, plan_id, kw.get("written_by"), kw.get("actor")))
            return {"act": f"act-{collection}"}

    out = D.one_pass(world.state, activate=Door(), sources=Fake())
    refreshed = [r for r in out["refreshed"] if r["refreshed"]]
    assert len(refreshed) == D.COLLECTIONS_MOST
    # AT MOST ONE FETCH PER COLLECTION PER PASS: one plan and the one sweep that confirms it.
    assert len(calls["plan"]) == D.COLLECTIONS_MOST == len(calls["sweep"])
    assert len(set(calls["plan"])) == len(calls["plan"]) == D.REFRESH_PER_COLLECTION_MOST * D.COLLECTIONS_MOST
    # NO WORKER CREDENTIAL, and the author is the Magnet's own, never a new identity.
    assert {c[2] for c in calls["sweep"]} == {D.DUE_WRITER}
    assert {c[3] for c in calls["sweep"]} == {world.who}
    left = [r for r in out["refreshed"] if not r["refreshed"]]
    assert left and all("refreshed" in r["why"] for r in left)


# -- what stays the owner's -----------------------------------------------------------------------

@pytest.mark.parametrize("state,plan,why", [
    ({"bound": False}, None, "not bound"),
    ({"bound": True}, {"confirm": {"plan": "p", "acknowledge_binding_change": True}}, "binding"),
    ({"bound": True}, {"confirm": {}}, "cannot be confirmed"),
])
def test_an_unattended_refresh_decides_nothing_the_owner_decides(world, state, plan, why):
    class Fake:
        swept = False

        def binding_state(self, collection):
            return state

        def plan(self, collection, **kw):
            if plan is None:
                raise AssertionError("an unbound collection was planned")
            return plan

        def sweep(self, collection, plan_id, **kw):
            Fake.swept = True
            raise AssertionError("an unattended refresh swept what the owner decides")

    got = D.refresh(world.state, "ent-col000000001", by=world.who, sources=Fake())
    assert got["refreshed"] is False and why in got["why"]
    assert Fake.swept is False


def test_an_unattended_refresh_that_raises_changes_nothing_and_is_not_retried(world):
    tries = []

    class Fake:
        def binding_state(self, collection):
            tries.append(collection)
            raise RuntimeError("the connector is not available yet")

        def plan(self, collection, **kw):
            raise AssertionError("planned after the binding could not be read")

        def sweep(self, *a, **k):
            raise AssertionError("swept after the binding could not be read")

    got = D.refresh(world.state, "ent-col000000001", by=world.who, sources=Fake())
    assert got["refreshed"] is False and "not available yet" in got["why"]
    assert len(tries) == 1                      # once, never again inside the pass


# -- a failed pass --------------------------------------------------------------------------------

def test_a_failed_activation_changes_nothing_and_is_not_retried_in_the_pass(world):
    world.define(MAGNET)
    world.collected_by(MAGNET)
    before = world.corpus.advance()
    door = Door(raises=OSError("the front is not answering"))
    out = D.one_pass(world.state, activate=door, acquire=False)
    assert out["collected"] == [] and len(out["not_collected"]) == 1
    assert "the front is not answering" in out["not_collected"][0]["why"]
    assert len(door.asked) == 1                 # ONE attempt, never a second
    assert world.corpus.advance() == before     # and nothing written


def test_a_refused_activation_is_said_and_not_retried(world):
    world.define(MAGNET)
    world.collected_by(MAGNET)
    door = Door(answer=(503, X.processor_unavailable(MAGNET)))
    out = D.one_pass(world.state, activate=door, acquire=False)
    assert out["collected"] == [] and out["not_collected"][0]["status"] == 503
    assert len(door.asked) == 1


def test_a_pass_that_cannot_reach_its_own_front_asks_nothing_anywhere(world):
    world.define(MAGNET)
    world.collected_by(MAGNET)
    world.state.answers_at = "http://example.invalid:80"
    out = D.one_pass(world.state, acquire=False)
    assert out["collected"] == [] and len(out["not_collected"]) == 1
    assert "loopback only" in out["not_collected"][0]["why"]


# -- what starts it, and when it stops ------------------------------------------------------------

def test_the_keeper_is_started_once_per_server_and_stops_when_the_server_stops(world):
    world.define(MAGNET)
    world.collected_by(MAGNET)
    door = Door()
    one = D.start(world.state, every_s=0.02, activate=door)
    two = D.start(world.state, every_s=0.02, activate=door)
    assert one is two                            # ONE keeper per served Brain, one thread
    deadline = time.time() + 10
    while one.passes < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert one.passes >= 2 and one.running
    D.stop(world.state)
    assert not one.running                       # IT STOPS WHEN THE SERVER STOPS
    was = one.passes
    time.sleep(0.1)
    assert one.passes == was                     # and no pass happens after it stopped
    assert D.start(world.state, every_s=0.02, activate=door) is not one


def test_the_keepers_interval_is_the_named_bound_and_a_failing_pass_keeps_its_interval(world):
    assert D.Keeper(world.state).every_s == D.PASS_EVERY_S == 300.0
    assert D.PASS_EVERY_S >= D.CADENCE_LEAST_S
    broke = []

    def explode(st, **kw):
        broke.append(1)
        raise RuntimeError("the record could not be read")

    keeper = D.Keeper(world.state, every_s=0.02)
    import mentis.magnet.due as module
    was, module.one_pass = module.one_pass, explode
    try:
        keeper.start()
        deadline = time.time() + 10
        while len(broke) < 2 and time.time() < deadline:
            time.sleep(0.01)
    finally:
        keeper.stop()
        module.one_pass = was
    assert len(broke) >= 2 and keeper.failed and "could not be read" in keeper.failed


# -- the real door, with no credential at all -----------------------------------------------------

def test_the_unattended_request_presents_no_credential_and_is_refused_where_the_owner_logs_in(world):
    """THE OWNER'S AUTHENTICATION IS NOT WEAKENED FOR THE SCHEDULE. On a real server, with the
    suite's passphrase installation, the unattended request -- which carries no cookie, no bearer
    session, no boot secret and no worker grant -- is refused by the same owner gate a press
    passes, and nothing is recorded. Nothing here works around it."""
    world.define(MAGNET)
    world.collected_by(MAGNET)
    port = world.serve()
    world.state.answers_at = f"http://127.0.0.1:{port}"
    before = world.corpus.advance()
    out = D.one_pass(world.state, acquire=False)
    assert out["due"] == [MAGNET] and out["collected"] == []
    assert out["not_collected"][0]["status"] == 401
    assert world.corpus.advance() == before


def test_the_unattended_request_reaches_the_real_activation_door_where_the_owner_trusts_local(
        world, monkeypatch):
    """The one path, on a real server, where the installation trusts its local owner (the owner's
    own decision, 2026-11-11): the public activation door, the public body of `author` and `op`,
    and still no credential. Python alone has no processor by design, so the honest answer is
    `processor-unavailable` and nothing is recorded."""
    from mentis import owner_auth
    monkeypatch.setattr(owner_auth.Credential, "trusted_local", lambda self: True)
    world.define(MAGNET)
    who = world.collected_by(MAGNET)
    port = world.serve()
    world.state.answers_at = f"http://127.0.0.1:{port}"
    before = world.corpus.advance()
    out = D.one_pass(world.state, acquire=False)
    assert out["due"] == [MAGNET] and out["collected"] == []
    assert out["not_collected"][0]["status"] == 503
    assert "no processor" in out["not_collected"][0]["why"]
    assert world.corpus.advance() == before
    assert who == world.who


def test_a_scheduled_definition_is_run_by_the_one_path_and_continuous_is_still_refused(world):
    """`collection.mode` is interpreted, not refused -- and only `scheduled` is."""
    assert X.COLLECTABLE_MODES == ("one-time", "scheduled")
    for mode, code in (("one-time", None), ("scheduled", None),
                       ("continuous", "collection-not-supported"),
                       ("paused", "collection-not-supported")):
        config = world.define(MAGNET, mode=mode)
        value = X.checked(MAGNET, config)
        assert X._cannot_run_code(value) == code, mode


def test_the_record_says_a_due_collection_was_due_and_a_press_was_a_press(world):
    """The op key decides words and nothing else. Nothing about authority is read from it."""
    assert D.DUE_OP_PREFIX == X.DUE_OP_PREFIX == "magnet-due:"
    assert X.unattended(D.op_for(MAGNET, "every3600s@1"))
    assert "due on the schedule" in X._because(D.op_for(MAGNET, "every3600s@1"))
    assert not X.unattended("collect-now")
    assert X._because("collect-now") == "its Magnet was activated by hand"
