"""A Turn addressed to an agent becomes ONE run through the execution boundary.

The owner addresses a Participant in a Conversation through the HTTP route;
dispatch runs for real (only `dispatch_soon`'s thread is made synchronous) and
the agent is `FakeExecution`. What is pinned is the whole contract with MARS
on the Mentis side:

  * exactly one `RunSpec`, on the runtime the owner named (`backend`);
  * ONE MCP server, `mentis`: this interpreter, `-I -c` and the worker's boot
    command for THIS run's grant, asking this server (`via`);
  * the workspace: the server's `--workspace`, or the directory the request
    declared as its repository;
  * what MARS returned recorded: the reply Turn is the agent's text, the
    `result-returned` act carries the stop reason, tool calls and usage, and
    the grant is gone once the run has ended;
  * a run that could not start is a `delivery-failed` act saying why, and no
    reply Turn.
"""

from __future__ import annotations

import sys
import time

import pytest

from mentis.execution import RunResult
from tests._loop import a_conversation, say, world  # noqa: F401


@pytest.fixture()
def synchronous(world, monkeypatch):
    """`dispatch_soon` runs the real dispatch on the calling thread."""
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(st, **kw))
    return world


def _agent(world, alias="@Ada"):
    cv = world["cv"]
    ada = cv.create_participant(alias, about="an agent")
    return ada


def _address(world, cid, who, text="please summarise the plan", **spec):
    return say(world, cid, text, action="ask-participant",
               dispatch=[{"participant": who, "work": text, **spec}])


def test_a_turn_addressed_to_an_agent_is_one_runspec_and_a_recorded_reply(
        synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution
    held = {}

    def answer(spec):
        held["grant"] = st.agents.authority.grant_for(
            st.agents.authority.grant_of(spec.run_id), st.path)
        now = time.time()
        return RunResult(
            run_id=spec.run_id, backend=spec.backend, started=True,
            stop_reason="end_turn", text="Here is the summary.",
            tool_calls=[{"id": "t1", "title": "orient", "kind": "other",
                         "status": "completed", "locations": []}],
            usage={"input_tokens": 12, "output_tokens": 5},
            session_id="mars-session-1", started_at=now, finished_at=now)

    ex.script = {"codex": answer}
    ada = _agent(world)
    cid = a_conversation(world)
    out = _address(world, cid, ada, runtime="codex")
    request = out["expectations"][0]

    # ONE run, on the runtime named, in the server's workspace.
    assert len(ex.performed) == 1
    spec = ex.performed[0]
    assert spec.backend == "codex"
    assert spec.workspace == st.workspace
    assert "please summarise the plan" in spec.prompt

    # ONE MCP server: the Mentis bridge, under this run's grant, asking here.
    assert len(spec.mcp_servers) == 1
    server = spec.mcp_servers[0]
    assert server["name"] == "mentis"
    assert server["command"] == sys.executable
    assert server["args"][:2] == ["-I", "-c"]
    boot = server["args"][2]
    assert "from mentis.worker import serve" in boot
    assert f"serve(r'{st.path}'" in boot
    assert "capability=None" not in boot
    assert held["grant"]["instance"] == spec.run_id
    assert held["grant"]["expectation"] == request
    assert held["grant"]["participant"] == ada
    assert held["grant"]["runtime"] == "codex"

    # The grant lasted exactly as long as the run.
    assert st.agents.authority.grant_of(spec.run_id) is None

    # What MARS returned is on the record: the reply, and how the run ended.
    started = [a for a in cv.history(caused_by=request)
               if a["act"] == "execution-started"]
    assert len(started) == 1 and started[0]["runtime"] == "codex"
    assert started[0]["execution"] == spec.run_id
    returned = [a for a in cv.history(execution=spec.run_id)
                if a["act"] == "result-returned"]
    assert len(returned) == 1
    d = returned[0]["detail"]
    assert d["terminal"] == "reported_done"
    assert d["runtime_evidence"]["stop_reason"] == "end_turn"
    assert d["runtime_evidence"]["session_id"] == "mars-session-1"
    assert d["tool_calls"][0]["title"] == "orient"
    assert d["tool_calls_observable"] is True
    assert d["input_tokens"] == 12 and d["output_tokens"] == 5
    reply = returned[0]["turn"]
    got = cv.corpus.read([reply])[0]
    assert got["attributed_to"] == ada
    said = " ".join(p.get("text") or "" for p in got["body"]["parts"])
    assert said == "Here is the summary."

    # The request's status is Mentis's own, after the session has ended, and it
    # claims nothing about Git that Mentis does not track (Mark IV said
    # "nothing committed" from worktree records this build no longer has).
    from mentis.operational import work_overview as wo
    from mentis.web import _runtime_observation
    view = wo.overview(cv, viewer=wo.owner_of(cv), runtime=_runtime_observation(st))
    item = next(i for i in view["items"] if i.get("expectation") == request)
    assert item["stage"] == "ended"
    assert "committed" not in item["stage_words"]


def test_the_bridge_asks_the_server_it_was_dispatched_from(synchronous):
    """`via` is where this server answers: the bridge asks it, not a file."""
    world = synchronous
    st = world["state"]
    st.agents.workers_read(st.path, answers_at="http://127.0.0.1:8790")
    ada = _agent(world)
    cid = a_conversation(world)
    _address(world, cid, ada, runtime="claude")
    boot = st.agents.execution.performed[0].mcp_servers[0]["args"][2]
    assert "via='http://127.0.0.1:8790'" in boot


def test_a_declared_repository_directory_is_the_workspace(synchronous,
                                                          tmp_path):
    world = synchronous
    st = world["state"]
    repo = tmp_path / "the-repo"
    repo.mkdir()
    ada = _agent(world)
    cid = a_conversation(world)
    _address(world, cid, ada, runtime="claude",
             repository={"path": str(repo)})
    spec = st.agents.execution.performed[0]
    assert spec.workspace == str(repo)
    assert spec.backend == "claude"


def test_a_declared_directory_that_is_not_there_is_refused_before_a_run(
        synchronous, tmp_path):
    world = synchronous
    st, cv = world["state"], world["cv"]
    ada = _agent(world)
    cid = a_conversation(world)
    out = _address(world, cid, ada, runtime="claude",
                   repository={"path": str(tmp_path / "nowhere")})
    request = out["expectations"][0]
    assert st.agents.execution.performed == []
    failed = [a for a in cv.history(caused_by=request)
              if a["act"] == "delivery-failed"]
    assert failed and failed[-1]["detail"]["stage"] == "repository"
    assert "nowhere" in failed[-1]["because"]


def test_a_run_mars_could_not_start_is_a_recorded_failure_and_no_reply(
        synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]

    def unavailable(spec):
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="auth_required",
                         error="claude is not logged in")

    st.agents.execution.script = {"claude": unavailable}
    ada = _agent(world)
    cid = a_conversation(world)
    out = _address(world, cid, ada, runtime="claude")
    request = out["expectations"][0]
    run = st.agents.execution.performed[0].run_id
    failed = [a for a in cv.history(execution=run)
              if a["act"] == "delivery-failed"]
    assert len(failed) == 1
    assert "auth_required" in failed[0]["because"]
    assert "not logged in" in failed[0]["because"]
    assert not [a for a in cv.history(execution=run)
                if a["act"] in ("result-returned", "turn-said")]
    # Ended is not satisfied: the request is still owed.
    assert not cv.expectation_state(request)["satisfied_by"]


