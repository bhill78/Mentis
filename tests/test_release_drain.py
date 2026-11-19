"""The release tool drains a server before it stops it (`tools/env/mentis_env.py`, `switch`).

The server side is `tests/test_server_drain.py`. Here the server is a fake that answers the
drain request as the real one does: the flag, and `held`, read in one moment. What is tested:
the server is stopped while it is still draining and only once it holds nothing, in its
stopping phase, whose bound is longer than the stop can take; with runs held the drain is
CLEARED and the switch refused, nothing stopped; the bounded wait; a server without the route
falls back to counting and says so; and nothing that fails before the stop leaves a server
draining.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_release_contract import Args, head, me, w  # noqa: F401


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

    def ask(self, env, on, reason="", stopping_s=None):
        assert env["name"] == self.name
        if not on:
            self.calls.append("clear")
            if self.fail_clear:
                raise me.Failed("the server went away")
            self.on, self.phase = False, None
            return {"ok": True, "draining": None, "held": 0}
        if stopping_s:
            self.calls.append("stopping")
            self.asked_to_stay = stopping_s
            now = {"since": 100.0, "by": "@brian", "reason": reason, "phase": self.phase,
                   "expires_at": 220.0, "refused": 0, "refused_starts": []}
            if self.held_at_stop:
                return {"ok": False, "held": self.held_at_stop, "at": 150.0, "draining": now,
                        "stopping_refused": f"{self.held_at_stop} dispatch(es) are held"}
            self.phase = "stopping"
            lasts = stopping_s if self.grants is None else self.grants
            return {"ok": True, "held": 0, "at": 150.0,
                    "draining": {**now, "phase": "stopping", "expires_at": 150.0 + lasts}}
        self.calls.append("extend" if self.on else "drain")
        self.on, self.reason, self.phase = True, reason, self.phase or "draining"
        held = self.held.pop(0) if len(self.held) > 1 else self.held[0]
        return {"ok": True, "held": held, "bound_s": 120.0, "draining": {
            "since": 100.0, "by": "@brian", "reason": reason, "expires_at": 220.0,
            "phase": self.phase,
            "refused": len(self.refused), "refused_starts": list(self.refused)}}


def _deploy(w, rid, **kw):
    return me.cmd_deploy(w.cfg, Args(environment="test", release=rid, **kw))


# -- quiet: stopped while still draining ----------------------------------------------

def test_a_quiet_server_is_drained_and_stopped_while_it_is_still_draining(w, monkeypatch, capsys):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    w.unheld["test"] = {"recorded-under-this-server": 5600.0}     # what a read-back would doubt
    assert _deploy(w, rid) == 0
    assert server.calls == ["drain", "stopping", "stop(draining=True)"], "never cleared: it was stopped"
    assert server.phase_at_stop == "stopping" and server.asked_to_stay == me.STOP_DRAIN_S
    assert server.reason.startswith("deployment of r1")
    cur = w.cfg.serving("test")["current"]
    # NO RUN WAS INTERRUPTED, on the server's own answer: nothing was held and nothing could
    # start. The run a read-back alone could not exclude is excluded by that answer
    assert cur["runs_interrupted"] is False and cur["runs_in_flight"] == 0
    assert cur["runs_not_excluded"] == [] and cur["runs_ended_by_restart"] == []
    d = cur["drain"]
    assert d["used"] is True and d["held"] == 0 and d["by"] == "@brian"
    assert d["phase"] == "stopping" and d["stopping_lasts_seconds"] == me.STOP_DRAIN_S
    assert d["stop_before_kill_max_seconds"] == me.STOP_BEFORE_KILL_MAX_S
    assert cur["runs_interrupted_rests_on"].startswith("the server's own answer: nothing held, and stopping")
    assert cur["runs_interrupted_rests_on"].endswith("the record read back agrees")
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
    because the server was stopped in its stopping phase, and the record says that is what
    it rests on. Without that phase the same doubt is reported as not known."""
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    w.unheld["test"] = None
    assert _deploy(w, rid) == 0
    cur = w.cfg.serving("test")["current"]
    assert server.phase_at_stop == "stopping"
    assert cur["runs_interrupted"] is False and cur["drain"]["read_back"] == "could not be read"
    assert cur["runs_interrupted_rests_on"] == (
        "the server's own answer: nothing held, and stopping (draining until after it was "
        "stopped); the record could not be read back")
    # the same doubt with no drain at all
    w.release(head(w), "r2", mars=b"mars-2")
    monkeypatch.setattr(me, "_drain_ask", lambda env, on, reason="", stopping_s=None: (
        _ for _ in ()).throw(me._NoDrain("the server has no drain route (a release from before it)")))
    assert _deploy(w, "r2") == 0
    cur = w.cfg.serving("test")["current"]
    assert cur["runs_interrupted"] is None
    assert cur["runs_interrupted_rests_on"] == "nothing: the record could not be read back and no drain was used"


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


