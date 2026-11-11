"""One keyed session `delegate`, in a process of its own, that ends for good at one
write boundary:

    python tests/_delegate_opkey_crash.py <corpus> <workdir> <boundary> <body.json>

`body` names the session (`execution`, `participant`, `runtime`, `host`), the
`delegate` arguments (with their `op_key`) and, optionally, an `outbox` folder:
when given, the write is first kept in that session's outbox exactly as the
bridge keeps it (`mentis.outbox`), so a later session start can resend it.

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
    st = _State(root, workdir)
    web.dispatch_soon = lambda *a, **kw: None      # nothing runs here
    state = {"armed": False}
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
    _post(url + "/api/worker", {"corpus": st.path, "op": "delegate", "args": args},
          {CAPABILITY_HEADER: grant["grant"]})
    os._exit(0)


if __name__ == "__main__":
    main(*sys.argv[1:])
