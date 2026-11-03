"""R4.2's routes over HTTP: Python's exact bytes from the front, or a forward, for the shapes the review
found wrong on real data, and what each route does as the snapshot goes stale, is lost and recovers.

Real Python runs in this process, so `begin_execution` is the real one and its snapshot producers are
the real ones. `Proxy` stands between the front and Python, carries everything and counts what isn't a
poll, so a route's own answer is told from a forward. `docs/rust/R4-R6-live-fields.md`, "Stalled-Python
acceptance", is what these rows pay; `tools/r4_2/compare.py` is the same comparison on a real Brain.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import threading
import time

import pytest

from tests.front.pair import (CLIENT, FRONT_503, SPARE_PORTS, Pair, _template, ask,
                              conversation_named, post_json, rows)
from tests.front.test_live_snapshot import (IDLE_S, PRIVATE_PORT, _clean_env, _front_binary, is_fresh,
                                            is_stale, is_unavailable, until)
from tools.r4_2.common import Proxy, get

SECRET = "r4-2-views"
PY_PORT, PROXY_PORT, FRONT_PORT, PAIR_PROXY_PORT = SPARE_PORTS[2:6]
FRESH_AFTER_WRITE_S = 1.2


def _say(cv, where, who, words, **kw):
    return cv.say(where, who, [{"type": "text", "text": words}], **kw)


def build(st) -> dict:
    """Each real shape, by Python's own commands."""
    from mentis.conversation import anchors, versions

    cv = st.cv
    owner = cv.resolve_participant("@r1-owner")
    agent = cv.resolve_participant("@r1-agent")
    other = cv.resolve_participant("@r4-2-other")
    home = cv.open_conversation("R4.2 shapes", about="", attributed_to=owner)
    away = cv.open_conversation("R4.2 elsewhere", about="", attributed_to=owner)
    ids: dict = {"owner": owner, "agent": agent, "home": home, "other": other}

    def ask_of(words, of=agent, by=owner, **kw):
        turn = _say(cv, home, by, words)
        return turn, cv.expect(turn, of=of, kind=kw.pop("kind", "result"), by=by, **kw)

    ids["plain"] = _say(cv, home, owner, "nothing owed")
    ids["written_by"] = _say(cv, home, owner, "written by a run", written_by="claude/shape")
    ids["agent_work"] = _say(cv, home, agent, "an agent's note", written_by="codex/shape")
    ids["addressed"] = _say(cv, home, owner, "to them, nothing asked", addressed_to=[agent])
    ids["addressed_two"] = _say(cv, home, owner, "two", addressed_to=[other, agent])
    ids["open_ask"], ids["open_ask_e"] = ask_of("asked and open")

    # An answered ask, whose reply `answered_by` names, with the alternative it chose.
    ids["answered"], ids["answered_e"] = ask_of("asked and answered")
    ids["answer"] = _say(cv, home, agent, "  the answer  ", replies_to=ids["answered"])
    cv.record_act(actor=agent, act="turn-said", conversation=home, turn=ids["answer"],
                  detail={"chose": "the first"})

    # A decision asked under work, which answering would continue.
    ids["request"], ids["request_e"] = ask_of("do the work", kind="result")
    ids["decision_post"] = _say(cv, home, agent, "a decision first", replies_to=ids["request"])
    ids["continues_e"] = cv.expect(ids["decision_post"], of=owner, kind="decision", by=agent,
                                   caused_by=ids["request_e"])

    # A decision form with two questions, one answered, on a post by the agent; and one still open
    # on the owner's post.
    def form(on, words):
        made = cv.record_act(actor=agent, act="decision-form", conversation=home, turn=on,
                             caused_by=ids["request_e"], because="the work needs it",
                             detail={"questions": len(words)})
        return made, [cv.expect(None, of=owner, kind="decision", by=agent,
                                caused_by=ids["request_e"], conversation=home,
                                detail={"options": [{"label": "yes"}, {"label": "no"}],
                                        "form": made, "index": i, "question": q,
                                        "requester": owner})
                      for i, q in enumerate(words)]

    ids["form_post"] = _say(cv, home, agent, "questions", addressed_to=[owner])
    ids["form"], (ids["q1"], ids["q2"]) = form(ids["form_post"], ["First?", "Second?"])
    ids["form_answer"] = _say(cv, home, owner, "yes", replies_to=ids["form_post"])
    cv.record_act(actor=owner, act="decision-answered", conversation=home, turn=ids["form_answer"],
                  caused_by=ids["q1"], detail={"reply": ids["form_answer"], "option": 0,
                                               "label": "yes"})
    ids["open_form_post"] = _say(cv, home, owner, "my own post carries a form")
    ids["open_form"], (ids["open_q"],) = form(ids["open_form_post"], ["Third?"])

    # A line: the root, its later version and a deleted one.
    ids["edited"] = _say(cv, home, owner, "before")
    versions.edit(cv, ids["edited"], by=owner, text="after", because="a slip")
    ids["later_version"] = st.corpus.links(relation=versions.supersedes_relation(st.corpus),
                                           to=ids["edited"])[0]["link"]["from"]
    ids["deleted"] = _say(cv, home, owner, "gone")
    versions.delete(cv, ids["deleted"], by=owner, because="review")

    # What only Python projects.
    ids["anchored"] = _say(cv, home, owner, "an anchor on this passage of plain text")
    anchors.create_anchor(cv, {"version": ids["anchored"], "type": "text-range", "part": 0,
                               "start": 3, "end": 9, "unit": "codepoint",
                               "expected_excerpt": "anchor"}, by=owner)
    ids["linked"] = _say(cv, home, owner, "linked elsewhere")
    cv.link_into(ids["linked"], away, by=owner)
    topic = cv.open_topic(home, "R4.2 topic", attributed_to=owner)
    ids["filed"] = _say(cv, home, owner, "filed")
    cv.assign_topic(ids["filed"], topic, attributed_to=owner)
    ids["addressed_later"] = _say(cv, home, owner, "addressed afterwards")
    cv.address_turn(ids["addressed_later"], agent, by=owner, because="they should see it")

    # A thread: a reply's reply names the root, not its parent.
    ids["root"] = _say(cv, home, owner, "a root")
    ids["reply"] = _say(cv, home, agent, "a reply", replies_to=ids["root"])
    ids["deep_reply"] = _say(cv, home, owner, "a reply to the reply", replies_to=ids["reply"])

    ids["batch"] = [_say(cv, home, owner, f"batched {n}", written_by="claude/batch")
                    for n in range(64)]

    # What intake refuses. `resumable` must hold only the last, until something is deleted.
    def unresolved(words, actor):
        turn, made = ask_of(words, of=None)
        cv.record_act(actor=actor, act="assignment-unresolved", conversation=home, turn=turn,
                      caused_by=made, because="nobody designated")
        return turn, made

    ids["other_actor_t"], ids["other_actor_e"] = unresolved("another's act", agent)
    ids["resumable_t"], ids["resumable_e"] = unresolved("resumable", owner)
    ids["live_only_t"], ids["live_only_e"] = unresolved("overlay only", owner)

    # A durably open run, for the second reference; and a carrier's ask for the fallback handle.
    ids["durable_t"], ids["durable_e"] = ask_of("durably open")
    cv.record_act(actor=owner, act="execution-started", conversation=home, turn=ids["durable_t"],
                  caused_by=ids["durable_e"], execution="instance-durable", runtime="codex")
    ids["fallback_t"], ids["fallback_e"] = ask_of("for the carrier", of=other)
    return ids


