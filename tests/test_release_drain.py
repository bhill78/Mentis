"""The release tool drains a server before it stops it (`tools/env/mentis_env.py`, `switch`).

The server side is `tests/test_server_drain.py`. Here the server is a fake that answers the
drain request as the real one does: the flag, and `held`, read in one moment; an id for the
drain, which every later call must name. What is tested: the server is stopped while it is
still draining and only once it holds nothing, in its stopping phase, whose duration is
longer than the SUM of every bounded step of the stop before the backend is killed; with runs
held the tool's own drain is CLEARED and the switch refused, nothing stopped; the bounded
wait; a server without the route falls back to counting and says so; nothing that fails
before the stop leaves a server draining; and a stop that began and did not finish is not
told to take work again.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_release_contract import Args, head, me, w  # noqa: F401

TOKEN = "drain-of-this-deployment"


class Draining:
    """A server as the tool sees it: what it answers to a drain request, what it lists as
    held, and the order things were asked of it."""

    def __init__(self, w, monkeypatch, held=(0,), name="test"):
        self.held = list(held)          # the count each successive `on` answers; the last repeats
        self.on = False
        self.phase = None
        self.held_at_stop = 0           # what it holds when asked to mark itself as stopping
        self.grants = None              # seconds it stays draining once stopping; None: as asked
        self.phase_at_stop = "never stopped"
        self.calls = []                 # "drain", "extend", "stopping", "clear", "stop(draining=...)"
        self.named = []                 # the drain each call named, in order
        self.fail_clear = False
        self.refused = [{"act": "opr-1", "expectation": "exp-1", "participant": "p"}]
        self.name = name
        monkeypatch.setattr(me, "_drain_ask", self.ask)
        monkeypatch.setattr(me, "DRAIN_ASK_EVERY_S", 0.01)

        def stop(c, e):
            self.calls.append(f"stop(draining={self.on})")
            self.phase_at_stop = self.phase
            self.on = False             # the flag ends with the process
            return ["stopped"]
        monkeypatch.setattr(me, "stop_env", stop)

    def flag(self, reason, lasts=120.0):
        return {"since": 100.0, "by": "@brian", "reason": reason, "phase": self.phase,
                "expires_at": 100.0 + lasts, "lasts_s": lasts,
                "refused": len(self.refused), "refused_starts": list(self.refused)}

    def ask(self, env, on, reason="", stopping_s=None, token=None, force=False):
        assert env["name"] == self.name
        self.named.append(token)
        if not on:
            self.calls.append("clear")
            if self.fail_clear:
                raise me.Failed("the server went away")
            if not self.on or token != TOKEN:
                return {"ok": False, "cleared": False, "held": 0, "refused": "not this drain",
                        "draining": self.flag("r") if self.on else None, "was": None}
            self.on, self.phase = False, None
            return {"ok": True, "cleared": True, "draining": None, "held": 0, "was": {}}
        if self.on and token != TOKEN:
            self.calls.append("refused")
            return {"ok": False, "held": 0, "draining": self.flag("someone else's"),
                    "refused": "a drain is already standing, and this call does not name it"}
        if stopping_s:
            self.calls.append("stopping")
            self.asked_to_stay = stopping_s
            if self.held_at_stop:
                return {"ok": False, "held": self.held_at_stop, "at": 150.0,
                        "draining": self.flag(reason),
                        "refused": f"{self.held_at_stop} dispatch(es) are held"}
            self.phase = "stopping"
            lasts = stopping_s if self.grants is None else self.grants
            return {"ok": True, "held": 0, "at": 150.0, "drain": TOKEN,
                    "draining": self.flag(reason, lasts)}
        self.calls.append("extend" if self.on else "drain")
        self.on, self.reason, self.phase = True, reason, self.phase or "draining"
        held = self.held.pop(0) if len(self.held) > 1 else self.held[0]
        return {"ok": True, "held": held, "bound_s": 120.0, "drain": TOKEN,
                "draining": self.flag(reason)}


def _deploy(w, rid, **kw):
    return me.cmd_deploy(w.cfg, Args(environment="test", release=rid, **kw))


def _no_route(env, on, reason="", **kw):
    raise me._NoDrain("the server has no drain route (a release from before it)")


# -- quiet: stopped while still draining ----------------------------------------------

def test_a_quiet_server_is_drained_and_stopped_while_it_is_still_draining(w, monkeypatch, capsys):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    w.unheld["test"] = {"recorded-under-this-server": 5600.0}     # what a read-back would doubt
    assert _deploy(w, rid) == 0
    assert server.calls == ["drain", "stopping", "stop(draining=True)"], "never cleared: it was stopped"
    # THE TOOL NAMES ITS OWN DRAIN on every call after the one that set it
    assert server.named == [None, TOKEN]
    assert server.phase_at_stop == "stopping" and server.asked_to_stay == me.STOP_DRAIN_S
    assert server.reason.startswith("deployment of r1")
    cur = w.cfg.serving("test")["current"]
    # NO RUN WAS INTERRUPTED, on the server's own answer: nothing was held and nothing could
    # start. The run a read-back alone could not exclude is excluded by that answer
    assert cur["runs_interrupted"] is False and cur["runs_in_flight"] == 0
    assert cur["runs_not_excluded"] == [] and cur["runs_ended_by_restart"] == []
    d = cur["drain"]
    assert d["used"] is True and d["held"] == 0 and d["by"] == "@brian" and d["id"] == TOKEN
    assert d["phase"] == "stopping" and d["stopping_lasts_seconds"] == me.STOP_DRAIN_S
    assert d["stop_before_kill_max_seconds"] == me.STOP_BEFORE_KILL_MAX_S
    assert 0 <= d["stop_took_seconds"] < d["stopping_lasts_seconds"] and "_asked" not in d
    # WHAT IT RESTS ON says exactly what the answer proves, and what it does not cover
    rests = cur["runs_interrupted_rests_on"]
    assert rests.startswith("the server's own answer that it held no dispatch and, in the same moment, "
                            "entered a stopping phase")
    assert f"{me.STOP_DRAIN_S} s by its monotonic clock" in rests
    assert "not hand-started sessions" in rests and rests.endswith("the record read back agrees")
    assert d["excluded_by_drain"] == ["recorded-under-this-server"] and d["read_back"] == "read"
    # what the drain refused is reported, so it can be addressed again
    assert d["starts_refused"] == 1 and d["starts_refused_listed"][0]["expectation"] == "exp-1"
    assert json.loads(capsys.readouterr().out)["drain"]["used"] is True


def test_the_read_back_stays_a_cross_check_on_a_drained_stop(w, monkeypatch):
    """Draining says nothing could be ended. If the record read back afterwards shows a run
    the restart ended all the same, that is reported, never overruled by the drain."""
    rid = w.release(head(w), "r1")
    Draining(w, monkeypatch)
    real_start = me.start_env

    def start(c, e, r, wait=300):
        real_start(c, e, r, wait)
        w.unheld["test"] = {"ended-all-the-same": 6000.0}
    monkeypatch.setattr(me, "start_env", start)
    assert _deploy(w, rid) == 0
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_ended_by_restart"] == ["ended-all-the-same"]
    assert cur["runs_interrupted"] is True
    assert cur["runs_interrupted_rests_on"] == "the record read back after the restart lists run(s) it ended"


def test_an_unreadable_read_back_rests_on_the_stopping_phase_and_says_so(w, monkeypatch):
    """The record cannot be read back after the restart. "No run interrupted" is still said,
    because the server was stopped inside its stopping phase, and the record says that is
    what it rests on. Without that phase the same doubt is reported as not known."""
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    w.unheld["test"] = None
    assert _deploy(w, rid) == 0
    cur = w.cfg.serving("test")["current"]
    assert server.phase_at_stop == "stopping"
    assert cur["runs_interrupted"] is False and cur["drain"]["read_back"] == "could not be read"
    assert cur["runs_interrupted_rests_on"].startswith("the server's own answer that it held no dispatch")
    assert cur["runs_interrupted_rests_on"].endswith("the record could not be read back")
    # the same doubt with no drain at all
    w.release(head(w), "r2", mars=b"mars-2")
    monkeypatch.setattr(me, "_drain_ask", _no_route)
    assert _deploy(w, "r2") == 0
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_interrupted"] is None
    assert cur["runs_interrupted_rests_on"] == "nothing: the record could not be read back and no drain was used"


class _Clock:
    """The tool's `time`, with a monotonic clock the test moves."""

    def __init__(self):
        self.ahead = 0.0

    def __getattr__(self, name):
        return getattr(time, name)

    def monotonic(self):
        return time.monotonic() + self.ahead


