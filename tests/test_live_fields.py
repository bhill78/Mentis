"""The two fields `/private/live` adds for R4 to R6, from their real producers on real classes:
`Conversations.active_execution_rows` and `MentisService.run_observations`, and the one rule for
the byte cap (`docs/rust/contracts/live-snapshot.md`).

What Rust makes of them is `crates/mentis-server/tests/live_seam.rs`, against these same producers.
"""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from mentis.core.run_feed import RunFeed
from mentis.web import (_LIVE_FIELDS_MOST, _added_live_fields, _live_answer,
                        _LiveSnapshots, _State, fixture)


@pytest.fixture()
def st(tmp_path):
    fixture.build(str(tmp_path / "brain"))
    return _State(str(tmp_path / "brain"))


@pytest.fixture()
def fast_switching():
    """Threads change hands as often as the interpreter allows, so a copy that isn't atomic shows."""
    held = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(held)


def _who(st):
    return st.cv.resolve_participant("@brian")


def _conversation(st):
    return st.cv.open_conversation("Live fields", attributed_to=_who(st))


def _open_run(st, run, instance="inst-1", *, activity=None):
    st.agents.agents_open_run(instance, run)
    if activity:
        st.agents._runs[run]["feed"].activity = activity
        st.agents._runs[run]["feed"].activity_at = 5.5


# -- active_executions ----------------------------------------------------------------------------


def test_only_the_six_named_members_of_what_is_not_ended_in_start_order(st):
    me, where = _who(st), _conversation(st)
    first = st.cv.begin_execution(participant=me, conversation=where, persona="ent-persona",
                                  runtime="claude", for_expectation="opr-e",
                                  material=("not for the snapshot",))
    gone = st.cv.begin_execution(participant=me, conversation=where)
    last = st.cv.begin_execution(participant=me)
    st.cv.end_execution(gone.reference)

    rows = st.cv.active_execution_rows()
    assert rows == [
        {"reference": first.reference, "participant": me, "conversation": where,
         "runtime": "claude", "persona": "ent-persona", "for_expectation": "opr-e"},
        {"reference": last.reference, "participant": me, "conversation": None,
         "runtime": None, "persona": None, "for_expectation": None},
    ]
    assert [r["reference"] for r in rows] == [e.reference for e in st.cv.active_executions()]
    assert "not for the snapshot" not in json.dumps(rows)


def test_the_registry_is_the_exact_dict_the_atomic_copy_argument_is_about(st):
    assert type(st.cv._executions) is dict


def _churning(st, stop):
    me, where = _who(st), _conversation(st)

    def churn():
        while not stop.is_set():
            ex = st.cv.begin_execution(participant=me, conversation=where)
            st.cv.end_execution(ex.reference)
    return churn


def test_the_lock_free_copy_survives_starts_and_ends_landing_during_it(st, fast_switching):
    """And the comprehension beside it, which is the control: the same dict and the same threads
    do break a copy that runs bytecode between items."""
    me, where = _who(st), _conversation(st)
    for _ in range(2000):
        st.cv.begin_execution(participant=me, conversation=where)
    stop = threading.Event()
    churn = threading.Thread(target=_churning(st, stop), daemon=True)
    churn.start()
    try:
        deadline = time.monotonic() + 5
        broke = None
        while broke is None and time.monotonic() < deadline:
            try:
                [e for e in st.cv._executions.values()]
            except RuntimeError as exc:
                broke = str(exc)
        assert broke and "changed size" in broke, "the control never broke: this shows nothing"

        # By the clock: the churn leaves every ended handle in the registry, as a real process does.
        copies, deadline = 0, time.monotonic() + 3
        while time.monotonic() < deadline:
            assert len(st.cv.active_execution_rows()) >= 2000
            copies += 1
        assert copies >= 1
    finally:
        stop.set()
        churn.join(timeout=10)


# -- run_observations -----------------------------------------------------------------------------


class _Stated:
    def __init__(self, inner, on_running):
        self._inner, self._on_running = inner, on_running

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def running(self):
        self._on_running()
        return {"inst-running"}