def test_a_drain_answer_that_cannot_be_read_clears_and_refuses(w, monkeypatch):
    rid = w.release(head(w), "r1")
    calls = []

    def ask(env, on, reason="", stopping_s=None):
        calls.append("drain" if on else "clear")
        if on:
            raise me.Failed("the drain request was not answered: timed out")
        return {"ok": True, "draining": None, "held": 0}
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="could not read whether runs are in flight.*Nothing was stopped"):
        _deploy(w, rid)
    assert calls == ["drain", "clear"] and w.started == []


def test_a_drain_the_server_refuses_to_this_tool_stops_nothing(w, monkeypatch):
    """Draining is the owner's. A server that answers 401 to the tool is not stopped on a
    count from outside instead: the safer mechanism exists and was refused."""
    rid = w.release(head(w), "r1")

    def ask(env, on, reason="", stopping_s=None):
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

    def ask(env, on, reason="", stopping_s=None):
        got = real(env, on, reason, stopping_s)
        if on and got["held"] == 0:
            w.runs["test"] = 0                         # and the server lists none held either
        return got
    monkeypatch.setattr(me, "_drain_ask", ask)
    assert _deploy(w, rid, wait_for_runs=30) == 0
    # asked again while waiting (each ask is what keeps it draining), never cleared, stopped
    assert server.calls == ["drain", "extend", "extend", "extend", "stopping", "stop(draining=True)"]
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
    assert server.calls == ["stop(draining=False)"]


# -- a server without the route ---------------------------------------------------------

def test_a_server_without_the_route_falls_back_to_counting_and_says_so(w, monkeypatch):
    rid = w.release(head(w), "r1")
    asked = []

    def ask(env, on, reason="", stopping_s=None):
        asked.append(on)
        raise me._NoDrain("the server has no drain route (a release from before it)")
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
    monkeypatch.setattr(me, "_drain_ask", lambda env, on, reason="", stopping_s=None: (
        _ for _ in ()).throw(me._NoDrain("the server has no drain route (a release from before it)")))
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

def test_the_stopping_bound_is_longer_than_the_stop_can_take_to_kill_the_backend():
    """The numbers, tied together: what the tool asks the server to stay draining for is
    strictly more than `stop_env` can take before the backend is killed, and the server
    grants at least that."""
    from mentis.web import drain
    assert me.STOP_BEFORE_KILL_MAX_S == me.FRONT_STOP_TIMEOUT_S + me.FRONT_EXIT_WAIT_S
    assert me.STOP_DRAIN_S == me.STOP_BEFORE_KILL_MAX_S + me.STOP_MARGIN_S
    assert me.STOP_MARGIN_S >= 30 and me.STOP_DRAIN_S > me.STOP_BEFORE_KILL_MAX_S
    assert drain.STOPPING_BOUND_S >= me.STOP_DRAIN_S, "the server would cap the tool's request"
    assert me.STOP_DRAIN_S > drain.BOUND_S, "an ordinary drain would not have covered the stop"


def test_stop_env_kills_the_backend_within_what_the_stopping_bound_was_computed_from(
        tmp_path, monkeypatch):
    """`stop_env` itself, at its slowest: the front's stop command uses its whole timeout and
    the front never exits by itself. The time until the backend is killed is measured on a
    clock the test owns. Lengthen or add a wait before that kill without the constants, and
    this fails."""
    import types
    clock = {"now": 1000.0}
    killed = {}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    brain = tmp_path / "brain"
    (run_dir / "launch.json").write_text(json.dumps({
        "brain": str(brain),
        "front": {"pid": 11, "start_time": "f", "executable": str(tmp_path / "bin" / "mentis-server.exe")},
        "python": {"pid": 22, "start_time": "p"}}), "utf-8")

    def run(args, **kw):
        args = [str(a) for a in args]
        if "stop" in args and "--front" in args:
            assert kw["timeout"] == me.FRONT_STOP_TIMEOUT_S
            clock["now"] += kw["timeout"]                 # it used all of its timeout
        elif args[0] == "taskkill":
            killed[args[args.index("/PID") + 1]] = clock["now"] - 1000.0
        return types.SimpleNamespace(returncode=1, stdout="", stderr="")

    def sleep(seconds):
        clock["now"] += seconds
    monkeypatch.setattr(me, "run", run)
    monkeypatch.setattr(me, "time", types.SimpleNamespace(time=lambda: clock["now"], sleep=sleep))
    monkeypatch.setattr(me, "_still", lambda pid, start_time: str(pid) not in killed)
    monkeypatch.setattr(me, "port_owner", lambda port: None)
    said = me.stop_env(None, {"name": "t", "run_dir": str(run_dir), "brain": str(brain),
                              "port": 11, "private_port": 12})
    assert "front did not exit on its own and was killed" in said
    assert set(killed) == {"11", "22"}
    assert me.STOP_BEFORE_KILL_MAX_S - 1 <= killed["22"] <= me.STOP_BEFORE_KILL_MAX_S, killed
    assert killed["22"] < me.STOP_DRAIN_S


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
    assert w.started == [] and w.serves["test"] == "before"