def test_a_runtime_mars_does_not_list_is_refused_before_a_run(synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]
    ada = _agent(world)
    cid = a_conversation(world)
    out = _address(world, cid, ada, runtime="kimi-k3")
    request = out["expectations"][0]
    assert st.agents.execution.performed == []
    failed = [a for a in cv.history(caused_by=request)
              if a["act"] == "delivery-failed"]
    assert failed and failed[-1]["detail"]["before_execution_started"]
    assert "kimi-k3" in failed[-1]["because"]


def test_a_run_addressed_with_a_persona_records_the_persona_it_ran_as(synchronous):
    # Found in the integrated browser check: a post addressed with a Persona ran
    # as it (it was composed into the prompt) and its run could not say so --
    # nothing recorded it. The start act carries it, and the run details read it.
    from mentis.operational.runs import asked_with
    world = synchronous
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution

    def answer(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", tool_calls=[],
                         usage={}, session_id="s", started_at=now, finished_at=now)

    ex.script = {"codex": answer}
    ada = _agent(world)
    persona = cv.define_persona("Builder", "You build the declared property.",
                                attributed_to=world["who"]["@brian"])
    cid = a_conversation(world)
    _address(world, cid, ada, runtime="codex", persona=persona)
    spec = ex.performed[0]
    assert "You build the declared property." in spec.prompt
    started = [a for a in cv.history() if a["act"] == "execution-started"][-1]
    assert started["detail"]["persona"] == persona
    assert asked_with(cv, started)["persona_name"] == "Builder"