def test_a_stop_that_outlasted_the_stopping_phase_is_not_claimed_as_covered(w, monkeypatch):
    """The stop finished, but later than the server said it would stay draining (which the
    bounds make impossible unless something is wrong). The drain is then not what "no run
    interrupted" may rest on: with a read-back in doubt, it is reported as not known."""
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(me, "time", clock)
    stop = me.stop_env

    def slow(c, e):
        clock.ahead += me.STOP_DRAIN_S + 1
        return stop(c, e)
    monkeypatch.setattr(me, "stop_env", slow)
    w.unheld["test"] = {"recorded-under-this-server": 5600.0}
    assert _deploy(w, rid) == 0
    cur = w.cfg.serving("test")["current"]
    assert server.phase_at_stop == "stopping"
    assert cur["drain"]["stop_took_seconds"] > cur["drain"]["stopping_lasts_seconds"]
    assert cur["runs_interrupted"] is None
    assert cur["runs_not_excluded"] == ["recorded-under-this-server"]


def test_a_promotion_drains_production_and_is_complete(w, monkeypatch, capsys):
    w.release(head(w), "before", mars=b"mars-0")
    rid = w.release(head(w), "r1")
    w.accepted(rid)
    w.serves["prod"] = "before"
    server = Draining(w, monkeypatch, name="prod")
    w.unheld["prod"] = {"recorded-under-this-server": 5600.0}
    assert me.cmd_promote(w.cfg, Args(release=rid, owner_approved="yes")) == 0
    assert server.calls == ["drain", "stopping", "stop(draining=True)"]
    assert w.cfg.serving("prod")["current"]["runs_interrupted"] is False
    assert "no run interrupted" in capsys.readouterr().out


