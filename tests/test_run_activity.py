"""A run's live feed, what it is doing now, Stop and its permission policy.

`mentis.core.run_feed` (the bounded feed Fluid's run panel reads),
`mentis.web.permissions.standing_answer` (what a run's own grant answers),
and the `/api/runs/<run>/feed|stop` routes for a run this server does not
hold. The MARS side of permissions is in test_execution_mars.py.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from mentis.core import run_feed
from mentis.core.run_feed import RunFeed
from mentis.conversation.owner import _owner
from mentis.web.permissions import standing_answer
from tests._loop import world  # noqa: F401


def test_chunks_join_and_move_to_the_end():
    f = RunFeed()
    f.add("agent_message_chunk", {"text": "Hel"}, 1.0)
    f.add("agent_message_chunk", {"text": "lo"}, 2.0)
    first = f.since(0)
    assert [(e["kind"], e["text"]) for e in first] == [("message", "Hello")]
    seen = f.seq
    f.add("tool_call", {"tool_call_id": "t1", "title": "Read AGENTS.md",
                        "kind": "read", "status": "in_progress"}, 3.0)
    assert f.activity == "Read AGENTS.md"
    f.add("tool_call_update", {"tool_call_id": "t1", "status": "completed",
                               "raw_output": "x" * 5000}, 4.0)
    new = f.since(seen)
    assert [e["id"] for e in new] == ["tool-t1"]
    assert new[0]["status"] == "completed" and new[0]["title"] == "Read AGENTS.md"
    assert len(new[0]["raw_output"]) <= run_feed.FIELD_KEPT + 1
    # a new message after a tool is a new entry, not the old one continued
    f.add("agent_message_chunk", {"text": "Done."}, 5.0)
    assert [e["kind"] for e in f.since(0)] == ["message", "tool", "message"]
    assert f.activity == "Writing"


def test_plan_step_is_the_activity_unless_a_tool_runs():
    f = RunFeed()
    f.add("plan", {"entries": [{"content": "Run tests", "status": "in_progress"},
                               {"content": "Report", "status": "pending"}]}, 1.0)
    assert f.activity == "Run tests"
    f.add("tool_call", {"tool_call_id": "a", "title": "npm test", "status": "in_progress"}, 2.0)
    f.add("plan", {"entries": [{"content": "Report", "status": "in_progress"}]}, 3.0)
    assert f.activity == "npm test"
    assert [e["kind"] for e in f.since(0)] == ["tool", "plan"]


def test_feed_is_bounded():
    f = RunFeed()
    for i in range(run_feed.KEPT + 50):
        f.add("tool_call", {"tool_call_id": str(i), "title": f"t{i}", "status": "completed"}, i)
    got = f.since(0)
    assert len(got) == run_feed.KEPT and got[0]["id"] == "tool-50"


OPTS = [{"option_id": "once", "kind": "allow_once", "name": "Allow once"},
        {"option_id": "no", "kind": "reject_once", "name": "Reject"}]


def test_the_runs_grant_answers_reads_and_workspace_edits(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    ask = lambda tool: standing_answer({"tool_call": tool, "options": OPTS}, str(ws))  # noqa: E731
    assert ask({"kind": "read", "title": "Read C:/anything"}) == "once"
    assert ask({"kind": "edit", "locations": [{"path": str(ws / "a.py")}]}) == "once"
    # everything else is the owner's
    assert ask({"kind": "edit", "locations": [{"path": str(tmp_path / "out.py")}]}) is None
    assert ask({"kind": "edit"}) is None
    assert ask({"kind": "execute", "title": "npm test"}) is None
    assert ask({"kind": "delete", "locations": [{"path": str(ws / "a.py")}]}) is None


def _get(world, path):
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_a_run_not_held_here_has_no_feed(world):
    got = _get(world, "/api/runs/nope/feed?after=3")
    assert got["held_here"] is False and got["events"] == [] and got["next"] == 3


def test_stop_needs_a_recorded_run(world):
    req = urllib.request.Request(world["base"] + "/api/runs/nope/stop", data=b"{}",
                                 method="POST", headers={"X-Mentis-Client": "1",
                                                         "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        raise AssertionError("stopped an unrecorded run")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_workspace_edits_that_become_commands_are_the_owners(tmp_path):
    """Git hooks and config, agent and editor settings: inside the workspace,
    still the owner's (they would run code, or widen the agent's authority,
    later). A relative path is resolved against nothing the run names."""
    ws = tmp_path / "ws"
    ws.mkdir()
    ask = lambda path: standing_answer(  # noqa: E731
        {"tool_call": {"kind": "edit", "locations": [{"path": path}]}, "options": OPTS},
        str(ws))
    for guarded in (".git/hooks/pre-commit", ".git/config", ".claude/settings.json",
                    ".mcp.json", ".vscode/tasks.json", "sub/.git/config",
                    ".GitHub/workflows/x.yml"):
        assert ask(str(ws / guarded)) is None, guarded
    assert ask(str(ws / "src" / "app.py")) == "once"
    assert ask("src/app.py") is None


def test_feed_read_is_one_moment():
    f = RunFeed()
    f.add("tool_call", {"tool_call_id": "a", "title": "Run tests", "status": "in_progress"}, 1.0)
    events, seq, activity, _ = f.read(0)
    assert seq == events[-1]["seq"] and activity == "Run tests"
    f.add("tool_call_update", {"tool_call_id": "a", "status": "completed"}, 2.0)
    later, seq2, _, _ = f.read(seq)
    assert [e["status"] for e in later] == ["completed"] and seq2 > seq


def test_a_stopped_session_is_worded_stopped_not_failed():
    from mentis.operational.runs import run_state
    start = {"id": "r", "execution": "i", "runtime": "claude", "at": 1.0}
    end = {"id": "e", "act": "delivery-failed", "at": 2.0,
           "because": "terminal 'cancelled', exit None: the turn ended with "
                      "stop reason 'cancelled'"}
    got = run_state(start, end)
    assert got["state"] == "stopped" and "stays open" in got["words"]
    other = run_state(start, {**end, "because": "backend_exited: boom"})
    assert other["state"] == "failed"


def _start(cv, who, conversation, instance, turn=None):
    """A run as dispatch opens it: its start act, then held by this process."""
    return cv.record_act(actor=who, act="execution-started",
                         conversation=conversation, turn=turn,
                         execution=instance, runtime="fake",
                         because="test run")


def test_working_scans_participants_once_for_its_repeated_owner_reads(
        world, monkeypatch):
    """The route asks for the owner through run consent several times, but
    one HTTP read resolves it from the participant rows once."""
    cv, corpus = world["cv"], world["state"].corpus
    owner = world["who"]["@brian"]
    conversation = world["conversations"]["design"]
    turn = cv.turns(conversation)[0]["turn"]
    request = cv.expect(turn, of=world["steward"], kind="result", by=owner)
    cv.record_act(actor=world["steward"], act="execution-started",
                  conversation=conversation, turn=turn, caused_by=request,
                  execution="owner-scan", runtime="fake",
                  because="exercise the working read")

    calls = []
    real = type(corpus).entries_of_kind

    def counted(self, kind, *args, **kwargs):
        if self is corpus and kind == "participant":
            calls.append(kind)
        return real(self, kind, *args, **kwargs)

    monkeypatch.setattr(type(corpus), "entries_of_kind", counted)

    # Outside a read scope, every call still reads exactly as it did before.
    assert [_owner(cv) for _ in range(3)] == [owner] * 3
    assert len(calls) == 3

    calls.clear()
    got = _get(world, "/api/working")
    assert any(row["expectation"] == request for row in got["open"])
    assert calls == ["participant"]


def test_activity_is_per_run_and_says_where_each_run_is(world):
    """Two runs of one Participant are two runs, each in ITS conversation;
    a conversation's working count is its own runs only, and says whose
    (the owner, 2026-10-27: work from other conversations showed in this
    one's indicators, and two @Caretaker runs were one)."""
    from tests._loop import a_conversation
    cv, st = world["cv"], world["state"]
    a, b = a_conversation(world, "Here"), a_conversation(world, "Elsewhere")
    care = world["steward"]
    runs = [_start(cv, care, a, "inst-1"), _start(cv, care, a, "inst-2"),
            _start(cv, care, b, "inst-3")]
    for i, r in enumerate(runs, 1):
        st.agents.agents_open_run(f"inst-{i}", r)
    # an open run nobody here holds is not somebody working
    _start(cv, care, b, "inst-4")

    rows = {r["participant"]: r for r in _get(world, "/api/activity")["activity"]}
    mine = rows[care]
    assert mine["has_live_execution"] is True
    by_run = {r["run"]: r for r in mine["runs"]}
    assert set(runs) <= set(by_run)
    assert [by_run[r]["conversation"] for r in runs] == [a, a, b]
    assert all(by_run[r]["live"] for r in runs)
    assert sum(1 for r in mine["runs"] if not r["live"]) == 1

    listed = {c["id"]: c for c in _get(
        world, "/fluid/api/conversations?activity=1&limit=40")["conversations"]}
    assert listed[a]["working"] == 2 and listed[b]["working"] == 1
    assert sorted(w["run"] for w in listed[a]["workers"]) == sorted(runs[:2])
    assert {w["participant"] for w in listed[a]["workers"]} == {care}
    assert listed[b]["workers"][0]["alias"] == "Steward"
    one = _get(world, f"/fluid/api/conversations?ids={a}")["conversations"][0]
    assert one["working"] == 2

    # a run that returned here is no longer working, before its end is recorded
    st.agents._runs[runs[0]]["ended_at"] = 1.0
    listed = {c["id"]: c for c in _get(
        world, "/fluid/api/conversations?activity=1&limit=40")["conversations"]}
    assert listed[a]["working"] == 1


def test_a_run_says_its_persona_and_the_task_gravity_in_force(world):
    """Fluid's run details read Participant · Persona · runtime · Task
    Gravity (operating-model §6). The Persona is the one its grant carried,
    else its request's assignment; Task Gravity is the ORIGINAL request's
    permission with the run's generation below it -- a finding pursued under
    a depth-2 trunk is generation 1 of 2, never a fresh "ask"."""
    from tests._loop import a_conversation, say
    cv, care, persona = world["cv"], world["steward"], world["persona"]
    owner = world["who"]["@brian"]
    cid = a_conversation(world, "Gravity")
    turn = say(world, cid, "look into it")["turn"]
    trunk = cv.expect(turn, of=care, kind="result", by=owner,
                      detail={"follow_up": {"depth": 2}})
    cv.record_act(actor=owner, act="expectation-assigned", conversation=cid,
                  turn=turn, caused_by=trunk, about=[trunk],
                  detail={"carrier": care, "persona": persona})
    worn = cv.record_act(actor=care, act="execution-started", conversation=cid,
                         turn=turn, execution="inst-g1", runtime="fake",
                         caused_by=trunk, because="test run")
    found = cv.expect(turn, of=care, kind="result", by=care, caused_by=trunk)
    cv.record_act(actor=care, act="work-discovered", conversation=cid,
                  turn=turn, caused_by=trunk, about=[found])
    side = cv.record_act(actor=care, act="execution-started", conversation=cid,
                         turn=turn, execution="inst-g2", runtime="fake",
                         caused_by=found, because="test run",
                         detail={"authority": {"persona": None}})
    plain = cv.expect(turn, of=care, kind="result", by=owner)
    asks = cv.record_act(actor=care, act="execution-started", conversation=cid,
                         turn=turn, execution="inst-g3", runtime="fake",
                         caused_by=plain, because="test run")

    got = {r["id"]: r for r in _get(
        world, f"/fluid/api/runs?ids={worn},{side},{asks}")["runs"]}
    assert got[worn]["persona"] == persona
    assert got[worn]["persona_name"] == "Steward"
    assert got[worn]["follow_up"] == {"depth": 2}
    assert got[worn]["generation"] == 0 and got[worn]["runtime"] == "fake"
    assert got[side]["follow_up"] == {"depth": 2}
    assert got[side]["generation"] == 1 and got[side]["persona"] is None
    assert got[asks]["follow_up"] == "ask" and got[asks]["persona"] is None

    rows = {r["run"]: r for r in _get(world, "/api/working")["open"]}
    assert rows[worn]["persona_name"] == "Steward"
    assert rows[side]["generation"] == 1 and rows[asks]["follow_up"] == "ask"