def test_every_run_reads_as_agents_runs_says_member_by_member_and_in_its_order(st):
    agents = st.agents
    _open_run(st, "opr-new", "inst-running", activity="Run npm test")
    _open_run(st, "opr-asking", "inst-2")
    agents._runs["opr-asking"]["permissions"]["form-1"] = {"form": "form-1", "asked_at": 1.5}
    agents._runs["opr-asking"]["permissions"]["form-2"] = {"form": "form-2", "asked_at": 2.5}
    _open_run(st, "opr-done", "inst-3")
    row = agents._runs["opr-done"]
    row.update(performing_since=1.0, last_event={"kind": "k", "at": 2.0, "what": "w"},
               stop={"by": "me", "why": "enough", "at": 2.5},
               consent_applied={"mode": "client"}, tooling={"mcp": ["mentis"], "n": 1.5},
               outcome={"stop_reason": "end_turn", "error_kind": None, "error": None,
                        "stopped": True, "session_ended": False})
    agents.agents_end_run("opr-done")
    agents.execution = _Stated(agents.execution, lambda: None)

    got = agents.run_observations()
    want = agents.agents_runs()
    assert got == want
    assert list(got) == list(want)
    for run in want:
        assert list(got[run]) == list(want[run]), "as `agents_runs` lists them"
    assert got["opr-new"]["running"] is True
    assert got["opr-new"]["activity"] == "Run npm test"
    assert got["opr-asking"]["permission"]["form"] == "form-1"
    assert "tooling" not in got["opr-new"], "absent until the run has ended"
    assert got["opr-done"]["tooling"] == {"mcp": ["mentis"], "n": 1.5}


def test_only_the_named_members_go_and_nothing_held_is_handed_out(st):
    _open_run(st, "opr-1")
    st.agents._runs["opr-1"]["permissions"]["form-1"] = {"form": "form-1"}
    st.agents._runs["opr-1"]["not-named"] = "stays here"
    got = st.agents.run_observations()["opr-1"]
    assert "feed" not in got and "not-named" not in got
    got["permissions"].clear()
    assert st.agents._runs["opr-1"]["permissions"], "a copy"


def test_mars_is_read_with_no_service_lock_held_and_a_failed_read_is_nothing_running(st):
    agents = st.agents
    _open_run(st, "opr-1", "inst-running")
    free = []

    def on_running():
        taken = []

        def try_it():
            got = agents._lock.acquire(timeout=0)
            taken.append(got)
            if got:
                agents._lock.release()
        other = threading.Thread(target=try_it)
        other.start()
        other.join()
        free.extend(taken)

    agents.execution = _Stated(agents.execution, on_running)
    assert agents.run_observations()["opr-1"]["running"] is True
    assert free == [True]

    def raises():
        raise RuntimeError("no MARS")
    agents.execution = _Stated(agents.execution, raises)
    assert agents.run_observations()["opr-1"]["running"] is False


def test_a_real_feed_s_activity_is_read_without_its_lock_so_only_one_lock_is_ever_held(st):
    _open_run(st, "opr-1")
    feed = st.agents._runs["opr-1"]["feed"]
    assert isinstance(feed, RunFeed)
    with feed._lock:
        done = []
        reader = threading.Thread(target=lambda: done.append(st.agents.run_observations()))
        reader.start()
        reader.join(timeout=10)
        assert done, "it waited on a feed's lock"


