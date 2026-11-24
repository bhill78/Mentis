"""THE ACTUAL SEND BOUNDARY (`mentis.execution.send`): eligibility checked
where the bytes cross, and an honest account of what became of them.

The seam the Magnet message boundary's revised contract (§§4-5) needs from
the execution boundary, and generic: nothing here knows what a Magnet is.

  * A caller deciding a run may go and the run's prompt crossing are not the
    same moment. The connection, the session and the tooling happen in
    between, and an edit can land there. `begin_gate` cannot see it -- it
    answers before all of that -- so the send gate is entered at the send,
    with nothing but the hand-over after it. Of an edit and a send, one wins:
    the first half of this suite drives both orders against the REAL
    `MarsExecution` and a stand-in for `mars stdio`, and reads the stand-in's
    own log to see whether a prompt was ever sent.
  * Preparing is not sending, sending is not delivery, and a failed send is
    not delivery either. `supplied` is said only of bytes a runtime
    acknowledged, and an acknowledgement belongs to the send it answers.
  * Where a run never reaches its boundary at all -- a stop held on it, an
    execution that honours no gate -- the caller is told `prepared`. Never
    `supplied`, which is what a false delivery audit would look like.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import pytest

from mentis.api.types import Address, Selection
from mentis.execution import FakeExecution, RunResult, RunSpec, send
from mentis.execution.mars import MarsExecution
from mentis.execution.send import DeliveryWatch, SendBoundary
from mentis.web import _State, fixture

STAND_IN = Path(__file__).with_name("fakes") / "mars_send_boundary_stand_in.py"


# -- the real boundary -------------------------------------------------------

@pytest.fixture()
def mars(tmp_path):
    made = []

    def start(mode):
        log = tmp_path / f"told-{mode}-{len(made)}.jsonl"
        ex = MarsExecution([sys.executable, str(STAND_IN), str(log), mode],
                           startup_s=30)
        made.append(ex)
        return ex, log

    yield start
    for ex in made:
        ex.close()


def _told(log: Path) -> list[dict]:
    """What the stand-in was actually asked to do, in order."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _events(log: Path) -> list[str]:
    return [entry["event"] for entry in _told(log)]


def _gate(answer):
    """A send gate that answers whatever `answer()` says now."""
    @contextlib.contextmanager
    def gate():
        yield answer()
    return gate


def _spec(tmp_path, run_id="r1", **kw):
    return RunSpec(run_id=run_id, backend="stand-in", workspace=str(tmp_path),
                   prompt="the words that were accepted", **kw)


def test_an_edit_landing_while_the_session_opens_wins_and_nothing_is_sent(mars, tmp_path):
    """THE WINDOW `begin_gate` CANNOT SEE. `on_open` fires once the session is
    open -- after the run was decided, before the bytes go -- and stands here
    for the owner editing the work in that window. The gate is entered after
    it, so the edit wins: the stand-in is never asked to prompt."""
    ex, log = mars("ok")
    edited: list[bool] = []
    reports: list[dict] = []
    spec = _spec(tmp_path,
                 on_open=lambda applied: edited.append(True),
                 send_gate=_gate(lambda: ("the work was edited after it was "
                                          "accepted") if edited else None),
                 on_delivery=reports.append)
    res = ex.perform(spec)
    assert _events(log) == ["new"], "an edited request was sent anyway"
    assert res.stop_reason == "cancelled"
    assert "the work was edited after it was accepted" in (res.error or "")
    assert "prompt_sent" not in res.timing
    assert [r["state"] for r in reports] == ["refused"]
    assert reports[0]["why"] == "the work was edited after it was accepted"
    assert reports[0]["sent_at"] is None and reports[0]["acknowledged"] is None