class World:
    def __init__(self, brain, workspace):
        from mentis.web import _Handler, _Server, _State
        self.st = _State(str(brain), str(workspace))
        self.brain = brain
        self.ids = build(self.st)
        _Handler.boot_secret = SECRET
        _Handler.state = self.st
        self.server = _Server(("127.0.0.1", PY_PORT), _Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.proxy = Proxy(PROXY_PORT, PY_PORT)
        self.proxy.forward = True
        words = _template()
        self.log = open(brain.parent / "front.log", "ab")  # noqa: SIM115  for the process's life
        self.front = subprocess.Popen(
            [_front_binary(words), str(brain), "--host", "127.0.0.1", "--port", str(FRONT_PORT),
             "--upstream", f"http://127.0.0.1:{PROXY_PORT}", "--dist",
             words[words.index("--dist") + 1]],
            env={**_clean_env(), "MENTIS_BOOT_SECRET": SECRET},
            stdout=self.log, stderr=subprocess.STDOUT)
        self.beating = True
        self.fresh_key = itertools.count(1)
        deadline = time.monotonic() + 30
        while True:
            try:
                get(FRONT_PORT, "/api/pulse", 5)
                break
            except OSError:
                assert time.monotonic() < deadline, "the front didn't start"
                time.sleep(0.05)
        threading.Thread(target=self._pulse, daemon=True).start()
        self.fresh()

    def _pulse(self):
        while self.front.poll() is None:
            if self.beating:
                try:
                    get(FRONT_PORT, "/api/pulse", 5)
                except OSError:
                    pass
            time.sleep(0.3)

    def fresh(self, settle=FRESH_AFTER_WRITE_S) -> None:
        """A poll that began after what was just written: the marker is at or past it."""
        until(FRONT_PORT, is_fresh, 20)
        time.sleep(settle)

    def stop(self):
        self.front.kill()
        self.front.wait(20)
        self.log.close()
        self.proxy.srv.shutdown()
        self.server.shutdown()
        self.server.server_close()

    # -- what a read did ------------------------------------------------------------------------

    def front_says(self, target) -> tuple:
        before = self.proxy.forwarded
        got = get(FRONT_PORT, target)
        return (got[0], got[3], got[1]), self.proxy.forwarded - before

    def python_says(self, target) -> tuple:
        got = get(PY_PORT, target)
        return (got[0], got[3], got[1])

    def fresh_target(self, target) -> str:
        """Python's decisions memo is keyed without `active_executions`, so each read gets its own
        key and the comparison is with a fresh answer, as that known staleness isn't the front's."""
        if target.startswith("/fluid/api/decisions"):
            mark = "&" if "?" in target else "?"
            return f"{target}{mark}n={next(self.fresh_key)}"
        return target

    def answered(self, target) -> bytes:
        """Rust's own answer, byte for byte Python's."""
        target = self.fresh_target(target)
        said, forwards = self.front_says(target)
        assert forwards == 0, f"{target} forwarded"
        assert said == self.python_says(target), target
        return said[2]

    def forwarded(self, target) -> bytes:
        """Python's answer, through the front."""
        target = self.fresh_target(target)
        said, forwards = self.front_says(target)
        assert forwards == 1, f"{target} answered by Rust: {said[2][:300]!r}"
        assert said == self.python_says(target), target
        return said[2]

    def targets(self) -> dict:
        i = self.ids
        return {"turn": f"/api/turns/{i['open_ask']}", "turn-plain": f"/api/turns/{i['plain']}",
                "turns": f"/api/turns?ids={i['open_ask']},{i['plain']}",
                "thread": f"/api/conversations/{i['home']}/thread/{i['open_ask']}",
                "post": f"/fluid/api/decisions?post={i['open_ask']}",
                "ids": f"/fluid/api/decisions?ids={i['open_ask_e']}", "intake": "/api/intake"}

    def durable_siblings(self) -> list:
        i = self.ids
        return ["/api/personas", f"/api/conversations/{i['home']}?fields=name,participants"]

    def each_live_route_forwards(self) -> None:
        for target in self.targets().values():
            target = self.fresh_target(target)
            _, forwards = self.front_says(target)
            assert forwards == 1, target

    def each_durable_sibling_answers(self) -> None:
        for target in self.durable_siblings():
            said, forwards = self.front_says(target)
            assert forwards == 0 and said[0] == 200, target

    def exact_again(self) -> None:
        self.fresh()
        for target in self.targets().values():
            self.answered(target)
        for target in self.durable_siblings():
            self.answered(target)


@pytest.fixture(scope="module")
def world(brain_seed, tmp_path_factory):
    where = tmp_path_factory.mktemp("r42")
    shutil.copytree(brain_seed, where / "brain")
    made = World(where / "brain", where / "ws")
    yield made
    made.stop()


# -- each defect, with the shape that showed it -----------------------------------------------------


def test_written_by_and_agent_work_are_python_s(world):
    i = world.ids
    wrote = json.loads(world.answered(f"/api/turns/{i['written_by']}"))
    assert wrote["versions"]["versions"][0]["written_by"] == "claude/shape"
    note = json.loads(world.answered(f"/api/turns/{i['agent_work']}"))
    assert note["agent_work"]["kind"] == "follow-up"


def test_addressees_come_from_who_the_turn_was_addressed_to(world):
    i = world.ids
    one = json.loads(world.answered(f"/api/turns/{i['addressed']}"))
    assert [row["participant"] for row in one["addressees"]] == [i["agent"]]
    two = json.loads(world.answered(f"/api/turns/{i['addressed_two']}"))
    assert [row["participant"] for row in two["addressees"]] == [i["other"], i["agent"]]
    asked = json.loads(world.answered(f"/api/turns/{i['open_ask']}"))
    assert asked["addressees"] == [] and asked["expectations"]
    world.answered(f"/api/conversations/{i['home']}/thread/{i['addressed']}")


def test_an_answered_ask_names_its_reply_on_ids_and_forwards_on_the_turn(world):
    i = world.ids
    got = json.loads(world.answered(f"/fluid/api/decisions?ids={i['answered_e']}"))
    answered_by = got["expectations"][0]["answered_by"]
    assert answered_by["turn"] == i["answer"]
    assert answered_by["said"] == "the answer" and answered_by["chose"] == "the first"
    world.forwarded(f"/api/turns/{i['answered']}")
    world.forwarded(f"/fluid/api/decisions?post={i['answered']}")


def test_continues_work_is_false_by_proof_and_otherwise_python_s(world):
    i = world.ids
    got = json.loads(world.forwarded(f"/fluid/api/decisions?ids={i['continues_e']}"))
    assert got["expectations"][0]["continues_work"] is True
    got = json.loads(world.answered(f"/fluid/api/decisions?ids={i['open_ask_e']}"))
    assert got["expectations"][0]["continues_work"] is False


def test_one_question_brings_its_whole_form(world):
    i = world.ids
    for asked in (i["q1"], i["q2"], f"{i['q2']},{i['q1']},{i['open_ask_e']}"):
        target = f"/fluid/api/decisions?ids={asked}"
        got = json.loads(world.answered(target))
        assert got["decision_forms"][0]["form"] == i["form"]
        assert len(got["decision_forms"][0]["questions"]) == 2
        assert "cursor" not in got["decision_forms"][0]
        assert [e["id"] for e in got["expectations"]][:2] == [i["q1"], i["q2"]]
        assert got["expectations"][0]["answered_by"]["turn"] == i["form_answer"]


def test_a_form_on_a_turn_is_as_decision_form_gives_it(world):
    i = world.ids
    got = json.loads(world.answered(f"/api/turns/{i['open_form_post']}"))
    assert "cursor" not in got["decision_forms"][0]
    assert [e["id"] for e in got["expectations"]] == [i["open_q"]]


@pytest.mark.parametrize("shape", ["edited", "later_version", "deleted", "anchored", "linked", "filed",
                                   "addressed_later", "reply"])
def test_what_only_python_projects_forwards(world, shape):
    target = world.ids[shape]
    world.forwarded(f"/api/turns/{target}")
    world.forwarded(f"/fluid/api/decisions?post={target}")


def test_an_edited_turn_s_later_version_shows_its_whole_line(world):
    i = world.ids
    got = json.loads(world.forwarded(f"/api/turns/{i['later_version']}"))
    assert [v["entry"] for v in got["versions"]["versions"]] == [i["edited"], i["later_version"]]


def test_a_reply_s_thread_names_the_root(world):
    i = world.ids
    for reply in (i["reply"], i["deep_reply"]):
        got = json.loads(world.answered(f"/api/conversations/{i['home']}/thread/{reply}"))
        assert got == {
            "error": f"{reply} is a reply, not a thread root; its thread is {i['root']}",
            "thread": reply, "root": i["root"]}
    world.forwarded(f"/api/conversations/{i['home']}/thread/{i['root']}")
    world.answered(f"/api/conversations/{i['home']}/thread/{i['plain']}")
    world.answered(f"/api/conversations/{i['home']}/thread/nope")


def test_a_large_batch_is_python_s_bytes(world):
    i = world.ids
    got = json.loads(world.answered("/api/turns?ids=" + ",".join(i["batch"])))
    assert len(got["turns"]) == 64
    assert got["turns"][0]["turn"]["written_by"] == "claude/batch"
    # One id Python has to say something about, and the whole batch is Python's.
    world.forwarded(f"/api/turns?ids={i['batch'][0]},{i['reply']}")


def test_refusals_and_edges_are_python_s_words(world):
    i = world.ids
    home = i["home"]
    for target in (
            f"/api/conversations/{home}?fields=bogus", f"/api/conversations/{home}?fields=name,bogus",
            f"/api/conversations/{home}?fields=name%1C", "/api/conversations/nope?fields=name",
            "/fluid/api/decisions?post=nope", f"/fluid/api/decisions?post={i['owner']}",
            "/fluid/api/decisions?ids=,", "/fluid/api/decisions", "/fluid/api/decisions?ids=nope",
            f"/fluid/api/decisions?ids=%1C{i['open_ask_e']}%1C", "/api/turns", "/api/turns?ids=%20,%20",
            "/api/turns?ids=a/b", "/api/turns?ids=" + ",".join(f"x{n}" for n in range(65)),
            f"/api/turns?ids=%1C{i['plain']}%1C", f"/api/turns?ids={i['plain']}&ids={i['written_by']}",
            f"/api/turns?ids={i['plain']},nope"):
        world.answered(target)
    world.forwarded(f"/api/turns?ids={i['owner']}")
    world.forwarded(f"/api/turns?ids={i['plain']},{i['owner']}")
    world.forwarded(f"/api/turns/{i['plain'].replace('-', '%2D')}")


def test_a_held_avatar_reaches_none_of_these_routes(world):
    """The reconcile row's held-avatar cost: `_avatar` is `/api/participants`' and the participant
    page's, so a pictured Participant changes nothing here and no answer holds a picture."""
    from mentis import artifacts
    i = world.ids
    st = world.st
    before = {target: world.answered(target) for target in (
        f"/api/turns/{i['addressed']}", f"/api/conversations/{i['home']}?fields=participants",
        f"/fluid/api/decisions?ids={i['open_ask_e']}", "/api/intake")}
    with st.corpus.atomic():
        picture = artifacts.hold(st.corpus, st.cv, b"\x89PNG\r\n\x1a\n" + b"\0" * 32,
                                 act=artifacts.SUBMITTED, actor=i["owner"], source="avatar:r4-2",
                                 door="human-ingress", claimed_name="a.png",
                                 claimed_media_type="image/png",
                                 because="a picture")["admission"]
        st.cv.set_avatar(i["agent"], picture, by=i["owner"])
    assert st.cv.avatar_of(i["agent"]) == picture
    world.fresh()
    for target, was in before.items():
        now = world.answered(target)
        assert b"avatar" not in now and picture.encode() not in now, target
        if "decisions" not in target:  # Its `cursor` moves with the record.
            assert now == was, target


# -- the snapshot, route by route --------------------------------------------------------------------


def test_fresh_every_route_is_rust_s_and_python_s_bytes(world):
    world.exact_again()


def test_the_durable_second_reference_changes_nothing(world):
    i = world.ids
    run = world.st.cv.begin_execution(participant=i["agent"], conversation=i["home"],
                                      for_expectation=i["durable_e"], runtime="codex")
    try:
        world.fresh()
        raw = world.st.cv.expectation_state(i["durable_e"])["live_execution"]
        assert len(raw) == 2, raw
        got = json.loads(world.answered(f"/api/turns/{i['durable_t']}"))
        assert got["expectations"][0]["live_execution"] is True
        assert b"instance-durable" not in world.answered(f"/fluid/api/decisions?ids={i['durable_e']}")
        # Behind the marker, the second reference still changes nothing, so no forward.
        world.proxy.hold()
        time.sleep(0.15)
        world.st.cv.record_act(actor=i["owner"], act="turn-said", conversation=i["home"],
                               turn=i["plain"], detail={"note": "moves the record"})
        said, forwards = world.front_says(f"/api/turns/{i['durable_t']}")
        assert forwards == 0 and json.loads(said[2])["expectations"][0]["live_execution"] is True
    finally:
        world.proxy.release()
        world.st.cv.end_execution(run.reference)
    world.fresh()


def test_intake_s_liveness_branch(world):
    i = world.ids
    world.fresh()
    got = json.loads(world.answered("/api/intake"))
    assert i["resumable_e"] in got["resumable"] and i["live_only_e"] in got["resumable"]
    assert i["other_actor_e"] not in got["resumable"]
    run = world.st.cv.begin_execution(participant=i["agent"], conversation=i["home"],
                                      for_expectation=i["live_only_e"], runtime="codex")
    try:
        world.fresh()
        got = json.loads(world.answered("/api/intake"))
        assert i["live_only_e"] not in got["resumable"]
        got = json.loads(world.answered(f"/api/turns/{i['live_only_t']}"))
        assert got["expectations"][0]["live_execution"] is True
        # Behind the marker, this one ref changes both answers, and it can't be spoken for.
        world.proxy.hold()
        time.sleep(0.15)
        world.st.cv.record_act(actor=i["owner"], act="turn-said", conversation=i["home"],
                               turn=i["plain"], detail={"note": "moves the record"})
        _, forwards = world.front_says(f"/api/turns/{i['live_only_t']}")
        assert forwards == 1
        _, forwards = world.front_says("/api/intake")
        assert forwards == 1
    finally:
        world.proxy.release()
        world.st.cv.end_execution(run.reference)
    world.exact_again()


def test_the_fallback_handle_forwards_behind_the_marker(world):
    i = world.ids
    run = world.st.cv.begin_execution(participant=i["other"], conversation=i["home"], runtime="codex")
    try:
        world.fresh()
        got = json.loads(world.answered(f"/api/turns/{i['fallback_t']}"))
        assert got["expectations"][0]["live_execution"] is True
        world.proxy.hold()
        time.sleep(0.15)
        world.st.cv.record_act(actor=i["owner"], act="turn-said", conversation=i["home"],
                               turn=i["plain"], detail={"note": "moves the record"})
        _, forwards = world.front_says(f"/api/turns/{i['fallback_t']}")
        assert forwards == 1
    finally:
        world.proxy.release()
        world.st.cv.end_execution(run.reference)
    world.exact_again()


def test_stale_forwards_and_durable_siblings_answer(world):
    world.fresh()
    world.proxy.hold()
    try:
        until(FRONT_PORT, is_stale, 6)
        world.each_live_route_forwards()
        world.each_durable_sibling_answers()
    finally:
        world.proxy.release()
    world.exact_again()


def test_resume_after_idle_forwards_until_a_good_poll(world):
    world.fresh()
    world.beating = False
    try:
        time.sleep(IDLE_S)
        world.each_live_route_forwards()
        world.each_durable_sibling_answers()
    finally:
        world.beating = True
    world.exact_again()


@pytest.mark.parametrize("change", [
    pytest.param(lambda envelope: envelope.update(boot_id="another"), id="changed-boot"),
    pytest.param(lambda envelope: envelope.update(generation=1), id="lower-generation"),
    pytest.param(lambda envelope: envelope.update(schema=99), id="unknown-schema")])
def test_a_discarded_snapshot_forwards(world, change):
    # Python's own generation may be its lowest, so the held one is put above what comes next.
    world.proxy.edit = lambda envelope: envelope.update(generation=1000)
    time.sleep(FRESH_AFTER_WRITE_S)
    world.fresh()
    polled = world.proxy.polls
    world.proxy.edit_once(change)
    try:
        until(FRONT_PORT, is_unavailable, 3)
        assert world.proxy.polls > polled
        world.each_live_route_forwards()
        world.each_durable_sibling_answers()
    finally:
        world.proxy.edit = None
        world.proxy.release()
    world.exact_again()


def _without(field):
    return lambda envelope: envelope["fields"].pop(field, None)


def test_a_missing_active_executions_forwards_what_reads_it(world):
    i = world.ids
    world.fresh()
    world.proxy.edit = _without("active_executions")
    try:
        time.sleep(FRESH_AFTER_WRITE_S)
        until(FRONT_PORT, is_fresh, 5)
        for target in (f"/api/turns/{i['open_ask']}", f"/fluid/api/decisions?ids={i['open_ask_e']}",
                       f"/api/conversations/{i['home']}/thread/{i['open_ask']}", "/api/intake"):
            target = world.fresh_target(target)
            _, forwards = world.front_says(target)
            assert forwards == 1, target
        # Nothing asked, so nothing to read it for.
        world.answered(f"/api/turns/{i['plain']}")
        world.each_durable_sibling_answers()
    finally:
        world.proxy.edit = None
    world.exact_again()


def test_run_observations_is_not_a_field_these_routes_need(world):
    world.fresh()
    world.proxy.edit = _without("run_observations")
    try:
        time.sleep(FRESH_AFTER_WRITE_S)
        until(FRONT_PORT, is_fresh, 5)
        for target in world.targets().values():
            world.answered(target)
    finally:
        world.proxy.edit = None
    world.fresh()


# -- last, because a deleted Turn sends intake to Python from here on -------------------------------


def test_intake_refuses_what_python_refuses(world):
    from mentis.conversation.versions import delete
    i = world.ids
    world.fresh()
    delete(world.st.cv, i["resumable_t"], by=i["owner"], because="review")
    world.fresh()
    got = json.loads(world.forwarded("/api/intake"))
    assert i["resumable_e"] not in got["resumable"]
    assert i["other_actor_e"] not in got["resumable"]


# -- with the whole of Python, over the launcher ---------------------------------------------------


@pytest.fixture
def seeded(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    return copy


def _posted(pair) -> tuple[str, str]:
    conversation = conversation_named(pair.brain, "R1 known conversation")
    owner = rows(pair.brain, "SELECT id FROM entry WHERE def_name='participant' "
                             "AND json_extract(body,'$.alias')='@r1-owner'")[0][0]
    got = post_json(pair.port, "/fluid/api/posts", {"conversation": conversation, "author": owner,
                                                    "text": "an owned shape"}, CLIENT)
    assert got.status == 200, got
    turn = rows(pair.brain, "SELECT id FROM entry WHERE def_name='contribution' "
                            "ORDER BY seq DESC LIMIT 1")[0][0]
    return conversation, turn


def _front_only(port, target) -> tuple:
    got = ask(port, "GET", target, headers=CLIENT)
    return got.status, got.header("Content-Type"), got.body


def test_past_ten_seconds_the_live_routes_forward_and_a_good_poll_restores_them(seeded):
    proxy = Proxy(PAIR_PROXY_PORT, PRIVATE_PORT)
    proxy.forward = True
    try:
        with Pair(seeded, upstream=f"http://127.0.0.1:{PAIR_PROXY_PORT}") as pair:
            conversation, turn = _posted(pair)
            live = [f"/api/turns/{turn}", f"/api/turns?ids={turn}",
                    f"/api/conversations/{conversation}/thread/{turn}", "/api/intake"]
            durable = ["/api/personas", f"/api/conversations/{conversation}?fields=name,topics"]

            def exact():
                until(pair.port, is_fresh, 15)
                time.sleep(FRESH_AFTER_WRITE_S)
                for target in live + durable:
                    before = proxy.forwarded
                    said = _front_only(pair.port, target)
                    assert proxy.forwarded == before, f"{target} forwarded"
                    assert said == _front_only(pair.private_port, target), target

            exact()
            proxy.hold()
            try:
                until(pair.port, is_unavailable, 14)
                for target in live:
                    before = proxy.forwarded
                    assert _front_only(pair.port, target)[0] == 200, target
                    assert proxy.forwarded == before + 1, f"{target} answered with no snapshot"
                for target in durable:
                    before = proxy.forwarded
                    said = _front_only(pair.port, target)
                    assert proxy.forwarded == before, f"{target} forwarded, though durable"
                    assert said == _front_only(pair.private_port, target), target
            finally:
                proxy.release()
            exact()
    finally:
        proxy.srv.shutdown()


def test_python_gone_live_routes_say_so_durable_ones_answer_and_a_new_python_restores(seeded):
    with Pair(seeded) as pair:
        conversation, turn = _posted(pair)
        live = [f"/api/turns/{turn}", f"/api/turns?ids={turn}",
                f"/api/conversations/{conversation}/thread/{turn}", "/api/intake",
                f"/fluid/api/decisions?post={turn}"]
        durable = ["/api/personas", f"/api/conversations/{conversation}?fields=name,topics"]
        until(pair.port, is_fresh, 15)
        time.sleep(FRESH_AFTER_WRITE_S)
        before = {target: _front_only(pair.port, target) for target in durable}
        pair.kill_python()
        until(pair.port, is_unavailable, 14)
        for target in live:
            got = ask(pair.port, "GET", target, headers=CLIENT)
            assert got.status == 503, (target, got)
            assert got.json == {"error": FRONT_503["Python-unreached"]}, target
        for target in durable:
            assert _front_only(pair.port, target) == before[target], target

        pair.restart_python()
        until(pair.port, is_fresh, 15)
        time.sleep(FRESH_AFTER_WRITE_S)
        for target in live:
            target = f"{target}&n=1" if "decisions" in target else target
            assert _front_only(pair.port, target) == _front_only(pair.private_port, target), target