def test_end_consent_and_tooling_landing_during_the_copy_change_nothing_it_encodes(st, fast_switching):
    """What a run's end writes it writes outside the service's lock (`core/service.py`), so a member
    can change beside the copy, but each is replaced whole: the row encodes as one or the other."""
    agents = st.agents
    for n in range(40):
        _open_run(st, f"opr-{n}", f"inst-{n}")
    rows = list(agents._runs.values())
    stop = threading.Event()

    def change():
        n = 0
        while not stop.is_set():
            n += 1
            for o in rows:
                o["ended_at"] = float(n)
                o["consent_applied"] = {"n": n}
                o["tooling"] = {"n": n, "mcp": ["mentis"]}
                o["last_event"] = {"kind": "k", "at": float(n), "what": "w"}
                o["permissions"][f"f{n}"] = {"form": f"f{n}"}
                o["permissions"].pop(f"f{n - 1}", None)
                o["stop"] = {"by": "b", "why": "w", "at": float(n)}

    other = threading.Thread(target=change, daemon=True)
    other.start()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            json.dumps(agents.run_observations(), allow_nan=False)
    finally:
        stop.set()
        other.join(timeout=10)


# -- the envelope and the byte rule ---------------------------------------------------------------


def _answer(st, snapshots=None):
    return json.loads(_live_answer(snapshots or _LiveSnapshots(), st.agents, st.cv))


def test_the_fields_are_added_to_the_envelope_and_nothing_of_it_changes(st):
    me, where = _who(st), _conversation(st)
    st.cv.begin_execution(participant=me, conversation=where, for_expectation="opr-e")
    _open_run(st, "opr-1")
    snapshots = _LiveSnapshots()
    bare = snapshots.take(st.agents)
    got = _answer(st, snapshots)
    assert list(got) == ["schema", "boot_id", "generation", "live_hash", "taken_at", "fields"]
    assert list(got["fields"]) == ["live_now", "run_marks", "active_executions", "run_observations"]
    assert got["fields"]["live_now"] == json.loads(json.dumps(bare["fields"]["live_now"]))
    assert got["fields"]["active_executions"] == st.cv.active_execution_rows()
    assert got["fields"]["run_observations"] == json.loads(json.dumps(st.agents.run_observations()))
    assert (got["generation"], got["live_hash"]) == (bare["generation"], bare["live_hash"])


def test_a_change_only_the_added_fields_see_moves_neither_generation_nor_hash(st):
    me, where = _who(st), _conversation(st)
    _open_run(st, "opr-1")
    snapshots = _LiveSnapshots()
    before = _answer(st, snapshots)
    st.cv.begin_execution(participant=me, conversation=where)
    st.agents._runs["opr-1"]["consent_applied"] = {"mode": "client"}
    after = _answer(st, snapshots)
    assert len(after["fields"]["active_executions"]) == 1
    assert after["fields"]["run_observations"]["opr-1"]["consent_applied"] == {"mode": "client"}
    assert (after["generation"], after["live_hash"]) == (before["generation"], before["live_hash"])
    _open_run(st, "opr-2")
    moved = _answer(st, snapshots)
    assert moved["generation"] > after["generation"], "a run_marks change still does"


def _populated(st, count, *, asking=False):
    """`count` active on each side, the gate's matched population: the real classes and their real
    shapes, with JSON-shaped tooling sized so 1,000 runs encode to about the gate's 685 KB. `asking`
    puts a waiting question on each run as well, which the gate's case didn't."""
    me, where = _who(st), _conversation(st)
    for n in range(count):
        st.cv.begin_execution(participant=me, conversation=where, persona=f"ent-persona{n:06d}",
                              runtime="claude", for_expectation=f"opr-{n:012d}")
        run = f"opr-run{n:09d}"
        st.agents.agents_open_run(f"inst-{n:012d}", run)
        o = st.agents._runs[run]
        o.update(performing_since=1793562000.5, consent_applied={"mode": "client", "n": n},
                 last_event={"kind": "tool_call", "at": 1793562001.25, "what": "Run npm test"},
                 tooling={"mcp": ["mentis"], "tools": ["read", "edit", "bash"], "version": "0.97.0",
                          "note": "x" * 150})
        if asking:
            o["permissions"][f"form-{n}"] = {
                "form": f"form-{n}", "decision": f"opr-d{n}", "title": "Run npm test",
                "summary": "Run npm test", "kind": "execute", "asked_at": 1793562002.5,
                "options": ["Allow", "Deny"], "conversation": where, "post": f"ent-p{n}"}
        o["feed"].activity, o["feed"].activity_at = "Run npm test", 1793562003.5