def test_a_send_that_wins_is_supplied_only_on_its_acknowledgement(mars, tmp_path):
    """SEND WINNING FIRST. The gate allows and hands back its reservation; the
    bytes go; `sent` says they were handed over and says nothing about
    arrival; `supplied` comes from the session's own acknowledgement and
    carries the reservation the gate made."""
    ex, log = mars("ok")
    reports: list[dict] = []
    res = ex.perform(_spec(tmp_path, send_gate=_gate(
        lambda: {"version": 3, "turn": "ent-accepted"}), on_delivery=reports.append))
    assert _events(log) == ["new", "prompt"]
    assert [e["text"] for e in _told(log) if e["event"] == "prompt"] == [
        "the words that were accepted"]
    assert res.stop_reason == "end_turn"
    assert [r["state"] for r in reports] == ["sent", "supplied"]
    sent, supplied = reports
    assert sent["acknowledged"] is None, "handing over was called delivery"
    assert sent["reservation"] == {"version": 3, "turn": "ent-accepted"}
    assert supplied["acknowledged"] == send.BY_UPDATE
    assert supplied["reservation"] == {"version": 3, "turn": "ent-accepted"}
    assert supplied["sent_at"] == sent["sent_at"]
    assert supplied["acknowledged_at"] >= sent["sent_at"]
    assert supplied["send"] == sent["send"] == 1


def test_an_edit_after_a_send_blocks_the_next_one_and_unsends_nothing(mars, tmp_path):
    """A LATER EDIT IS NOT AN UNSEND. The first send is acknowledged and stays
    supplied; the edit that follows it refuses the next send."""
    ex, log = mars("ok")
    edited: list[bool] = []
    first: list[dict] = []
    second: list[dict] = []
    gate = _gate(lambda: "the accepted version was edited" if edited else None)
    ex.perform(_spec(tmp_path, "r1", send_gate=gate, on_delivery=first.append))
    assert [r["state"] for r in first] == ["sent", "supplied"]
    edited.append(True)
    res = ex.perform(_spec(tmp_path, "r2", send_gate=gate, on_delivery=second.append))
    assert [r["state"] for r in second] == ["refused"]
    assert res.stop_reason == "cancelled"
    assert _events(log) == ["new", "prompt", "new"], "the edited work was sent"
    assert [r["state"] for r in first] == ["sent", "supplied"], (
        "a later edit changed what an earlier send was reported as")


def test_a_turn_with_no_update_is_acknowledged_by_its_own_result(mars, tmp_path):
    """The only acknowledgement a silent turn gives is its result, and that is
    an acknowledgement of these bytes."""
    ex, log = mars("quiet")
    reports: list[dict] = []
    res = ex.perform(_spec(tmp_path, send_gate=_gate(lambda: None),
                           on_delivery=reports.append))
    assert res.stop_reason == "end_turn"
    assert _events(log) == ["new", "prompt"]
    assert [r["state"] for r in reports] == ["sent", "supplied"]
    assert reports[-1]["acknowledged"] == send.BY_RESULT


def test_a_send_the_other_end_would_not_take_is_failed_never_supplied(mars, tmp_path):
    """A SEND THAT FAILED IS NOT A DELIVERY. The backend answered and refused
    the prompt: the bytes were handed over and did not arrive."""
    ex, log = mars("refuse")
    reports: list[dict] = []
    res = ex.perform(_spec(tmp_path, send_gate=_gate(lambda: None),
                           on_delivery=reports.append))
    assert _events(log) == ["new", "prompt"]
    assert res.error_kind and res.stop_reason is None
    assert [r["state"] for r in reports] == ["sent", "failed"]
    assert reports[-1]["acknowledged"] is None
    assert send.SUPPLIED not in [r["state"] for r in reports]


def test_bytes_in_flight_when_the_connection_went_are_unconfirmed(mars, tmp_path):
    """NOT DELIVERED, NOT FAILED: UNKNOWN. The prompt arrived and the other
    end died without answering, so nothing can say whether a runtime ever
    read it. The honest state is its own, and it is not `supplied`."""
    ex, log = mars("vanish")
    reports: list[dict] = []
    res = ex.perform(_spec(tmp_path, send_gate=_gate(lambda: None),
                           on_delivery=reports.append))
    assert _events(log) == ["new", "prompt"]
    assert res.stop_reason is None
    assert [r["state"] for r in reports] == ["sent", "unconfirmed"]
    assert reports[-1]["acknowledged"] is None
    assert reports[-1]["why"], "an unconfirmed send said nothing of why"


