"""One keyed session `delegate`, in a process of its own, that ends for good at one
write boundary:

    python tests/_delegate_opkey_crash.py <corpus> <workdir> <boundary> <body.json>

`body` names the session (`execution`, `participant`, `runtime`, `host`), the
`delegate` arguments (with their `op_key`) and, optionally, an `outbox` folder:
when given, the write is first kept in that session's outbox exactly as the
bridge keeps it (`mentis.outbox`), so a later session start can resend it.

Round 4 (C2) adds the boundaries AFTER the commit, up to the child's run starting:
`dispatching` (inside the door's dispatch, before its reply), `answered` (the answer
was received, the dispatch never ran), `starting` (inside the transaction that writes
the child's `execution-started`, before its COMMIT) and `started` (just after that
COMMIT). And `recovering`: no delegation is sent; the server-start recovery pass
(`dispatch.recover_delegations`) runs and the process dies as it starts the run it
claimed.

`os._exit` is the crash: no `finally`, no rollback, nothing Python held is
flushed. What the disk then says is what `tests/test_delegate_opkey_crash.py`
reads. Run to the end without reaching the boundary, it exits 0, and that test
fails."""
from __future__ import annotations

import json
import os
import sys
import threading

CRASHED = 43

#: Each write `delegate` makes, in order, and the op key's own.
#: `joined` .. `delegated`: after that write of the delegation returned.
#: `keying`: just before the op key's act is written; `keyed`: just after.
#: `committing`: at the COMMIT that would make the op key durable.
#: `committed`: just after that COMMIT, before the answer is sent.
DELEGATION = ("joined", "said", "expected", "delegated")
KEY = ("keying", "keyed", "committing")
AFTER = ("committed",)
EVERY = (*DELEGATION, *KEY, *AFTER)
#: Round 4 (C2): after the commit, before (or at) the child's run starting.
DISPATCH = ("dispatching", "answered", "starting", "started")
RECOVERING = "recovering"


class _Commits:
    """The store's connection, seeing the op key's COMMIT go by."""

    def __init__(self, conn, state, at):
        self._conn_, self._state, self._at = conn, state, at

    def __getattr__(self, name):
        return getattr(self._conn_, name)

    def execute(self, sql, *args):
        keyed = self._state.get("keyed")
        if sql == "COMMIT" and keyed and self._at == "committing":
            os._exit(CRASHED)
        got = self._conn_.execute(sql, *args)
        if sql == "COMMIT" and keyed and self._at == "committed":
            os._exit(CRASHED)
        return got


def main(root, workdir, at, body_file) -> None:
    from http.server import ThreadingHTTPServer

    import mentis.opkeys as opkeys
    import mentis.web as web
    from mentis.conversation import Conversations
    from mentis.web import _Handler, _State
    from mentis.worker import CAPABILITY_HEADER, SESSION_ROUTE
    from tests.test_manual_session import _post

    body = json.loads(open(body_file, encoding="utf-8").read())
    # AS IN EVERY TEST (`tests/conftest.py`): runs go to a FakeExecution, never MARS.
    from mentis.core import service
    from mentis.execution import FakeExecution
    service.unavailable_execution = lambda why: FakeExecution()
    st = _State(root, workdir)
    web.dispatch_soon = lambda *a, **kw: None      # nothing runs here
    state = {"armed": False}
    if at == RECOVERING:
        # THE SERVER-START PASS, dying as it starts what it claimed.
        from mentis.web.dispatch import recover_delegations
        recover_delegations(st, start=lambda *a, **kw: os._exit(CRASHED))
        os._exit(0)
    if at == "dispatching":
        web.dispatch_soon = lambda *a, **kw: os._exit(CRASHED)
    if at in ("starting", "started"):
        # The door's dispatch, run for real on this thread, up to the child's start.
        from mentis.web import dispatch as D
        web.dispatch_soon = lambda s, **kw: D.dispatch(s, **kw)
        if at == "starting":
            real_started = D._started_act

            def started_act(*a, **kw):
                real_started(*a, **kw)
                os._exit(CRASHED)       # inside the start's transaction
            D._started_act = started_act
        else:
            st.agents.agents_open_run = lambda *a, **kw: os._exit(CRASHED)
    store = st.corpus._store
    store._conn = _Commits(store._conn, state, at)

    def after(method, boundary, when=lambda kw: True):
        real = getattr(Conversations, method)

        def wrapped(self, *a, **kw):
            got = real(self, *a, **kw)
            if state["armed"] and at == boundary and when(kw):
                os._exit(CRASHED)
            return got
        setattr(Conversations, method, wrapped)

    after("join", "joined")
    after("say", "said")
    after("expect", "expected")
    after("record_act", "delegated", lambda kw: kw.get("act") == "work-delegated")

    real_remember = opkeys.remember

    def remember(*a, **kw):
        if state["armed"] and at == "keying":
            os._exit(CRASHED)
        got = real_remember(*a, **kw)
        if state["armed"]:
            state["keyed"] = True
            if at == "keyed":
                os._exit(CRASHED)
        return got
    opkeys.remember = remember

    handler = type("H", (_Handler,), {"state": st})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    status, grant = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": body["runtime"],
                           "host": body["host"], "participant": body["participant"],
                           "continues": body["execution"]},
                          {"X-Mentis-Client": "1"})
    assert status == 200, grant
    args = body["args"]
    if body.get("outbox"):
        # KEPT BEFORE IT IS SENT, as the bridge keeps every session write.
        from mentis.outbox import Outbox
        from mentis.session_identity import default_alias
        Outbox(default_alias(body["runtime"], body["host"]), body["outbox"],
               execution=body["execution"]).put("delegate", args)
    state["armed"] = True
    said = _post(url + "/api/worker", {"corpus": st.path, "op": "delegate", "args": args},
                 {CAPABILITY_HEADER: grant["grant"]})
    print(json.dumps(said, default=str)[:600], flush=True)
    os._exit(CRASHED if at == "answered" else 0)


if __name__ == "__main__":
    main(*sys.argv[1:])