# -- runs held: the drain is cleared and nothing is stopped -----------------------------

def test_runs_held_at_the_drain_clear_it_and_refuse_with_nothing_stopped(w, monkeypatch):
    """Idle when first counted, and a run began while the switch was prepared: the drain's
    own count finds it, the drain is cleared so work goes on, and nothing is stopped."""
    rid = w.release(head(w), "r1")
    w.serves["test"] = "before"
    server = Draining(w, monkeypatch, held=[1])
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped: wait"):
        _deploy(w, rid)
    assert server.calls == ["drain", "clear"] and server.on is False
    assert server.named == [None, TOKEN], "it cleared the drain it set, by name"
    assert w.started == [] and w.serves["test"] == "before"


def test_a_run_the_server_lists_as_held_is_never_overruled_by_a_zero(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch, held=[0])
    asked = []

    def runs(env):
        asked.append(env["name"])
        return 0 if len(asked) < 2 else 1       # idle when first counted; held beside the drain
    monkeypatch.setattr(me, "_open_runs", runs)
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "clear"] and w.started == []


def test_an_unreadable_count_beside_the_drain_clears_it_and_refuses(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    asked = []

    def runs(env):
        asked.append(1)
        return 0 if len(asked) < 2 else None
    monkeypatch.setattr(me, "_open_runs", runs)
    with pytest.raises(me.Refused, match="could not read whether runs are in flight.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "clear"] and w.started == []


def test_a_drain_answer_that_cannot_be_read_refuses_and_clears_nothing_it_cannot_name(w, monkeypatch):
    """The first answer never came, so this tool does not know whether a drain was set, nor
    its id. It stops nothing and clears nothing: a drain it cannot name is not its to clear,
    and one that was set ends by its bound."""
    rid = w.release(head(w), "r1")
    calls = []

    def ask(env, on, reason="", **kw):
        calls.append("drain" if on else "clear")
        raise me.Failed("the drain request was not answered: timed out")
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="could not read whether runs are in flight.*ends by itself "
                                         "within 120 s.*Nothing was stopped"):
        _deploy(w, rid)
    assert calls == ["drain"] and w.started == []


def test_a_server_already_draining_for_somebody_else_is_left_alone(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    server.on, server.phase = True, "draining"            # another deployment's drain stands
    with pytest.raises(me.Refused, match="would not drain for this deployment.*that drain was not touched"):
        _deploy(w, rid)
    assert server.calls == ["refused"] and server.on is True and w.started == []


def test_a_drain_the_server_refuses_to_this_tool_stops_nothing(w, monkeypatch):
    """Draining is the owner's. A server that answers 401 to the tool is not stopped on a
    count from outside instead: the safer mechanism exists and was refused."""
    rid = w.release(head(w), "r1")

    def ask(env, on, reason="", **kw):
        raise me.Refused("test: the server refused the request to drain (HTTP 401)")
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="refused the request to drain"):
        _deploy(w, rid)
    assert w.started == []


# -- the bounded wait -----------------------------------------------------------------

def test_waiting_keeps_the_server_draining_until_its_runs_end_then_stops_it(w, monkeypatch):
    rid = w.release(head(w), "r1")
    w.runs["test"] = 2                                 # busy when first counted
    server = Draining(w, monkeypatch, held=[2, 2, 1, 0])
    real = me._drain_ask

    def ask(env, on, reason="", **kw):
        got = real(env, on, reason, **kw)
        if on and got["held"] == 0:
            w.runs["test"] = 0                         # and the server lists none held either
        return got
    monkeypatch.setattr(me, "_drain_ask", ask)
    assert _deploy(w, rid, wait_for_runs=30) == 0
    # asked again while waiting (each ask is what keeps it draining), never cleared, stopped
    assert server.calls == ["drain", "extend", "extend", "extend", "stopping", "stop(draining=True)"]
    assert server.named == [None, TOKEN, TOKEN, TOKEN, TOKEN], "every later call names its drain"
    assert server.phase_at_stop == "stopping"
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_interrupted"] is False and cur["drain"]["used"] is True


def test_a_wait_that_ends_with_runs_still_held_clears_the_drain_and_refuses(w, monkeypatch):
    rid = w.release(head(w), "r1")
    w.serves["test"] = "before"
    w.runs["test"] = 1
    server = Draining(w, monkeypatch, held=[1])
    with pytest.raises(me.Refused, match=r"1 run.s. are in flight.*waited 0 s.*Nothing was stopped"):
        _deploy(w, rid, wait_for_runs=0.05)
    assert server.calls[0] == "drain" and server.calls[-1] == "clear"
    assert set(server.calls[1:-1]) <= {"extend"} and "stop(draining=True)" not in server.calls
    assert server.on is False and w.started == [] and w.serves["test"] == "before"


def test_a_drain_that_is_gone_while_waiting_refuses(w, monkeypatch):
    """The tool's drain ended while it waited (its bound, or somebody's forced clear) and the
    server says the drain it names is not standing: nothing is stopped."""
    rid = w.release(head(w), "r1")
    w.runs["test"] = 1
    server = Draining(w, monkeypatch, held=[1])
    real = me._drain_ask

    def ask(env, on, reason="", **kw):
        if on and server.calls:                       # every ask after the first
            server.calls.append("extend")
            return {"ok": False, "held": 0, "draining": None,
                    "refused": "the drain this call names is not standing"}
        return real(env, on, reason, **kw)
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="no longer draining for this deployment.*Nothing was stopped"):
        _deploy(w, rid, wait_for_runs=5)
    assert "stop(draining=True)" not in server.calls and w.started == []