@pytest.mark.parametrize("how", ["enter", "exit"])
def test_a_gate_that_cannot_answer_or_commit_refuses(mars, tmp_path, how):
    """FAILS CLOSED. An eligibility nobody could confirm, and a reservation
    that could not be written, both send nothing."""
    ex, log = mars("ok")
    reports: list[dict] = []

    @contextlib.contextmanager
    def gate():
        if how == "enter":
            raise RuntimeError("the record could not be read")
        yield None
        raise RuntimeError("the reservation could not be committed")

    res = ex.perform(_spec(tmp_path, send_gate=gate, on_delivery=reports.append))
    assert _events(log) == ["new"], "a send nothing vouched for went anyway"
    assert res.stop_reason == "cancelled"
    assert "could not be confirmed" in (res.error or "")
    assert [r["state"] for r in reports] == ["refused"]


# -- the coordination that asks for the run ----------------------------------

@pytest.fixture()
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    return {"st": st, "svc": st.agents, "ex": st.agents.execution}


def _instance(world):
    return world["svc"].agents_summon(
        Address(name="A", runtime="claude"),
        Selection(runtime="claude", model=None, requested_effort=None,
                  because=("test",)),
        workspace=".")


def test_the_service_carries_the_gate_and_the_account_to_the_execution(world):
    """The seam is generic: `agents_perform` hands the gate and the delivery
    account to whatever `Execution` it has, and a refusal at that boundary
    sends nothing and ends the run as a cancel."""
    svc, ex = world["svc"], world["ex"]
    inst = _instance(world)
    reports: list[dict] = []
    svc.agents_perform(inst.instance_id, "the accepted words",
                       send_gate=_gate(lambda: None), on_delivery=reports.append)
    assert ex.sent == ["the accepted words"]
    assert [r["state"] for r in reports] == ["sent", "supplied"]

    refused: list[dict] = []
    svc.agents_perform(inst.instance_id, "the edited words",
                       send_gate=_gate(lambda: "it was edited"),
                       on_delivery=refused.append)
    assert ex.sent == ["the accepted words"], "a refused send was sent"
    assert [r["state"] for r in refused] == ["refused"]


def test_an_edit_in_the_window_wins_through_the_service_too(world):
    """`FakeExecution.before_send` is the same window the real boundary has
    between opening a session and sending. An edit landing there refuses."""
    svc, ex = world["svc"], world["ex"]
    inst = _instance(world)
    edited: list[bool] = []
    ex.before_send = lambda spec: edited.append(True)
    reports: list[dict] = []
    outcome = svc.agents_perform(inst.instance_id, "the accepted words",
                                 send_gate=_gate(lambda: "it was edited"
                                                 if edited else None),
                                 on_delivery=reports.append)
    assert ex.sent == [], "the work was sent after it was edited"
    assert [r["state"] for r in reports] == ["refused"]
    assert outcome is not None


def test_a_run_held_before_it_began_is_prepared_and_never_supplied(world):
    """A stop held on the run never reaches a send boundary at all. Prepared
    is the whole truth of it: composed, and nothing sent."""
    svc, ex = world["svc"], world["ex"]
    inst = _instance(world)
    reports: list[dict] = []
    svc.agents_perform(inst.instance_id, "the accepted words",
                       begin_gate=_gate(lambda: "the owner stopped this work"),
                       send_gate=_gate(lambda: None),
                       on_delivery=reports.append)
    assert ex.sent == []
    assert [r["state"] for r in reports] == [send.PREPARED]
    assert "stopped" in (reports[0]["why"] or "")
    assert reports[0]["sent_at"] is None