def test_in_the_matched_1000_active_case_neither_field_is_over_and_the_total_loses_the_second(st):
    _populated(st, 1000)
    active = json.dumps(st.cv.active_execution_rows())
    runs = json.dumps(st.agents.run_observations())
    assert len(active) < _LIVE_FIELDS_MOST and len(runs) < _LIVE_FIELDS_MOST, "neither alone"
    assert len(active) + len(runs) > _LIVE_FIELDS_MOST, "and together they are"

    added = _added_live_fields(st.agents, st.cv)
    assert [name for name, _ in added] == ["active_executions"]
    assert sum(len(text) for _, text in added) <= _LIVE_FIELDS_MOST
    fields = _answer(st)["fields"]
    assert len(fields["active_executions"]) == 1000
    assert "run_observations" not in fields


def test_with_every_run_asking_run_observations_is_over_alone_and_the_outcome_is_the_same(st):
    _populated(st, 1000, asking=True)
    assert len(json.dumps(st.agents.run_observations())) > _LIVE_FIELDS_MOST
    assert [name for name, _ in _added_live_fields(st.agents, st.cv)] == ["active_executions"]


def test_a_fixed_rule_whichever_field_is_large(st, monkeypatch):
    big, small = {"x": "y" * (_LIVE_FIELDS_MOST + 1)}, {"x": "y"}

    def with_sizes(active, runs):
        monkeypatch.setattr(st.cv, "active_execution_rows", lambda: active)
        monkeypatch.setattr(st.agents, "run_observations", lambda: runs)
        return [name for name, _ in _added_live_fields(st.agents, st.cv)]

    assert with_sizes(small, small) == ["active_executions", "run_observations"]
    assert with_sizes(big, small) == ["run_observations"], "the first alone over goes, and adds nothing"
    assert with_sizes(small, big) == ["active_executions"]
    assert with_sizes(big, big) == []
    half = {"x": "y" * (_LIVE_FIELDS_MOST // 2)}
    assert with_sizes(half, half) == ["active_executions"], "neither over, the total over"
    exact = "y" * (_LIVE_FIELDS_MOST - len(json.dumps({"x": ""})))
    assert with_sizes({"x": exact}, {}) == ["active_executions"], "up to the cap, inclusive"


@pytest.mark.parametrize("tooling", [float("nan"), float("inf"), object(), {"a": {1, 2}}, b"bytes"],
                         ids=["nan", "inf", "object", "set", "bytes"])
def test_tooling_that_can_t_be_json_loses_its_field_and_never_the_envelope(st, tooling):
    me, where = _who(st), _conversation(st)
    st.cv.begin_execution(participant=me, conversation=where)
    _open_run(st, "opr-1")
    st.agents._runs["opr-1"]["tooling"] = tooling
    got = _answer(st)
    assert "run_observations" not in got["fields"]
    assert len(got["fields"]["active_executions"]) == 1
    assert isinstance(got["live_hash"], str)


def test_a_producer_that_raises_loses_its_field_and_never_the_envelope(st, monkeypatch):
    def fails():
        raise RuntimeError("no")
    monkeypatch.setattr(st.agents, "run_observations", fails)
    assert list(_answer(st)["fields"]) == ["live_now", "run_marks", "active_executions"]


def test_tooling_as_a_real_run_returns_it_is_carried(st):
    """Through a real `perform` on `FakeExecution`, as far as a run's end writes it."""
    _open_run(st, "opr-1")
    from mentis.execution import RunResult
    result = RunResult(run_id="inst-1", backend="claude", started=True, tooling={"a": [1, {"b": None}]},
                       consent_applied={"mode": "x"}, started_at=1.0, finished_at=2.0)
    o = st.agents._runs["opr-1"]
    o["consent_applied"], o["tooling"] = result.consent_applied, result.tooling
    fields = _answer(st)["fields"]
    assert fields["run_observations"]["opr-1"]["tooling"] == {"a": [1, {"b": None}]}