def test_without_a_wait_runs_in_flight_refuse_at_once_as_before(w, monkeypatch):
    rid = w.release(head(w), "r1")
    w.runs["test"] = 1
    server = Draining(w, monkeypatch, held=[1])
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped: wait"):
        _deploy(w, rid)
    assert server.calls == [], "refused on the first count: the server was never asked to drain"


def test_interrupting_runs_still_needs_the_owners_words_and_does_not_wait(w, monkeypatch):
    rid = w.release(head(w), "r1")
    w.runs["test"] = 1
    server = Draining(w, monkeypatch, held=[1])
    with pytest.raises(me.Refused, match="needs explicit authorization"):
        _deploy(w, rid, interrupt_runs=True, wait_for_runs=30)
    assert _deploy(w, rid, interrupt_runs=True, wait_for_runs=30,
                   owner_approved="the owner: end that run") == 0
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_interrupted"] is True and cur["drain"]["used"] is False
    assert cur["runs_interrupted_rests_on"] == "the owner's words to interrupt runs"
    assert server.calls == ["stop(draining=False)"]


# -- a server without the route ---------------------------------------------------------

def test_a_server_without_the_route_falls_back_to_counting_and_says_so(w, monkeypatch):
    rid = w.release(head(w), "r1")
    asked = []

    def ask(env, on, reason="", **kw):
        asked.append(on)
        return _no_route(env, on)
    monkeypatch.setattr(me, "_drain_ask", ask)
    w.unheld["test"] = {"recorded-under-this-server": 5600.0}
    assert _deploy(w, rid) == 0
    assert asked == [True], "asked once; nothing to clear, because nothing is draining"
    cur = w.cfg.serving("test")["current"]
    assert cur["drain"] == {"used": False,
                            "why": "the server has no drain route (a release from before it)"}
    # exactly as before the drain existed: the read-back cannot exclude that run
    assert cur["runs_interrupted"] is None
    assert cur["runs_not_excluded"] == ["recorded-under-this-server"]