def test_an_execution_that_honours_no_gate_is_never_reported_supplied(world,
                                                                      monkeypatch):
    """THE SAFE DIRECTION. An `Execution` that knows nothing of the boundary
    cannot make a delivery claim: the coordination says what it can see, and
    a run that reported no send is `prepared`."""
    svc = world["svc"]
    inst = _instance(world)

    class DeafExecution:
        def perform(self, spec, on_event=None, on_permission=None):
            return RunResult(run_id=spec.run_id, backend=spec.backend,
                             started=True, stop_reason="end_turn", text="done")

        def backends(self):
            return []

        def running(self):
            return set()

        def cancel(self, run_id):
            return False

        def close(self):
            pass

    monkeypatch.setattr(svc, "execution", DeafExecution())
    reports: list[dict] = []
    svc.agents_perform(inst.instance_id, "the accepted words",
                       send_gate=_gate(lambda: None), on_delivery=reports.append)
    assert [r["state"] for r in reports] == [send.PREPARED]
    assert send.SUPPLIED not in [r["state"] for r in reports]


def test_a_send_whose_account_is_lost_is_unconfirmed_not_supplied(world,
                                                                  monkeypatch):
    """Bytes handed over that nothing accounted for: the coordination can see
    the send happened and cannot see what became of it."""
    svc = world["svc"]
    inst = _instance(world)

    class SilentExecution(FakeExecution):
        def perform(self, spec, on_event=None, on_permission=None):
            res = RunResult(run_id=spec.run_id, backend=spec.backend, started=True)
            res.timing["prompt_sent"] = 1.0
            return res

    monkeypatch.setattr(svc, "execution", SilentExecution())
    reports: list[dict] = []
    svc.agents_perform(inst.instance_id, "the accepted words",
                       send_gate=_gate(lambda: None), on_delivery=reports.append)
    assert [r["state"] for r in reports] == [send.UNCONFIRMED]


# -- the account itself ------------------------------------------------------

def test_supplied_without_an_acknowledgement_is_not_recorded_as_supplied():
    """A caller cannot ask for a delivery claim it has no evidence for."""
    reports: list[dict] = []
    boundary = SendBoundary(RunSpec(run_id="r", backend="b", workspace=".",
                                    prompt="p", on_delivery=reports.append))
    boundary.handed_over(10.0)
    boundary.say(send.SUPPLIED)
    assert [r["state"] for r in reports] == [send.SENT, send.UNCONFIRMED]


def test_an_acknowledgement_before_the_send_is_not_proof_of_it():
    """Evidence from before the bytes went is not evidence that they went."""
    boundary = SendBoundary(RunSpec(run_id="r", backend="b", workspace=".",
                                    prompt="p"))
    boundary.acknowledge(send.BY_UPDATE, 5.0)
    assert boundary.acknowledged is None
    boundary.handed_over(10.0)
    boundary.acknowledge(send.BY_UPDATE, 9.0)
    assert boundary.acknowledged is None
    boundary.acknowledge(send.BY_UPDATE, 11.0)
    assert boundary.acknowledged == send.BY_UPDATE


def test_exactly_one_terminal_report_and_the_first_one_stands():
    reports: list[dict] = []
    watch = DeliveryWatch(reports.append)
    boundary = SendBoundary(RunSpec(run_id="r", backend="b", workspace=".",
                                    prompt="p", on_delivery=watch))
    boundary.handed_over(10.0)
    boundary.acknowledge(send.BY_RESULT, 11.0)
    boundary.say(send.SUPPLIED)
    boundary.say(send.FAILED, why="said twice")
    watch.otherwise(send.UNCONFIRMED, run="r", why="said again")
    assert [r["state"] for r in reports] == [send.SENT, send.SUPPLIED]
    assert watch.terminal() == send.SUPPLIED


def test_a_delivery_account_that_raises_never_fails_the_run(mars, tmp_path):
    """An audit is not a veto: a report that raises is logged and the run goes
    on exactly as it would have."""
    ex, log = mars("ok")

    def broken(report):
        raise RuntimeError("the audit could not be written")

    res = ex.perform(_spec(tmp_path, send_gate=_gate(lambda: None),
                           on_delivery=broken))
    assert res.stop_reason == "end_turn"
    assert _events(log) == ["new", "prompt"]
