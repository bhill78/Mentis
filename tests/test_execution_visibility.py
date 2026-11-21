"""Execution visibility (2026-11-16): a runtime-native worker stays a tool call of
its run, with its place in the run kept; what a run used is named for what it is;
a Mentis delegation is linked to the work it came from. Nothing is invented for a
runtime that reports none of it.

The shapes are the ones measured through MARS with claude-agent-acp 0.97.0
(`Mentis-env/evidence/claude-subagents`, `.../exec-visibility`)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mentis.core.run_feed import RunFeed
from mentis.execution import RunResult, RunSpec
from mentis.execution.mars import MarsExecution, _RunState, native_facts, turn_usage
from mentis.operational import runs
from mentis.web.dispatch import usage_facts


def _update(update_kind, call_id, *, meta=None, **fields):
    base = {"title": None, "kind": None, "status": None, "locations": None}
    return SimpleNamespace(session_update=update_kind, tool_call_id=call_id, field_meta=meta,
                           **{**base, **fields},
                           model_dump=lambda **_: {"session_update": update_kind, "tool_call_id": call_id,
                                                   "field_meta": meta,
                                                   **{k: v for k, v in fields.items() if v is not None}})


def _state(events):
    spec = RunSpec(run_id="r1", backend="claude", workspace="C:/ws", prompt="p")
    result = RunResult(run_id="r1", backend="claude", started=True)
    return _RunState(spec=spec, result=result, on_event=events.append)


AGENT = {"mars/tool": {"name": "Agent", "how": "observed", "worker": {"how": "observed"}}}
CHILD = {"mars/tool": {"name": "Bash", "shell": "bash", "how": "observed", "parent": "agent-1"}}
ENDED = {"mars/tool": {"name": "Agent", "how": "observed", "worker": {
    "agent_type": "general-purpose", "agent_id": "a84", "model": "claude-haiku-5-5",
    "duration_ms": 32489, "tool_calls": 2, "context_tokens": 24819, "how": "observed"}}}


def test_native_facts_reads_only_what_mars_reported():
    assert native_facts(None) == {}
    assert native_facts({"claudeCode": {"parentToolUseId": "x"}}) == {}      # MARS's key, not Claude's
    assert native_facts({"mars/tool": {"name": "Bash"}}) == {}
    assert native_facts(CHILD) == {"parent": "agent-1"}
    assert native_facts(AGENT) == {"worker": {}}                             # a worker, nothing reported yet
    assert native_facts(ENDED)["worker"] == {
        "agent_type": "general-purpose", "agent_id": "a84", "model": "claude-haiku-5-5",
        "duration_ms": 32489, "tool_calls": 2, "context_tokens": 24819}
    # nothing but the named facts, and no booleans or objects passed off as one
    odd = {"mars/tool": {"worker": {"model": True, "tokens_spent": 9, "elapsed_s": {"n": 1}}}}
    assert native_facts(odd) == {"worker": {}}


def test_a_workers_calls_keep_their_parent_in_the_record_and_the_event():
    events: list = []
    state = _state(events)
    ex = MarsExecution(["mars"])

    async def go():
        ex._states["s1"] = state
        await ex._session_update("s1", _update("tool_call", "agent-1", meta=AGENT, title="beta sum", kind="think", status="pending"))
        await ex._session_update("s1", _update("tool_call", "c1", meta=CHILD, title="echo hi", kind="execute", status="pending"))
        await ex._session_update("s1", _update("tool_call_update", "c1", meta=CHILD, status="completed"))
        await ex._session_update("s1", _update("tool_call_update", "agent-1", meta=ENDED, status="completed"))
        await ex._session_update("s1", _update("tool_call", "own-1", meta={"mars/tool": {"name": "Bash"}}, title="ls", status="pending"))
    asyncio.run(go())

    assert state.tools["c1"]["parent"] == "agent-1"
    assert state.tools["agent-1"]["worker"]["model"] == "claude-haiku-5-5"
    assert "parent" not in state.tools["agent-1"] and "parent" not in state.tools["own-1"]
    assert "worker" not in state.tools["c1"] and "worker" not in state.tools["own-1"]
    by_id = {}
    for e in events:
        by_id.setdefault(e.data["tool_call_id"], []).append(e.data)
    assert by_id["c1"][0]["parent"] == "agent-1"
    assert by_id["agent-1"][0]["worker"] == {}
    assert by_id["agent-1"][-1]["worker"]["duration_ms"] == 32489
    assert "parent" not in by_id["own-1"][0] and "worker" not in by_id["own-1"][0]
    # `_meta` itself is still not what Mentis records
    assert all("field_meta" not in d for ds in by_id.values() for d in ds)


def test_a_permission_asked_by_a_worker_says_so_and_nothing_else_does():
    state = _state([])
    state.tools["agent-1"] = {"id": "agent-1", "title": "beta sum"}
    state.tools["c1"] = {"id": "c1", "title": "echo hi", "parent": "agent-1"}
    asked = SimpleNamespace(tool_call_id="c1", field_meta=None)       # the request itself named none
    assert MarsExecution._asked_by_worker(state, asked) == {"parent": "agent-1", "parent_title": "beta sum"}
    named = SimpleNamespace(tool_call_id="c9", field_meta=CHILD)
    assert MarsExecution._asked_by_worker(state, named)["parent"] == "agent-1"
    own = SimpleNamespace(tool_call_id="own-1", field_meta={"mars/tool": {"name": "Bash"}})
    assert MarsExecution._asked_by_worker(state, own) == {}


def test_turn_usage_is_kept_as_reported_or_not_at_all():
    assert turn_usage(None) is None
    assert turn_usage({"mars/usage": {}}) is None
    assert turn_usage({"mars/usage": "many"}) is None
    got = turn_usage({"mars/usage": {"tokens": {"total": 76707}, "tokens_cover": "main-loop",
                                     "by_model": [{"model": "m", "tokens": {"total": 5}}],
                                     "cost": {"amount": 0.119, "currency": "USD"},
                                     "context": {"used": 38728, "size": 1000000}, "how": "reported",
                                     "something_else": 1}})
    assert set(got) == {"tokens", "tokens_cover", "by_model", "cost", "context", "how"}


def _feed():
    feed = RunFeed()
    feed.add("tool_call", {"tool_call_id": "agent-1", "title": "alpha count", "kind": "think", "status": "pending", "worker": {}}, 1.0)
    feed.add("tool_call", {"tool_call_id": "agent-2", "title": "beta sum", "kind": "think", "status": "pending",
                           "worker": {"requested_model": "haiku"}}, 2.0)
    feed.add("tool_call", {"tool_call_id": "c1", "title": "sleep 25; wc -l alpha.txt", "kind": "execute", "status": "pending", "parent": "agent-1"}, 3.0)
    feed.add("tool_call", {"tool_call_id": "c2", "title": "sleep 25; cat beta.txt", "kind": "execute", "status": "in_progress", "parent": "agent-2"}, 4.0)
    feed.add("tool_call_update", {"tool_call_id": "agent-1", "status": "in_progress", "worker": {"elapsed_s": 30}}, 5.0)
    return feed


def test_the_feed_nests_a_workers_calls_and_merges_what_is_reported_of_it():
    feed = _feed()
    entries = {e["id"]: e for e in feed.since(0)}
    assert entries["tool-c1"]["parent"] == "tool-agent-1"
    assert entries["tool-agent-1"]["worker"] == {"elapsed_s": 30}
    assert entries["tool-agent-2"]["worker"] == {"requested_model": "haiku"}
    assert "parent" not in entries["tool-agent-1"]
    feed.add("tool_call_update", {"tool_call_id": "c1", "status": "completed"}, 6.0)
    feed.add("tool_call_update", {"tool_call_id": "agent-1", "status": "completed",
                                  "worker": {"model": "claude-sonnet-5", "duration_ms": 32869, "tool_calls": 1, "context_tokens": 29229}}, 7.0)
    workers = feed.workers()
    assert [w["title"] for w in workers] == ["alpha count", "beta sum"]
    alpha, beta = workers
    assert alpha["status"] == "completed" and alpha["model"] == "claude-sonnet-5" and alpha["calls_seen"] == 1
    assert alpha["elapsed_s"] == 30 and alpha["context_tokens"] == 29229 and "now" not in alpha
    assert beta["status"] == "pending" and beta["now"] == "sleep 25; cat beta.txt" and beta["requested_model"] == "haiku"
    assert "model" not in beta          # not reported until it ends: not filled in


def test_a_run_with_no_native_workers_has_none_and_a_flat_feed():
    feed = RunFeed()
    feed.add("tool_call", {"tool_call_id": "t1", "title": "ls", "kind": "execute", "status": "completed"}, 1.0)
    assert feed.workers() == []
    assert all("parent" not in e and "worker" not in e for e in feed.since(0))


def test_the_feed_keeps_cost_and_the_turns_usage_apart_from_the_context_reading():
    feed = RunFeed()
    feed.add("usage_update", {"used": 38728, "size": 1000000, "cost": {"amount": 0.119, "currency": "USD"}}, 1.0)
    feed.add("turn_usage", {"tokens": {"total": 76707}, "tokens_cover": "main-loop"}, 2.0)
    entries = {e["kind"]: e for e in feed.since(0)}
    assert entries["usage"]["usage"] == {"used": 38728, "size": 1000000, "cost_amount": 0.119, "cost_currency": "USD"}
    assert entries["turn_usage"]["turn"] == {"tokens": {"total": 76707}, "tokens_cover": "main-loop"}
    # a permission a worker asked for names the worker's entry
    feed.add("permission", {"tool_call": {"title": "echo hi"}, "parent": "agent-1", "outcome": "selected"}, 3.0)
    asked = next(e for e in feed.since(0) if e["kind"] == "permission")
    assert asked["parent"] == "tool-agent-1"


def test_usage_facts_names_each_figure_and_lists_native_workers():
    usage = {"used": 38728, "size": 1000000, "cost": {"amount": 0.119, "currency": "USD"},
             "turn": {"tokens": {"total": 76707}, "tokens_cover": "main-loop",
                      "by_model": [{"model": "claude-sonnet-5", "tokens": {"total": 130182}}],
                      "cost": {"amount": 0.119, "currency": "USD"}}}
    calls = [{"id": "agent-1", "title": "beta sum", "status": "completed",
              "worker": {"model": "claude-haiku-5-5", "duration_ms": 32489, "tool_calls": 2, "context_tokens": 24819}},
             {"id": "c1", "title": "echo hi", "status": "completed", "parent": "agent-1"},
             {"id": "c2", "title": "sleep 9", "status": "pending", "parent": "agent-1", "open_at_end": True},
             {"id": "own-1", "title": "ls", "status": "completed"}]
    got = usage_facts(usage, calls)
    assert got["context_used"] == 38728 and got["context_size"] == 1000000
    assert got["tokens"] == {"total": 76707} and got["tokens_cover"] == "main-loop"
    assert got["tokens_by_model"] == [{"model": "claude-sonnet-5", "tokens": {"total": 130182}}]
    assert got["cost"] == {"amount": 0.119, "currency": "USD"}
    assert got["native_workers"] == [{"call": "agent-1", "title": "beta sum", "status": "completed",
                                      "model": "claude-haiku-5-5", "duration_ms": 32489, "tool_calls": 2,
                                      "context_tokens": 24819, "calls_seen": 2}]


def test_usage_facts_invents_nothing():
    assert usage_facts(None, []) == {}
    assert usage_facts({"used": 1200, "size": 8000}, [{"id": "t", "title": "ls", "status": "completed"}]) == {
        "context_used": 1200, "context_size": 8000}      # no tokens, no cost, no workers
    assert "tokens" not in usage_facts({"turn": {"context": {"used": 5}}}, [])


class _Record:
    """The few record reads these functions make."""

    def __init__(self, acts):
        self.acts = {a["id"]: a for a in acts}

    def _act(self, act_id):
        return self.acts.get(act_id)

    def history(self, caused_by=None, **_):
        return [a for a in self.acts.values() if a.get("caused_by") == caused_by]

    def alias(self, pid):
        return {"p-care": "@Caretaker", "p-rev": "@Reviewer"}.get(pid)


def test_a_delegated_runs_request_names_who_delegated_it_and_under_what():
    cv = _Record([
        {"id": "exp-parent", "act": "expectation-opened", "at": 1.0},
        {"id": "exp-child", "act": "expectation-opened", "at": 2.0, "caused_by": "exp-parent"},
        {"id": "d1", "act": "work-delegated", "at": 2.5, "caused_by": "exp-parent", "about": ["exp-child"], "actor": "p-care"},
        {"id": "exp-plain", "act": "expectation-opened", "at": 3.0},
    ])
    got = runs.delegated_from(cv, "exp-child")
    assert got == {"by": "p-care", "by_name": "Caretaker", "expectation": "exp-parent", "at": 2.5, "source": runs.RECORDED}
    assert runs.delegated_from(cv, "exp-plain") is None        # addressed directly: not a delegation
    assert runs.delegated_from(cv, None) is None


def test_recorded_end_hands_on_what_the_end_act_kept():
    from mentis.conversation import RUN_ENDS
    cv = _Record([
        {"id": "run-1", "act": "run-start", "at": 1.0},
        {"id": "end-1", "act": RUN_ENDS[1], "at": 9.0, "caused_by": "run-1",
         "detail": {"terminal": "cancelled", "tool_calls": [{"id": "agent-1", "worker": {}, "open_at_end": True}],
                    "native_workers": [{"call": "agent-1"}], "context_used": 5, "notes": ["x"]}},
        {"id": "run-2", "act": "run-start", "at": 1.0},
        {"id": "end-2", "act": RUN_ENDS[0], "at": 9.0, "caused_by": "run-2", "detail": {"terminal": "reported_done"}},
    ])
    got = runs.recorded_end(cv, "run-1")
    assert got["stop_reason"] == "cancelled" and got["ended_at"] == 9.0
    assert got["tool_calls"][0]["open_at_end"] is True and got["notes"] == ["x"]
    assert runs.recorded_end(cv, "run-2")["stop_reason"] == "reported_done"  # N-A2: older terminal still exists
    assert runs.recorded_end(cv, "run-3") is None             # no recorded end


STARTED = {"mars/tool": {"how": "observed", "worker": {"description": "alpha", "agent_id": "t-1", "event": "started", "how": "observed"}}}
COMPLETED = {"mars/tool": {"how": "observed", "worker": {"description": "alpha", "agent_id": "t-1", "event": "completed", "how": "observed"}}}


def test_a_runtime_that_reports_only_a_workers_start_and_end_gives_one_worker():
    """Codex (codex-acp 2.3.0): `Start subagent alpha`, whose own call completes at
    once, then `Complete subagent alpha`. One worker, at work between the two."""
    events: list = []
    state = _state(events)
    ex = MarsExecution(["mars"])
    feed = RunFeed()

    async def go():
        ex._states["s1"] = state
        await ex._session_update("s1", _update("tool_call", "call_7", meta=STARTED, title="Start subagent alpha", kind="other", status="in_progress"))
        await ex._session_update("s1", _update("tool_call_update", "call_7", meta=STARTED, status="completed"))
        mid = dict(state.tools["call_7"])
        await ex._session_update("s1", _update("tool_call", "done-1", meta=COMPLETED, title="Complete subagent alpha", kind="other", status="in_progress"))
        await ex._session_update("s1", _update("tool_call_update", "done-1", meta=COMPLETED, status="completed"))
        return mid
    mid = asyncio.run(go())
    assert mid["status"] == "in_progress"                 # the launch ended; the worker had not
    assert state.tools["call_7"]["status"] == "completed"
    assert "worker" not in state.tools["done-1"] and state.tools["done-1"]["parent"] == "call_7"
    for i, e in enumerate(events):
        feed.add(e.kind, e.data, 10.0 + i * 5)
    workers = feed.workers()
    assert [w["title"] for w in workers] == ["Start subagent alpha"]
    assert workers[0]["status"] == "completed" and workers[0]["event"] == "started"
    assert workers[0]["duration_ms"] == 10000             # between the two reports, as observed
    facts = usage_facts(None, list(state.tools.values()))
    assert [w["call"] for w in facts["native_workers"]] == ["call_7"]


def test_a_runtime_that_reports_only_a_workers_start_leaves_it_open():
    """Antigravity (agy 1.5.9) reports that a sub-agent was started and nothing after."""
    state = _state([])
    ex = MarsExecution(["mars"])
    meta = {"mars/tool": {"name": "invoke_subagent", "how": "observed",
                          "worker": {"description": "Task A Worker", "event": "launched", "how": "observed"}}}

    async def go():
        ex._states["s1"] = state
        await ex._session_update("s1", _update("tool_call", "step_3", meta=meta, title="Task A Worker", kind="other", status="in_progress"))
    asyncio.run(go())
    assert state.tools["step_3"]["status"] == "in_progress"
    assert state.tools["step_3"]["worker"] == {"description": "Task A Worker", "event": "launched"}


def test_whose_delegation_a_request_is_is_read_once_for_many_polls(monkeypatch):
    calls = []

    def read(cv, expectation):
        calls.append(expectation)
        return {"by": "p-care", "expectation": "exp-parent"} if expectation == "exp-child" else None
    monkeypatch.setattr(runs, "_delegated_from_record", read)
    runs._DELEGATED_FROM.clear()
    cv = object()
    first = runs.delegated_from(cv, "exp-child")
    first["run"] = "run-1"                                   # a caller's addition stays the caller's
    assert runs.delegated_from(cv, "exp-child") == {"by": "p-care", "expectation": "exp-parent"}
    assert runs.delegated_from(cv, "exp-plain") is None and runs.delegated_from(cv, "exp-plain") is None
    assert calls == ["exp-child", "exp-plain"]
    runs._DELEGATED_FROM.clear()