def test_without_a_drain_a_run_at_the_last_count_still_refuses(w, monkeypatch):
    rid = w.release(head(w), "r1")
    monkeypatch.setattr(me, "_drain_ask", _no_route)
    asked = []

    def runs(env):
        asked.append(1)
        return 0 if len(asked) < 2 else 1
    monkeypatch.setattr(me, "_open_runs", runs)
    with pytest.raises(me.Refused, match="1 run.s. started while this was being prepared.*"
                                         "Nothing was stopped.*no drain was available"):
        _deploy(w, rid)
    assert w.started == []


# -- the stopping phase: the drain outlasts the stop ---------------------------------------

def test_the_stopping_duration_is_longer_than_the_sum_of_every_bound_before_the_kill():
    """The numbers, tied together: what the tool asks the server to stay draining for is
    strictly more than the sum of every bounded step of `stop_env` before the backend is
    killed, and the server grants at least that."""
    from mentis.web import drain
    assert me.STOP_BEFORE_KILL_MAX_S == (
        me.IDENTITY_CHECK_TIMEOUT_S + me.FRONT_STOP_TIMEOUT_S
        + me.FRONT_EXIT_WAIT_S + me.IDENTITY_CHECK_TIMEOUT_S + me.FRONT_EXIT_POLL_S
        + me.IDENTITY_CHECK_TIMEOUT_S + me.TASKKILL_TIMEOUT_S
        + me.IDENTITY_CHECK_TIMEOUT_S + me.TASKKILL_TIMEOUT_S) == 276.0
    assert me.STOP_DRAIN_S == me.STOP_BEFORE_KILL_MAX_S + me.STOP_MARGIN_S == 306.0
    assert me.STOP_MARGIN_S > 0 and me.STOP_DRAIN_S > me.STOP_BEFORE_KILL_MAX_S
    assert drain.STOPPING_BOUND_S >= me.STOP_DRAIN_S, "the server would cap the tool's request"
    assert me.STOP_DRAIN_S > drain.BOUND_S, "an ordinary drain would not have covered the stop"


class _SlowStop:
    """`stop_env`'s world at its slowest, on a clock the test owns: EVERY operation it runs
    takes the whole of the timeout it was given, and one given no timeout before the backend
    is killed fails the test. Nothing of `stop_env` is replaced but `run` and the clock."""

    def __init__(self, tmp_path, monkeypatch, times_out=None):
        self.now, self.killed, self.ran, self.times_out = 1000.0, {}, [], times_out
        self.run_dir = tmp_path / "run"
        self.run_dir.mkdir()
        self.brain = tmp_path / "brain"
        (self.run_dir / "launch.json").write_text(json.dumps({
            "brain": str(self.brain),
            "front": {"pid": 11, "start_time": "f",
                      "executable": str(tmp_path / "bin" / "mentis-server.exe")},
            "python": {"pid": 22, "start_time": "p"}}), "utf-8")
        monkeypatch.setattr(me, "run", self.run)
        monkeypatch.setattr(me, "time", types.SimpleNamespace(
            time=lambda: self.now, monotonic=lambda: self.now - 900.0, sleep=self.sleep))
        self.env = {"name": "t", "run_dir": str(self.run_dir), "brain": str(self.brain),
                    "port": 11, "private_port": 12}

    def sleep(self, seconds):
        self.now += seconds

    def run(self, args, check=True, timeout=None, **kw):
        args = [str(a) for a in args]
        what = ("identity" if "Win32_Process -Filter 'ProcessId=" in args[-1] else
                "ports" if "Get-NetTCPConnection" in args[-1] else
                "taskkill" if args[0] == "taskkill" else "front-stop")
        self.ran.append(what)
        if "22" not in self.killed:
            assert timeout is not None, f"{what} runs before the backend is killed with no timeout"
        if what == self.times_out:
            self.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        self.now += timeout or 0.0                       # it took all the time it was given
        out = ""
        if what == "identity":
            pid = args[-1].split("ProcessId=")[1].split("'")[0]
            if pid not in self.killed:
                out = json.dumps({"pid": int(pid), "start_time": {"11": "f", "22": "p"}[pid]})
        elif what == "taskkill":
            self.killed[args[args.index("/PID") + 1]] = self.now - 1000.0
        return types.SimpleNamespace(returncode=1, stdout=out, stderr="")


