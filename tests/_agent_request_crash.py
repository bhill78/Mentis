"""One agent request in a process of its own, which ends for good at one boundary:

    python tests/_agent_request_crash.py <corpus> <boundary> <body.json>

`os._exit` is the crash: no `finally`, no rollback, no flush of anything Python was
holding. What the disk then says is what `tests/test_agent_request_crash.py` reads.
Run to the end without reaching the boundary, it exits 0, and that test fails."""
from __future__ import annotations

import json
import os
import sys
import time

CRASHED = 42

#: Inside the transaction: everything is written, and nothing is committed.
IN_TRANSACTION = ("opening", "opened", "claimed", "posted", "routed", "committing")
#: The commit has happened: the files and the run have not.
AFTER_COMMIT = ("committed", "file-temp", "file-replaced", "before-start",
                "start-uncommitted")
#: The run's start is durable, and the second has its end too.
RUNNING = ("run-started", "run-ended")
EVERY = (*IN_TRANSACTION, *AFTER_COMMIT, *RUNNING)
#: What a request into a Conversation that already exists never reaches.
OWN_ONLY = ("opening", "opened", "claimed", "file-temp", "file-replaced")


class _Commits:
    """The store's connection, seeing the request's own COMMIT go by."""

    def __init__(self, conn, armed, at):
        self._conn_, self._armed, self._at = conn, armed, at

    def __getattr__(self, name):
        return getattr(self._conn_, name)

    def execute(self, sql, *args):
        if sql == "COMMIT" and self._armed and self._at == "committing":
            os._exit(CRASHED)
        got = self._conn_.execute(sql, *args)
        if sql == "COMMIT" and self._armed and self._at == "committed":
            os._exit(CRASHED)
        return got


def main(root, at, body_file) -> None:
    import mentis.web as web
    from mentis.conversation import Conversations
    from mentis.execution import FakeExecution, RunResult
    from mentis.fluid import commands
    from mentis.web import dispatch as D
    from mentis.web import _State

    body = json.loads(open(body_file, encoding="utf-8").read())
    st = _State(root, execution=FakeExecution())
    store = st.corpus._store
    armed = []
    store._conn = _Commits(store._conn, armed, at)

    real_open = Conversations.open_conversation

    def opening(self, *a, **kw):
        if at == "opening":
            os._exit(CRASHED)
        return real_open(self, *a, **kw)
    Conversations.open_conversation = opening

    real_opened = commands.open_conversation

    def opened(*a, **kw):
        got = real_opened(*a, **kw)
        if at == "opened":
            os._exit(CRASHED)
        return got
    commands.open_conversation = opened

    real_act = Conversations.record_act

    def acted(self, **kw):
        got = real_act(self, **kw)
        if kw["act"] == commands.CONVERSATION_CLAIMED and at == "claimed":
            os._exit(CRASHED)
        if kw["act"] == commands.REQUEST_ROUTED:
            if at == "routed":
                os._exit(CRASHED)
            armed.append(True)
        return got
    Conversations.record_act = acted

    real_post = commands.write_post

    def posted(*a, **kw):
        got = real_post(*a, **kw)
        if at == "posted":
            os._exit(CRASHED)
        return got
    commands.write_post = posted

    real_replace = os.replace

    def replacing(src, dst):
        if at == "file-temp" and armed:
            os._exit(CRASHED)
        got = real_replace(src, dst)
        if at == "file-replaced" and armed:
            os._exit(CRASHED)
        return got
    os.replace = replacing

    real_started = D._started_act

    def start_act(*a, **kw):
        got = real_started(*a, **kw)
        if at == "start-uncommitted":
            os._exit(CRASHED)
        return got
    D._started_act = start_act

    def perform(spec):
        if at == "run-started":
            os._exit(CRASHED)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: the first run's",
                         started_at=now, finished_at=now)
    ex = st.agents.execution
    ex.script = {b["id"]: perform for b in ex.backends()}

    def starting(state, **kw):
        if at == "before-start":
            os._exit(CRASHED)
        D.dispatch(state, **kw)
        if at == "run-ended":
            os._exit(CRASHED)
    web.dispatch_soon = starting

    commands.agent_request(st, body,
                           written_by=lambda: web._observed_writer(st, None))
    os._exit(0)


if __name__ == "__main__":
    main(*sys.argv[1:])