def test_a_server_that_would_not_stay_draining_long_enough_is_not_stopped(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    server.grants = me.STOP_BEFORE_KILL_MAX_S          # not strictly longer than the stop
    with pytest.raises(me.Refused, match="would stay draining for .* Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and w.started == []


def test_a_server_that_does_not_say_it_is_stopping_is_not_stopped(w, monkeypatch):
    rid = w.release(head(w), "r1")
    server = Draining(w, monkeypatch)
    real = me._drain_ask

    def ask(env, on, reason="", stopping_s=None):
        got = real(env, on, reason, stopping_s)
        if stopping_s:
            got["draining"]["phase"] = "draining"      # a server that ignored the request
        return got
    monkeypatch.setattr(me, "_drain_ask", ask)
    with pytest.raises(me.Refused, match="did not enter its stopping phase.*Nothing was stopped"):
        _deploy(w, rid)
    assert server.calls == ["drain", "stopping", "clear"] and w.started == []


# -- nothing that fails leaves a server draining -----------------------------------------

def test_a_stop_that_fails_after_the_drain_clears_it(w, monkeypatch):
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
    said = {"status": 200, "body": {"ok": True, "held": 0, "draining": {"since": 1.0}}, "seen": []}

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
    assert got["held"] == 0
    assert answering["seen"][-1] == ("/api/server/drain", {"on": True, "reason": "deployment of r1"},
                                     "1", "Bearer the-owners-session")
    answering["body"] = {"ok": True, "held": 0, "draining": None}
    assert me._drain_ask(env, False)["draining"] is None
    assert answering["seen"][-1][1] == {"on": False}
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
    for body in ({"ok": True}, {"held": None, "draining": {}}, {"held": True, "draining": {}},
                 {"held": 0, "draining": None}, b"not json", []):
        answering["body"] = body
        with pytest.raises(me.Failed):
            me._drain_ask(env, True, "r")
    assert me._drain_clear({"name": "fake", "port": 1}).startswith("could not be cleared")


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
    """`drain_to_quiet` and `_drain_clear` against the real handler: the request the tool
    sends is one the server takes, and the answer is one the tool reads."""
    from mentis.web import drain
    st = world["state"]
    env = {"name": "fixture", "port": int(world["base"].rsplit(":", 1)[1])}
    got = me.drain_to_quiet(env, "deployment of r1: candidate deployed for testing")
    assert got["used"] is True and got["held"] == 0 and got["starts_refused"] == 0
    now = drain.read(st)["draining"]
    assert now["reason"] == "deployment of r1: candidate deployed for testing"
    assert now["since"] == got["since"]
    # a dispatch the server has admitted is what the tool is told is held, and it clears
    assert drain.request(st, on=False, by="t")["draining"] is None
    assert drain.admit(st) is None
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        me.drain_to_quiet(env, "deployment of r1")
    assert drain.read(st) == {"draining": None, "held": 1}, "cleared by the tool's finally"
    # THE STOPPING PHASE, against the real route: refused with something held, nothing changed
    assert drain.read(st)["draining"] is None
    with pytest.raises(me.Refused, match="1 run.s. are in flight.*Nothing was stopped"):
        me.drain_for_the_stop(env, "deployment of r1")
    assert drain.read(st) == {"draining": None, "held": 1}
    drain.leave(st)
    assert me.drain_to_quiet(env, "deployment of r1")["used"] is True
    got = me.drain_for_the_stop(env, "deployment of r1")
    assert got["phase"] == "stopping" and got["stopping_lasts_seconds"] == me.STOP_DRAIN_S
    now = drain.read(st)["draining"]
    assert now["phase"] == "stopping" and now["expires_at"] == got["stopping_until"]
    assert now["expires_at"] - got["stopping_at"] > me.STOP_BEFORE_KILL_MAX_S > drain.BOUND_S
    assert me._drain_clear(env) == "cleared" and drain.read(st)["draining"] is None