def test_stop_env_at_its_slowest_kills_the_backend_inside_the_computed_maximum(tmp_path, monkeypatch):
    """Every pre-kill operation takes its maximum, and the front never exits by itself. The
    time to the backend's kill, on the test's clock, is within STOP_BEFORE_KILL_MAX_S, which
    the stopping duration exceeds. Add or lengthen a step before that kill without its bound
    in the sum, or leave one without a timeout, and this fails."""
    world = _SlowStop(tmp_path, monkeypatch)
    said = me.stop_env(None, world.env)
    assert "front did not exit on its own and was killed" in said
    assert set(world.killed) == {"11", "22"}
    to_the_kill = world.killed["22"]
    slack = me.IDENTITY_CHECK_TIMEOUT_S + me.FRONT_EXIT_POLL_S      # where the wait's last look falls
    assert me.STOP_BEFORE_KILL_MAX_S - slack <= to_the_kill <= me.STOP_BEFORE_KILL_MAX_S, to_the_kill
    assert to_the_kill < me.STOP_DRAIN_S
    before = world.ran[:len(world.ran) - world.ran[::-1].index("taskkill")]
    assert before[0] == "identity" and before[1] == "front-stop" and before.count("taskkill") == 2
    assert set(before) == {"identity", "front-stop", "taskkill"}


@pytest.mark.parametrize("step", ["identity", "front-stop", "taskkill"])
def test_a_step_of_the_stop_that_runs_out_of_its_time_fails_the_stop(tmp_path, monkeypatch, step):
    """A bounded step that does not finish is a FAILED stop, said as one: never a hang, and
    never taken for the process being gone or still there."""
    world = _SlowStop(tmp_path, monkeypatch, times_out=step)
    with pytest.raises(me.Failed, match="within .* s"):
        me.stop_env(None, world.env)
    assert "22" not in world.killed
    assert (world.run_dir / "launch.json").is_file(), "not recorded as stopped"


def test_a_run_held_when_the_stop_is_about_to_begin_clears_the_drain_and_stops_nothing(w, monkeypatch):
    """Quiet when drained, and something is held at the very last answer: the server refuses
    to mark itself as stopping, the drain is cleared and nothing is stopped."""
    rid = w.release(head(w), "r1")
    w.serves["test"] = "before"
    server = Draining(w, monkeypatch)
    server.held_at_stop = 1
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and server.on is False
    assert server.named == [None, TOKEN, TOKEN]
    assert w.started == [] and w.serves["test"] == "before"


