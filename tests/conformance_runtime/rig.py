"""The runtime-conformance rig: one fixture Mentis server, one runtime, the real dispatch.

TWO MODES, ONE SET OF BEHAVIOURAL TESTS (round 2, O9 / program §12):

  * OFFLINE (default; pytest and CI): the execution is `ScriptedExecution`, a stand-in for
    MARS that serves one runtime PROFILE (`profiles.py`): its `_mars/backends` entry with the
    capability contract, and how that runtime resumes, cancels and reports. Its agent
    follows the task's STEP lines the way a model is asked to: it calls each Mentis
    operation over the same wire the bridge uses (`worker._over`, `/api/worker`, the run's
    own grant), writes the step report and ends with the outcome block the task gives.
  * LIVE (`MENTIS_RUNTIME_CONFORMANCE=<runtime>[:<model>]`, with `MENTIS_CONFORMANCE_MARS`
    the MARS command): the execution is the real `MarsExecution` over a MARS build, and the
    agent is the real runtime, given the Mentis bridge that points at THIS fixture server.

Everything else is real in both: the HTTP server, the owner's turn, dispatch, selection,
grants, the worker door, acts, completion reconciliation, leases and continuity.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentis.execution import RunEvent, RunResult

LIVE_ENV = "MENTIS_RUNTIME_CONFORMANCE"
MARS_ENV = "MENTIS_CONFORMANCE_MARS"
ROOT_ENV = "MENTIS_CONFORMANCE_ROOT"
PORT_ENV = "MENTIS_CONFORMANCE_PORT"

STEP = re.compile(r"^STEP (\d+): call the Mentis tool `([a-z_]+)` with (\{.*\})\s*$", re.M)
FINISH = "FINISH: end your final reply with exactly this block:"
CODEWORD = re.compile(r"CODEWORD:\s*([A-Z]{6})")


def live_selection() -> tuple[str, str | None] | None:
    """`(runtime, model)` when the live mode is selected, else None."""
    raw = os.environ.get(LIVE_ENV, "").strip()
    if not raw:
        return None
    runtime, _, model = raw.partition(":")
    return runtime.strip(), (model.strip() or None)


# -- the scripted runtime ------------------------------------------------------------------

@dataclass
class _Session:
    """What a scripted runtime remembers of one session: what it said."""
    said: list[str] = field(default_factory=list)


class ScriptedExecution:
    """A stand-in for MARS serving one runtime profile. It runs the agent described above
    and answers as that runtime does through MARS:

      * resume `on-new` (an ACP runtime with a verified resume: claude) gives a token at
        session/new and loads a session it gave; `per-prompt` (agy) gives a token per turn
        that it says cannot be resumed; `none` gives nothing resumable;
      * cancel ends the turn `cancelled` (cooperative, or by killing it: the client sees
        the same stopReason);
      * a model the profile does not offer fails at session/new (`backend_unavailable`,
        option `model`), as MARS does.
    """

    generation = 1

    def __init__(self, profile: dict, svc_ref: dict) -> None:
        self.profile = profile
        self._svc = svc_ref
        self._sessions: dict[str, _Session] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self.sent: list[tuple[str, str]] = []   # (run id, what the agent was sent)
        self.performed: list = []

    # Execution protocol --------------------------------------------------------------
    def backends(self) -> list[dict]:
        return [dict(self.profile["backend"])]

    def capacity(self) -> dict:
        return dict(self.profile.get("capacity") or {})

    def running(self) -> set[str]:
        with self._lock:
            return set(self._running)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            ev = self._cancel.get(run_id)
            live = run_id in self._running
        if ev is not None:
            ev.set()
        return live

    def close(self) -> None:
        pass

    def perform(self, spec, on_event=None, on_permission=None) -> RunResult:
        prof = self.profile
        now = time.time()
        with self._lock:
            self.performed.append(spec)
            self._running.add(spec.run_id)
            ev = self._cancel.setdefault(spec.run_id, threading.Event())
        try:
            model = (spec.options or {}).get("model")
            if model and model not in prof["backend"].get("models", []):
                return RunResult(run_id=spec.run_id, backend=spec.backend, started=False,
                                 error_kind="backend_unavailable", option="model",
                                 offered=list(prof["backend"].get("models", [])),
                                 error=f"backend {spec.backend!r} does not offer model {model!r}",
                                 started_at=now, finished_at=time.time())
            session, token, resumed = self._open(spec)
            sent = (spec.continuation if resumed and resumed.get("resumed") and spec.continuation
                    else spec.prompt)
            self.sent.append((spec.run_id, sent))
            if on_event is not None:
                on_event(RunEvent("agent_message_chunk", {"text": "working"}, time.time()))
            remembered = "\n".join(session.said)
            session.said.append(sent)
            text = self._agent(spec, sent, session, ev, remembered)
            if ev.is_set():
                return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                                 stop_reason="cancelled", text=text, started_at=now,
                                 finished_at=time.time(), runtime_session=token,
                                 resumed=resumed)
            if "[[runtime-error]]" in sent:
                return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                                 error_kind="backend_exited", error="the runtime exited 1",
                                 text=text, started_at=now, finished_at=time.time(),
                                 runtime_session=token, resumed=resumed)
            session.said.append(text)
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             stop_reason="end_turn", text=text, started_at=now,
                             finished_at=time.time(), runtime_session=token, resumed=resumed)
        finally:
            with self._lock:
                self._running.discard(spec.run_id)

    # the runtime's session handling ----------------------------------------------------
    def _open(self, spec):
        mode = self.profile["resume"]
        asked = (spec.resume or {}).get("token")
        resumed = None
        if mode == "on-new":
            if asked and asked in self._sessions:
                resumed = {"asked": True, "resumed": True,
                           "why": "session/resume loaded the runtime's own session"}
                return self._sessions[asked], {"token": asked, "backend": spec.backend,
                                               "supported": True}, resumed
            if asked:
                resumed = {"asked": True, "resumed": False,
                           "why": "the token is unknown here; a fresh session was opened"}
            token = f"scripted-{spec.backend}-{len(self._sessions)}"
            self._sessions[token] = _Session()
            return self._sessions[token], {"token": token, "backend": spec.backend,
                                           "supported": True}, resumed
        if asked:
            resumed = {"asked": True, "resumed": False,
                       "why": "this runtime offers no resume; a fresh session was opened"}
        if mode == "per-prompt":
            token = f"scripted-{spec.backend}-turn-{len(self._sessions)}"
            self._sessions[token] = _Session()
            return self._sessions[token], {"token": token, "backend": spec.backend,
                                           "supported": False}, resumed
        return _Session(), None, resumed

    # the agent ------------------------------------------------------------------------
    def _agent(self, spec, sent: str, session: _Session, cancelled: threading.Event,
               remembered: str = "") -> str:
        """Follow the task as a model is asked to. A resumed session remembers what it said
        (`session.said`); a fresh one knows only what it was sent."""
        from mentis.worker import NotPermitted, _over
        svc = self._svc["svc"]
        token = svc.authority.grant_of(spec.run_id)
        lines = []
        if "[[reply-exactly]]" in sent:
            # THE REPLY IS GIVEN, character for character (`scenarios.malformed_outcome`):
            # what a runtime that follows the instruction returns, with no tool called.
            given = re.search(r"^BEGIN REPLY\n(.*?)\nEND REPLY$", sent, re.S | re.M)
            if given:
                return given.group(1)
        if "[[hold-until-cancelled]]" in sent:
            cancelled.wait(timeout=120)
            return "started counting: 1 2 3"
        resuming = "Resuming the work you were carrying" in sent
        if resuming and "[[hold-on-resume]]" in remembered + sent:
            cancelled.wait(timeout=120)
            return "counting: one, two, three"
        steps = [] if resuming else STEP.findall(sent)
        for n, op, raw in steps:
            args = json.loads(raw)
            try:
                got = _over(svc._answers_at, svc._record, op, args, capability=token)
                lines.append(f"step {n}: ok" + (f" {got.get('lease')}" if isinstance(got, dict)
                                                 and got.get("lease") else ""))
            except NotPermitted as exc:
                d = exc.as_dict() if hasattr(exc, "as_dict") else {}
                lines.append(f"step {n}: refused boundary={d.get('boundary')} "
                             f"recovery={len(d.get('recovery') or [])} why={str(exc)[:160]}")
            except Exception as exc:                      # noqa: BLE001
                lines.append(f"step {n}: error {type(exc).__name__}: {str(exc)[:200]}")
        if "[[invent-codeword]]" in sent and not resuming:
            lines.append(f"CODEWORD: {self.profile['codeword']}")
        if resuming:
            # THE PRIOR CONTEXT: remembered by a resumed session, else only what was sent.
            memory = remembered + "\n" + sent
            found = CODEWORD.findall(memory)
            chose = re.findall(r"chose '([^']+)'", sent)
            lines.append(f"REMEMBERED: {found[-1] if found else 'NONE'}"
                         f" CHOSEN: {chose[-1] if chose else 'NONE'}")
        if "[[invent-codeword]]" in sent and not resuming:
            return "\n".join(lines)        # the work waits on the owner: no claim yet
        told = remembered + "\n" + sent
        block = told.rsplit(FINISH, 1)[1] if FINISH in told else ""
        fence = re.search(r"```outcome.*?```", block, re.S)
        if fence:
            lines.append("")
            lines.append(fence.group(0))
        return "\n".join(lines) or "done"


# -- the rig -------------------------------------------------------------------------------

class Rig:
    """One fixture Brain, one Mentis HTTP server over it, one runtime."""

    def __init__(self, runtime: str, *, root: Path, model: str | None = None,
                 profile: dict | None = None, mars: list[str] | None = None,
                 port: int = 0) -> None:
        from http.server import ThreadingHTTPServer

        from mentis.web import _Handler, _State, fixture
        self.runtime, self.model, self.profile = runtime, model, profile
        self.live = mars is not None
        self.root = Path(root)
        corpus = self.root / "corpus"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        built = fixture.build(str(corpus))
        self.who = built["who"]
        svc_ref: dict = {}
        if self.live:
            from mentis.execution.mars import MarsExecution
            execution = MarsExecution(list(mars))
        else:
            execution = ScriptedExecution(profile, svc_ref)
        self.execution = execution
        # The port is chosen first, so agents are told where to call.
        handler = type("ConformanceHandler", (_Handler,), {})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.state = _State(str(corpus), str(self.workspace), answers_at=self.base,
                            execution=execution)
        handler.state = self.state
        svc_ref["svc"] = self.state.agents
        self.cv = self.state.cv
        self.owner = self.who["@brian"]
        # THE OWNER LOGS IN (round 3 final, B3): owner operations need an owner session. This
        # rig's Brain gets a credential of its own beside it (or the suite's, under pytest), with
        # a random passphrase held only in this process's memory, and the rig logs in with it.
        from mentis import owner_auth
        import secrets as _secrets
        self.credential = owner_auth.for_brain(str(corpus))
        self.owner_passphrase = None
        if not self.credential.configured():
            self.owner_passphrase = _secrets.token_urlsafe(24)
            self.credential.set_passphrase(self.owner_passphrase)
            self.owner_token = None
        else:   # the suite's credential: a session from it, as conftest does
            self.owner_token, _ = self.credential.issue(kind="bearer", label="conformance rig")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if self.owner_token is None:
            self.owner_token = self.owner_login()
        keep = getattr(self.state.agents, "keep_current", None)
        if callable(keep) and self.live:
            keep()

    def close(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        finally:
            try:
                self.state.agents.close()
            finally:
                self.state.corpus.close()

    # HTTP -------------------------------------------------------------------------------
    def owner_login(self) -> str:
        """A bearer session from the owner's passphrase, through `POST /api/owner/login`."""
        return self.post("/api/owner/login", {"passphrase": self.owner_passphrase,
                                              "token": True, "label": "conformance rig"},
                         owner=False)["token"]

    def post(self, path: str, payload: dict, *, owner: bool = True) -> dict:
        headers = {"Content-Type": "application/json",
                   # the owner's interface (mentis/web CLIENT_HEADER)
                   "X-Mentis-Client": "1"}
        if owner:
            headers["Authorization"] = f"Bearer {self.owner_token}"
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    # the owner ------------------------------------------------------------------------------
    def conversation(self, name: str) -> str:
        return self.post("/api/conversations", {"name": name})["conversation"]

    def participant(self, cid: str, alias: str) -> str:
        pid = self.cv.create_participant(alias)
        self.cv.join(pid, cid, attributed_to=self.owner)
        return pid

    def ask(self, cid: str, who: str, work: str, *, model: str | None = ...) -> str:
        """The owner asks `who` for `work`, bound to this rig's runtime (and model); the real
        dispatch runs it. Returns the request (expectation)."""
        spec = {"participant": who, "work": work, "runtime": self.runtime}
        m = self.model if model is ... else model
        if m:
            spec["model"] = m
        out = self.post(f"/api/conversations/{cid}/turns",
                        {"author": self.owner, "text": work, "action": "ask-participant",
                         "dispatch": [spec]})
        return out["expectations"][0]

    # the record ------------------------------------------------------------------------------
    def acts(self, caused_by: str) -> list[dict]:
        return list(self.cv.history(caused_by=caused_by))

    def runs(self, expectation: str) -> list[dict]:
        return [a for a in self.acts(expectation) if a["act"] == "execution-started"]

    def end_of(self, start: dict) -> dict | None:
        return self.cv.run_end(start["id"])

    def failures(self, expectation: str) -> list[dict]:
        return [a for a in self.acts(expectation)
                if a["act"] in ("execution-failed", "dispatch-failed", "run-failed")
                or a["act"].endswith("-failed")]

    def wait_runs_ended(self, expectation: str, n: int = 1, timeout: float = 600,
                        allow_failed: bool = True) -> list[dict]:
        """The first `n` runs of `expectation`, once each has ended (or the work failed before
        any started). Raises on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            runs = self.runs(expectation)
            if len(runs) >= n and all(self.end_of(r) for r in runs[:n]):
                return runs[:n]
            if not runs and allow_failed and self.failures(expectation):
                return []
            time.sleep(0.2 if not self.live else 1.0)
        raise TimeoutError(f"{expectation}: {n} run(s) did not end within {timeout:g} s "
                           f"({len(self.runs(expectation))} started)")

    def wait_live(self, expectation: str, timeout: float = 300) -> dict:
        """The run of `expectation` while it is live. Raises `EndedBeforeLive` AT ONCE
        when its run already ended, or the work failed before any run started: there is
        nothing left to wait for (N2: a failed dispatch no longer costs the full timeout)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            runs = self.runs(expectation)
            if runs and not self.end_of(runs[-1]):
                return runs[-1]
            if runs:
                raise EndedBeforeLive(runs[-1], self.end_of(runs[-1]))
            failed = self.failures(expectation)
            if failed:
                raise EndedBeforeLive(None, failed[-1])
            time.sleep(0.1 if not self.live else 0.5)
        raise TimeoutError(f"{expectation}: no live run within {timeout:g} s")

    def reply_of(self, start: dict) -> str:
        """The text the run said, as its end act records it, else the posted reply."""
        end = self.end_of(start) or {}
        d = end.get("detail") or {}
        if isinstance(d.get("final_text"), str) and d["final_text"]:
            return d["final_text"]
        return self.turn_text(end.get("turn"))

    def turn_text(self, turn: str | None) -> str:
        if not turn:
            return ""
        try:
            entry = self.cv.corpus.read([turn])[0]
        except Exception:                                 # noqa: BLE001
            return ""
        return " ".join(p.get("text") or "" for p in ((entry.get("body") or {}).get("parts") or ()))


class EndedBeforeLive(RuntimeError):
    """The work's run ended (or the work failed) before it was seen live."""

    def __init__(self, start: dict | None, end: dict | None):
        self.start, self.end = start, end
        end = end or {}
        super().__init__(f"ended before it was seen live: {end.get('act')} "
                         f"({(end.get('because') or '')[:200]})")


def fresh_root(base: str | None, label: str) -> Path:
    if base:
        p = Path(base) / f"{label}-{int(time.time() * 1000) % 10_000_000}"
        p.mkdir(parents=True, exist_ok=False)
        return p
    return Path(tempfile.mkdtemp(prefix=f"conf-{label}-"))
