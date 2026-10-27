"""An execution handle's lifecycle, as the headless core keeps it.

Lifted from Mark IV's tests/test_session_lifecycle.py and PRUNED. Mark IV's
suite was mostly about Foundation: claiming a dormant runtime session, asking
the runtime whether it could still be resumed, adopting one after a restart,
provisioned runtime homes, Codex's sandbox, and each adapter's stream. All of
that is gone -- MARS opens a session per run (`mentis.execution`) -- and the
cases that only exercised it were removed, not ported.

What is kept is what the coordination layer still promises about the handle a
Participant's work runs on (`MentisService`), through the real dispatch with
only the agent replaced (`FakeExecution`):

  * repeated work by one binding reuses one handle; another Conversation,
    another runtime or another Participant is another binding;
  * a failed run's handle is given back, and the record still says it existed;
  * a claim is given back if the run cannot be recorded;
  * reuse never moves work to another workspace;
  * continuity notes belong to the thread that made them;
  * a release is recorded, is final even mid-run, and claims nothing about
    any provider session;
  * many dispatches at once share nothing and strand nothing.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.api.types import Address, Liveness, Selection
from mentis.execution import RunResult
from mentis.web import _State, fixture


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    return {"st": st, "cv": st.cv, "ex": st.agents.execution}


def _work(world, participant, conversation, *, runtime="claude"):
    """Real dispatch, through the real lifecycle, onto a fake AGENT.

    Nothing in Mentis is stubbed: `agents_summon`, `agents_perform`, the
    grant and the instance record all run. Only MARS is fake.
    """
    from mentis.web import dispatch as D
    from mentis.conversation import text as text_part
    cv = world["cv"]
    turn = cv.say(conversation, participant, [text_part("more please")])
    return D.dispatch(world["st"], conversation=conversation, turn=turn,
                      participant=participant, work="more", runtime=runtime)


def _selection(runtime="claude"):
    return Selection(runtime=runtime, model=None, requested_effort=None,
                     because=("test",))


def _member(cv, alias, name="Cells"):
    who = cv.create_participant(alias)
    conv = cv.open_conversation(name)
    cv.join(who, conv)
    return who, conv


# -- bindings, through dispatch, end to end ------------------------------------

def test_repeated_work_reuses_one_instance(world):
    """ACCEPTANCE: no duplicate lingering instances after each run."""
    st, cv = world["st"], world["cv"]
    ada, conv = _member(cv, "@AdaLife")
    ids = {_work(world, ada, conv)["instance"] for _ in range(4)}
    assert len(ids) == 1, "a new instance was minted for every run"
    assert len(world["ex"].performed) == 4
    assert len(st.agents.agents_list(include_finished=True)) == 1


def test_another_conversation_does_not_inherit_the_session(world):
    """ACCEPTANCE: continuity scope includes the Conversation."""
    cv = world["cv"]
    ada = cv.create_participant("@AdaScope")
    one = cv.open_conversation("Cells")
    two = cv.open_conversation("Busbars")
    for c in (one, two):
        cv.join(ada, c)
    assert _work(world, ada, one)["instance"] != _work(world, ada, two)["instance"]


def test_another_runtime_is_another_binding(world):
    """ACCEPTANCE: same Participant, two runtimes, two bindings, one identity."""
    st, cv = world["st"], world["cv"]
    ada, conv = _member(cv, "@AdaRuntimes")
    a = _work(world, ada, conv, runtime="claude")["instance"]
    b = _work(world, ada, conv, runtime="codex")["instance"]
    assert a != b
    live = st.agents.agents_list(include_finished=True)
    assert {i.participant for i in live} == {ada}
    assert [s.backend for s in world["ex"].performed] == ["claude", "codex"]


def test_two_adas_do_not_share_a_session(world):
    cv = world["cv"]
    one = cv.create_participant("@AdaTwin")
    two = cv.create_participant("@AdaTwin")
    conv = cv.open_conversation("Cells")
    for p in (one, two):
        cv.join(p, conv)
    assert _work(world, one, conv)["instance"] != _work(world, two, conv)["instance"]


# -- nothing is stranded ----------------------------------------------------

def test_a_failed_run_does_not_linger_in_the_live_set(world):
    """A handle whose run failed is given back; the history still says it
    existed and how it ended. Releasing a handle is not erasing a record."""
    st, cv = world["st"], world["cv"]

    def bad(spec):
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, error_kind="agent_error",
                         error="it went wrong")

    world["ex"].script = {"claude": bad}
    ada, conv = _member(cv, "@AdaFail")
    out = _work(world, ada, conv)
    assert out["ok"] is False
    assert st.agents.agents_list() == []
    assert st.agents.known(out["instance"]) is None
    assert any(i.instance_id == out["instance"]
               for i in st.agents.agents_list(include_finished=True))
    failed = [a for a in cv.history(execution=out["instance"])
              if a["act"] == "delivery-failed"]
    assert failed and "it went wrong" in failed[-1]["because"]


def test_a_claim_is_given_back_if_the_work_cannot_be_recorded(world):
    """An unusable claim would sit on the handle for good."""
    cv = world["cv"]
    ada, conv = _member(cv, "@AdaGuard")
    svc = world["st"].agents

    import mentis.web.dispatch as D
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no act"))
    real, D._started_act = D._started_act, boom
    try:
        with pytest.raises(RuntimeError):
            _work(world, ada, conv)
    finally:
        D._started_act = real
    assert [i for i in svc._live.values()
            if i.liveness is Liveness.BUSY] == [], "a claim was stranded"
    assert world["ex"].performed == []


def test_reuse_does_not_move_the_work_to_another_workspace(world, tmp_path):
    """An instance runs where it was started; work elsewhere gets its own."""
    svc = world["st"].agents
    addr = Address(name="A", runtime="claude")
    here, there = str(tmp_path / "here"), str(tmp_path / "there")
    first = svc.agents_summon(addr, _selection(), workspace=here)
    svc.agents_perform(first.instance_id, "work")
    got = svc.agents_summon(addr, _selection(), workspace=there)
    assert got.workspace == there
    assert got.instance_id != first.instance_id, (
        "work was moved into another workspace")
    # ...and the same workspace does continue the handle.
    again = svc.agents_summon(addr, _selection(), workspace=here)
    assert again.instance_id == first.instance_id


def test_continuity_evidence_is_not_shared_between_threads(world):
    """Notes lived on the service once, so dispatches mixed them."""
    svc = world["st"].agents
    seen = {}

    def go(tag):
        svc._notes().append(tag)
        time.sleep(0.05)
        seen[tag] = svc.summon_notes_here()

    threads = [threading.Thread(target=go, args=(f"t{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(v == [k] for k, v in seen.items()), seen


# -- release -----------------------------------------------------------------

def test_release_while_idle_is_recorded_as_relinquished(world):
    """ACCEPTANCE: the durable half of release, which is what survives."""
    svc = world["st"].agents
    inst = svc.agents_summon(Address("A", runtime="claude"), _selection(),
                             workspace=".", participant="ent-ada")
    svc.agents_perform(inst.instance_id, "work")
    result = svc.agents_release(inst.instance_id)
    assert result.released is True
    latest = [r for r in svc._corpus.instance_history()
              if r["instance_id"] == inst.instance_id][-1]
    assert latest["liveness"] == "gone"
    assert svc.known(inst.instance_id) is None


def test_a_released_handle_is_recorded_as_gone_not_finished(world):
    """The record must not contradict the release: a run that ends after its
    handle was let go is reported, and recorded GONE, not FINISHED."""
    svc = world["st"].agents
    inside, go_on = threading.Event(), threading.Event()

    def long(spec):
        inside.set()
        go_on.wait(5)
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done")

    world["ex"].script = {"claude": long}
    inst = svc.agents_summon(Address("A", runtime="claude"), _selection(),
                             workspace=".")
    out = []
    t = threading.Thread(target=lambda: out.append(
        svc.agents_perform(inst.instance_id, "long")), daemon=True)
    t.start()
    assert inside.wait(5)
    svc.agents_release(inst.instance_id)
    go_on.set()
    t.join(5)
    assert out and out[0].terminal == "reported_done"
    latest = [r for r in svc._corpus.instance_history()
              if r["instance_id"] == inst.instance_id][-1]
    assert latest["liveness"] == "gone"
    assert svc.known(inst.instance_id) is None


def test_release_never_claims_the_provider_session_was_destroyed(world):
    svc = world["st"].agents
    inst = svc.agents_summon(Address("A", runtime="claude"), _selection(),
                             workspace=".")
    result = svc.agents_release(inst.instance_id)
    said = " ".join(result.notes) + " ".join(result.residue)
    assert "destroyed" not in said.lower()
    assert "deleted" not in said.lower()


# -- under contention -------------------------------------------------------

def test_many_dispatches_at_once_share_nothing_and_strand_nothing(world):
    """Twelve threads asking for the same Participant in the same
    Conversation at the same moment. Each run must be alone in its handle,
    none may be lost, and nothing may be left BUSY with nothing inside it."""
    st, cv = world["st"], world["cv"]
    ada, conv = _member(cv, "@AdaBusy")
    inside: dict[str, int] = {}
    overlap = []
    lock = threading.Lock()

    def run(spec):
        with lock:
            inside[spec.run_id] = inside.get(spec.run_id, 0) + 1
            if inside[spec.run_id] > 1:
                overlap.append(spec.run_id)
        time.sleep(0.01)
        with lock:
            inside[spec.run_id] -= 1
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done")

    world["ex"].script = {"claude": run}
    done, errors = [], []

    def go():
        try:
            done.append(_work(world, ada, conv))
        except Exception as exc:                      # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)

    assert not errors, errors
    assert len(done) == 12
    assert all(d["ok"] for d in done), [d for d in done if not d["ok"]]
    assert len(world["ex"].performed) == 12
    assert overlap == [], "two runs were inside one handle at once"
    svc = st.agents
    assert [i.instance_id for i in svc._live.values()
            if i.liveness is Liveness.BUSY] == []
    assert svc.execution.running() == set()
    # No grant outlived its run.
    assert svc.authority._grants == {}