def test_a_server_that_would_not_stay_draining_long_enough_is_not_stopped(w, monkeypatch):
    """Judged on the DURATION the server states (`lasts_s`), not on wall-clock stamps."""
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    server.grants = me.STOP_BEFORE_KILL_MAX_S          # not strictly longer than the stop
    with pytest.raises(me.Refused, match="would stay draining for .* Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and w.started == []


def test_wall_clock_stamps_in_the_answer_do_not_decide_whether_the_stop_is_covered(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    real = me._drain_ask

    def ask(env, on, reason="", stopping_s=None, **kw):
        got = real(env, on, reason, stopping_s=stopping_s, **kw)
        if stopping_s:                                 # stamps that claim an hour; a short duration
            got["at"], got["draining"]["expires_at"], got["draining"]["lasts_s"] = 0.0, 3600.0, 5.0
        return got
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="would stay draining for 5.0 s"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and w.started == []


def test_a_server_that_does_not_say_it_is_stopping_is_not_stopped(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    real = me._drain_ask

    def ask(env, on, reason="", stopping_s=None, **kw):
        got = real(env, on, reason, stopping_s=stopping_s, **kw)
        if stopping_s:
            got["draining"]["phase"] = "draining"      # a server that ignored the request
        return got
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="did not enter its stopping phase.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and w.started == []


# -- nothing that fails leaves a server draining -----------------------------------------

def test_a_stop_that_refuses_before_touching_anything_clears_the_drain(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)

    def stop(c, e):
        server.calls.append(f"stop(draining={server.on})")
        raise me.Refused("its ports are held but there is no launch.json")
    monkeypatch.setattr(me, "stop_env", stop)
    with pytest.raises(me.Refused, match="no launch.json"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "stop(draining=True)", "clear"] and server.on is False
    assert w.started == []


def test_a_stop_that_began_and_did_not_finish_leaves_the_server_draining_and_says_so(w, monkeypatch):
    """A step of the stop ran out of its time: what is still running is not known. A server
    that may be half stopped is NOT told to take work again. Its drain stands until its bound
    and then ends, and the failure says exactly that; nothing is started."""
    rid = w.release(head(w), "r1")
    w.serves["test"] = "before"
    server = Draining(w, monkeypatch)

    def stop(c, e):
        server.calls.append(f"stop(draining={server.on})")
        raise me.Failed("killing the recorded process tree 22 did not finish within 30 s, so the "
                        "stop was abandoned part way: what is still running is not known")
    monkeypatch.setattr(me, "stop_env", stop)
    with pytest.raises(me.Failed, match=r"the stop did not finish.*NOT KNOWN.*stays draining "
                                        r"\(stopping\).*at most 306 s.*then takes work again by itself"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "stop(draining=True)"], "not cleared"
    assert server.on is True and server.phase == "stopping"
    assert w.started == [] and w.cfg.serving("test").get("current") is None


def test_anything_failing_between_the_drain_and_the_stop_clears_it(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)

    def boom(env):
        raise KeyboardInterrupt()
    monkeypatch.setattr(me, "_server_started", boom)
    with pytest.raises(KeyboardInterrupt):
        _deploy(w, rid)
    assert server.calls == ["drain", "clear"] and server.on is False and w.started == []


def test_a_clear_that_cannot_reach_the_server_does_not_hide_the_refusal(w, monkeypatch):
    """The tool's clear is the first of two ways a drain ends; the server's own bound is the
    other. A clear that fails changes nothing about what is reported."""
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch, held=[3])
    server.fail_clear = True
    with pytest.raises(me.Refused, match="3 run.s. are in flight.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "clear"] and w.started == []


# -- the request itself, against a real socket -------------------------------------------

@pytest.fixture
def answering():
    """A local HTTP server that answers the drain route as told."""
    said = {"status": 200, "seen": [],
            "body": {"ok": True, "held": 0, "drain": "abc", "draining": {"since": 1.0}}}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            said["seen"].append((self.path, body, self.headers.get("X-Mentis-Client"),
                                 self.headers.get("Authorization")))
            raw = said["body"] if isinstance(said["body"], bytes) else json.dumps(said["body"]).encode()
            self.send_response(said["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    said["env"] = {"name": "fake", "port": httpd.server_address[1]}
    yield said
    httpd.shutdown()
    httpd.server_close()


def test_the_request_is_the_owners_route_and_its_answers_are_read_strictly(answering, monkeypatch):
    env = answering["env"]
    monkeypatch.setenv("MENTIS_OWNER_TOKEN", "the-owners-session")
    got = me._drain_ask(env, True, "deployment of r1")
    assert got["held"] == 0 and got["drain"] == "abc"
    assert answering["seen"][-1] == ("/api/server/drain", {"on": True, "reason": "deployment of r1"},
                                     "1", "Bearer the-owners-session")
    # every later call names the drain: extend, stopping, clear
    me._drain_ask(env, True, "deployment of r1", token="abc")
    assert answering["seen"][-1][1] == {"on": True, "reason": "deployment of r1", "drain": "abc"}
    me._drain_ask(env, True, "deployment of r1", stopping_s=306.0, token="abc")
    assert answering["seen"][-1][1] == {"on": True, "reason": "deployment of r1", "stopping": True,
                                        "seconds": 306.0, "drain": "abc"}
    answering["body"] = {"ok": True, "cleared": True, "held": 0, "draining": None}
    assert me._drain_clear(env, "abc") == "cleared"
    assert answering["seen"][-1][1] == {"on": False, "drain": "abc"}, "never a forced clear"
    # a clear the server did not act on is said, not taken for done
    answering["body"] = {"ok": False, "cleared": False, "held": 0, "draining": {"since": 9.0},
                         "refused": "another drain is standing"}
    assert me._drain_clear(env, "abc") == "was not this tool's to clear any more (another drain is standing)"
    n = len(answering["seen"])
    assert me._drain_clear(env, None).startswith("was never known to be set")
    assert len(answering["seen"]) == n, "with no id there is nothing this tool may clear"
    # 404: a release from before the drain. Nothing is draining: fall back
    answering["status"] = 404
    with pytest.raises(me._NoDrain):
        me._drain_ask(env, True, "r")
    # 401: the server has the route and this tool is not the owner to it
    answering["status"] = 401
    with pytest.raises(me.Refused, match="MENTIS_OWNER_TOKEN"):
        me._drain_ask(env, True, "r")
    # anything else is not an answer, and is never read as zero held
    answering["status"] = 500
    with pytest.raises(me.Failed):
        me._drain_ask(env, True, "r")
    answering["status"] = 200
    for body in ({"ok": True}, {"ok": True, "held": None, "draining": {}, "drain": "a"},
                 {"ok": True, "held": True, "draining": {}, "drain": "a"},
                 {"ok": True, "held": 0, "draining": None, "drain": "a"},
                 {"ok": True, "held": 0, "draining": {}},                     # no id for the drain
                 {"held": 0, "draining": {}, "drain": "a"},                    # does not say ok
                 b"not json", []):
        answering["body"] = body
        with pytest.raises(me.Failed):
            me._drain_ask(env, True, "r")
    # an answer for another drain than the one named is not this tool's answer
    answering["body"] = {"ok": True, "held": 0, "draining": {}, "drain": "other"}
    with pytest.raises(me.Failed):
        me._drain_ask(env, True, "r", token="abc")
    assert me._drain_clear({"name": "fake", "port": 1}, "abc").startswith("could not be cleared")


def test_wait_for_runs_is_an_option_of_every_switching_command(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(me, "Config", lambda path: object())
    for cmd, argv in (("deploy", ["deploy", "test", "r1"]), ("promote", ["promote", "r1"]),
                      ("production", ["production", "r1"]), ("rollback", ["rollback", "test"])):
        monkeypatch.setattr(me, f"cmd_{cmd}", lambda cfg, a, cmd=cmd: seen.update({cmd: a.wait_for_runs}) or 0)
        assert me.main([*argv, "--wait-for-runs", "45"]) == 0 and seen[cmd] == 45.0
        assert me.main(argv) == 0 and seen[cmd] == 0.0, "the default refuses at once"
    assert set(seen) == {"deploy", "promote", "production", "rollback"}


# -- the tool against the real server route ----------------------------------------------

from tests._loop import world  # noqa: E402,F401


def test_the_tool_drains_a_real_server_through_its_owner_route(world):
    """`drain_to_quiet`, `drain_for_the_stop` and `_drain_clear` against the real handler: the
    requests the tool sends are ones the server takes, and its answers ones the tool reads."""
    from mentis.web import drain
    st = world["state"]
    env = {"name": "fixture", "port": int(world["base"].rsplit(":", 1)[1])}
    got = me.drain_to_quiet(env, "deployment of r1: candidate deployed for testing")
    assert got["used"] is True and got["held"] == 0 and got["starts_refused"] == 0
    token = got["id"]
    now = drain.read(st)["draining"]
    assert now["reason"] == "deployment of r1: candidate deployed for testing"
    assert now["since"] == got["since"] and st.drain["draining"]["id"] == token
    # a second deployment finds it standing and leaves it alone
    with pytest.raises(me.Refused, match="would not drain for this deployment.*not touched"):
        me.drain_to_quiet(env, "another deployment")
    assert st.drain["draining"]["id"] == token
    # the tool clears its own, and only its own
    assert me._drain_clear(env, "not-this-one").startswith("was not this tool's to clear any more")
    assert drain.read(st)["draining"] is not None
    assert me._drain_clear(env, token) == "cleared" and drain.read(st)["draining"] is None
    # a dispatch the server has admitted is what the tool is told is held, and it clears
    assert drain.admit(st) is None
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        me.drain_to_quiet(env, "deployment of r1")
    assert drain.read(st) == {"draining": None, "held": 1}, "cleared by the tool's finally"
    drain.leave(st)
    # THE STOPPING PHASE, against the real route
    token = me.drain_to_quiet(env, "deployment of r1")["id"]
    assert drain.admit(st) is not None                       # a start meets the drain
    st.drain["admitted"] = 1                                 # and one is held after all
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        me.drain_for_the_stop(env, "deployment of r1", token)
    assert drain.read(st)["draining"]["phase"] == "draining", "refused: nothing changed"
    st.drain["admitted"] = 0
    got = me.drain_for_the_stop(env, "deployment of r1", token)
    assert got["phase"] == "stopping"
    assert me.STOP_BEFORE_KILL_MAX_S < got["stopping_lasts_seconds"] <= me.STOP_DRAIN_S
    now = drain.read(st)["draining"]
    assert now["phase"] == "stopping" and me.STOP_BEFORE_KILL_MAX_S < now["lasts_s"] <= me.STOP_DRAIN_S
    assert me._drain_clear(env, token) == "cleared" and drain.read(st)["draining"] is None
