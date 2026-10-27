"""What a Mark IV runtime adapter must provide.

The shape of this class is dictated by three measured runtimes, not by one.
Where they disagreed, the disagreement is preserved here rather than smoothed:

* Capacity is optional, and its shape is the runtime's. A runtime may have none
  to report, or fail to report it, so `observe_capacity` may legitimately
  return a reading that establishes nothing. Antigravity's belongs to groups
  of models rather than to one pool, so a window may carry a `group`.
* Model and effort are not always separable. Antigravity fuses them into one
  slug and errors if you pass both, so `Invocation` carries both and each
  adapter decides how they map onto its command line.
* Actual effort is observable on exactly one of the three. The return type is
  `Observed`, so "we could not see it" is expressible.
* Workspace is explicit. Claude and Codex honour process cwd; Antigravity does
  not, and wrote a file into its own scratch directory when asked to use the
  working directory. Every adapter is handed the workspace and must make its
  runtime honour it.
"""

from __future__ import annotations

import subprocess


def _decode(raw) -> tuple[str, bool]:
    """Decode runtime output as UTF-8, and say whether it was clean.

    Never raises and never silently discards. A lossy decode is reported as a
    transport problem rather than being mistaken for an empty result.
    """
    if raw is None:
        return "", True
    if isinstance(raw, str):
        return raw, True
    try:
        return raw.decode("utf-8"), True
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), False


def _safely(fn, *args) -> None:
    """Observation must never be the reason a run fails."""
    try:
        fn(*args)
    except Exception:                                     # noqa: BLE001
        pass


#: A later turn's result shorter than this share of the longest earlier one
#: is an aside, not a replacement answer (`substantive_answer`).
ASIDE_SHARE = 0.25


def substantive_answer(results: list[str]) -> str | None:
    """The run's answer, from the results of each turn it ended, in order.

    A runtime woken after it answered -- a background helper finishing, a
    wait running out -- ends one more turn and writes one more result.
    Measured 2026-10-27: a 6,668-character review was followed three seconds
    later by a 183-character "the background wait ran out, nothing to
    change", and taking the LAST result would have posted only that. So the
    answer is the latest result that is not an aside: one at least
    `ASIDE_SHARE` of the longest result's length. A later full answer still
    replaces an earlier one; only a much shorter afterthought does not.
    """
    said = [r for r in results if isinstance(r, str) and r.strip()]
    if not said:
        return None
    longest = max(len(r.strip()) for r in said)
    for r in reversed(said):
        if len(r.strip()) >= ASIDE_SHARE * longest:
            return r
    return said[-1]


def _stop_wanted(observer) -> tuple[str, str] | None:
    """(by, why) when the run's waiter should stop its process tree now: the
    run has settled, or somebody asked (`RunObservation.halt`). Never raises,
    and anything that is not a plain answer is read as no."""
    try:
        why = observer.settle_due()
        if isinstance(why, str) and why:
            return ("settled", why)
        halt = observer.halt_due()
        if isinstance(halt, dict) and halt.get("why"):
            return (str(halt.get("by") or "halt"), str(halt["why"]))
    except Exception:                                     # noqa: BLE001
        pass
    return None


def _observe_line(raw: bytes, observer, parse) -> None:
    """Hand one line of a runtime's stream to whoever reads that runtime.

    Decoded on its own, with replacement, for OBSERVATION ONLY: the run's
    result is decoded from the whole output afterwards, as it always was.
    """
    import json

    line = raw.decode("utf-8", errors="replace").strip()
    if not line.startswith("{"):
        return
    try:
        ev = json.loads(line)
    except ValueError:
        _safely(observer.not_understood)
        return
    if not isinstance(ev, dict):
        return
    try:
        if parse is not None:
            parse(ev, observer)
        else:
            observer.saw(str(ev.get("type") or ev.get("event") or "event"))
    except Exception:                                     # noqa: BLE001
        _safely(observer.not_understood)


def _stop_windows_tree(pid) -> bool:
    """Stop descendants using native handles; taskkill can be refused even
    for our own children in a restricted Windows execution environment."""
    import ctypes
    from ctypes import wintypes as W

    class Entry(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
                    ("heap", ctypes.c_size_t), ("module", W.DWORD),
                    ("threads", W.DWORD), ("parent", W.DWORD),
                    ("priority", W.LONG), ("flags", W.DWORD),
                    ("name", W.WCHAR * 260)]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    k.CreateToolhelp32Snapshot.restype = W.HANDLE
    k.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(Entry)]
    k.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(Entry)]
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    k.CloseHandle.argtypes = [W.HANDLE]
    snapshot = k.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    parents = {}
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        if not k.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            parents[entry.pid] = entry.parent
            if not k.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        k.CloseHandle(snapshot)
    descendants, seen = [], {pid}
    while True:
        children = [p for p, parent in parents.items() if parent in seen and p not in seen]
        if not children:
            break
        descendants.extend(children)
        seen.update(children)
    # Capture handles before terminating anything, so later PID reuse cannot
    # redirect a termination to a different process.
    handles = []
    ok = True
    try:
        for child in descendants + [pid]:
            handle = k.OpenProcess(1, False, child)  # PROCESS_TERMINATE
            if handle:
                handles.append(handle)
            elif ctypes.get_last_error() != 87:  # already exited
                ok = False
        for handle in reversed(handles[:-1]):
            ok = bool(k.TerminateProcess(handle, 1)) and ok
        if handles:
            ok = bool(k.TerminateProcess(handles[-1], 1)) and ok
    finally:
        for handle in handles:
            k.CloseHandle(handle)
    return ok


def _stop_tree(proc) -> None:
    """Stop a runtime and everything it started. Never raises."""
    import os

    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            if not _stop_windows_tree(proc.pid):
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, timeout=30)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:                                     # noqa: BLE001
        pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:                                     # noqa: BLE001
        pass


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from mentis.api.types import (
    Capability,
    CapacityReading,
    DeliveryOpportunity,
    ModelInfo,
    Observed,
    RuntimeInfo,
)


@dataclass
class Invocation:
    """What Foundation asks a runtime to do.

    `deliver` is material to put in front of the agent at start. Foundation owns
    the delivery mechanism; it does not own the content, and nothing in
    Foundation writes behavioural prose into this field.
    """

    workspace: str
    prompt: str
    model: str | None = None
    effort: str | None = None
    deliver: str | None = None
    #: THE RECORD THIS WORK BELONGS TO, so the worker can ask about it.
    #:
    #: A worker used to receive a prompt and a directory and nothing else.
    #: Asked a question about Mentis's own record it had no way to address
    #: that record, so it searched the filesystem -- which is what anybody
    #: would do with no interface. This is the corpus it may query, and a
    #: runtime that can expose a query surface exposes THIS one and no other.
    #:
    #: A runtime with no way to offer one leaves it unused. That is an honest
    #: gap rather than a reason to hand out a database path.
    record: str | None = None
    #: WHERE THE PROCESS THAT OWNS `record` ANSWERS QUESTIONS ABOUT IT.
    #:
    #: A worker sandboxed away from the corpus cannot open it even to
    #: read: the spine is WAL and SQLite writes beside a WAL database
    #: before it will read one. Widening the sandbox would make the
    #: worker's filesystem rights decide the record's, which is backwards.
    #: So the question travels to the owner instead, and this is the only
    #: thing a runtime hands the worker in order to ask it.
    answers_at: str | None = None
    #: THE OPAQUE GRANT THIS EXECUTION ASKS WITH.
    #:
    #: Not an identity and not a login -- one string that says this
    #: execution may ask the four reads about this corpus. It exists so
    #: that being able to REACH the server is not the same as being
    #: allowed to ask it anything, which is what it would be if the
    #: loopback interface were the boundary.
    capability: str | None = None
    #: WHAT THIS RUN MAY DO, so that what it is SHOWN matches it.
    #:
    #: Derived by Foundation from the grant's scope, never composed by an
    #: adapter and never reachable by a worker. An adapter uses it for two
    #: things: to tell the query surface which tools to offer, and to
    #: pre-approve exactly those and no others. It is not the authority --
    #: `/api/worker` checks the grant itself on every call -- it is what stops
    #: an ordinary worker being SHOWN operations that belong to a different
    #: kind of execution. Empty or None means the four reads.
    permits: tuple[str, ...] | None = None
    resume_ref: str | None = None
    #: REUSE THIS RUNTIME HOME rather than provisioning a new one, where a
    #: runtime keeps its session there. Continuity needs the same home:
    #: measured, a Codex thread cannot be resumed from a different one.
    runtime_home: str | None = None
    #: A DEADLINE, AND ONLY WHEN SOMEBODY ASKS FOR ONE.
    #:
    #: This was 600 seconds, silently, and it killed real work: a dispatched
    #: agent writing a file, running a command and running a test suite was
    #: stopped mid-task and recorded as FAILED because ten minutes had
    #: passed. Nothing about ten minutes was a fact about the work.
    #:
    #: WHAT IT WAS PROTECTING AGAINST is already handled elsewhere: a
    #: runtime that blocks forever waiting on stdin, measured on `codex
    #: exec`, which is why `_run` always supplies stdin and closes it. A
    #: wall clock was standing in for that and catching honest work too.
    #:
    #: So None means no deadline: the run ends when the process ends, and a
    #: BUSY execution stays BUSY while it is working. A number means the
    #: owner asked for a boundary, and reaching it is reported as reaching
    #: it rather than as a crash.
    timeout_s: int | None = None
    isolate: bool = True
    #: THIS EXECUTION'S PRIVATE SCRATCH -- see `mentis.foundation.scratch`.
    #: Where there is one, the run STARTS there and `workspace` is the project
    #: it is also given, by name. None means no record is attached (a probe,
    #: a test, the CLI), and the run starts in `workspace` as it always did.
    scratch: str | None = None
    #: WHERE ELSE THIS RUN MAY WRITE, beside its scratch and its project: the
    #: roots the server was started with (`--writable-root`). Each adapter puts
    #: them inside the boundary it already has, and where they are given the
    #: boundary also refuses what is outside -- see each adapter. Empty means
    #: the boundary is exactly what it was.
    writable: tuple[str, ...] = ()
    #: WHERE WHAT THE RUNTIME SAYS WHILE IT WORKS IS REPORTED, as it says it.
    #: A `mentis.foundation.observe.RunObservation`, owned by Foundation and
    #: never written anywhere. None means nobody is watching this run, and
    #: the run is performed exactly as it would be otherwise.
    observer: Any = None
    #: A SCRATCH ANSWER (`mentis.scratch_store`): a run that answers once and
    #: leaves nothing behind it. An adapter that honours it offers the run the
    #: Mentis read tools and NO built-in action or filesystem tools, keeps no resumable session,
    #: and never resumes one. An adapter that cannot honour it must refuse
    #: (`transient_ok` False) rather than run with more than it was given.
    transient: bool = False
    #: FOLDERS THE OWNER SELECTED for a Scratch answer to read and write in
    #: (owner ruling 2026-10-10: "it should operate within the folders I
    #: explicitly select"). Empty is today's Scratch: no native file tools.
    #: Only an adapter that ENFORCES the boundary (`folder_bounded`) is given
    #: any; Foundation refuses the rest before launch.
    access: tuple[str, ...] = ()
    #: OF `access`, THE FOLDERS THE OWNER CHOSE TO READ ONLY: the runtime may
    #: read them and must not change anything in them. Only meaningful where
    #: the run writes at all (`files == "write"`).
    read_only: tuple[str, ...] = ()
    #: What a Scratch run may do with files: "" none (no native file tools),
    #: "read" (read tools only, in `access` and its private scratch), or
    #: "write". Empty with `access` set means "write" -- what selected
    #: folders meant before read-only references existed.
    files: str = ""
    cancel_event: Any = None

    @property
    def file_mode(self) -> str:
        return self.files or ("write" if self.access else "")

    @property
    def cwd(self) -> str:
        """Where the process is started: private scratch, or the workspace."""
        return self.scratch or self.workspace

    @property
    def project(self) -> str | None:
        """The shared project directory, where it differs from `cwd`."""
        import os
        if self.scratch and self.workspace and (
                os.path.normcase(self.workspace)
                != os.path.normcase(self.scratch)):
            return self.workspace
        return None

    def __post_init__(self):
        # Measured: a relative workspace is accepted here, written into a
        # runtime's own trust configuration and passed as its working
        # directory, and the runtime then fails with an opaque OS error. The
        # caller's cwd is not the runtime's cwd, so a relative path has no
        # stable meaning by the time it is used.
        import os
        if self.workspace and not os.path.isabs(self.workspace):
            object.__setattr__(self, "workspace", os.path.abspath(self.workspace))


class RunCancelled(RuntimeError):
    """A run stopped because its caller cancelled it (a dismissed Scratch).
    Carries what the runtime had said by then in `output`, as
    `subprocess.TimeoutExpired` does for a deadline."""

    def __init__(self, message: str, output: bytes = b""):
        super().__init__(message)
        self.output = output


@dataclass
class RunResult:
    """What came back. Raw and unjudged.

    `reported` is the agent's own words. Foundation never treats it as evidence
    that work happened -- all three runtimes were observed returning exit 0 with
    a confident success message while the artifact was absent or misplaced.
    """

    session_ref: str | None
    exit_code: int
    reported: str | None
    actual_model: Observed
    actual_effort: Observed
    usage: dict[str, Any] = field(default_factory=dict)
    capacity: CapacityReading | None = None
    error: str | None = None
    raw_events: list[dict] = field(default_factory=list)
    #: Monetary cost the runtime itself reported for this execution, if any.
    #: Never computed from a pricing table -- only what the runtime volunteered.
    reported_cost_usd: float | None = None
    #: The runtime home this run actually used, so the session it created
    #: can be found again. None where the runtime keeps none.
    runtime_home: str | None = None
    #: True when a DEADLINE stopped this run. Distinct from a crash: the
    #: process was running and was stopped, so whatever had already been
    #: delivered to it had genuinely crossed.
    timed_out: bool = False

    #: TOOL CALLS THIS RUN ACTUALLY MADE, as the runtime itself reported
    #: them. An observation of one execution, never a property of a model:
    #: work that needed no tool produces an empty tuple, and that is not
    #: evidence of anything except that no tool was needed.
    tool_calls: tuple[str, ...] = ()

    #: Whether this runtime's own stream says anything about tool calls at
    #: all. Without it an empty `tool_calls` is ambiguous -- it could mean
    #: `none were made` or `we cannot see them here`, and those must not be
    #: recorded as the same fact.
    tool_calls_observable: bool = False
    #: HOW MANY REASONING ITEMS THIS RUN'S OWN STREAM CARRIED. The evidence
    #: for whether a requested effort was honoured: a provider can accept a
    #: setting and ignore it, and Ollama reports `reasoning_tokens: 0` whether
    #: or not the model reasoned. None means this runtime does not report
    #: reasoning at all, which is not the same answer as 0.
    reasoning_items: int | None = None
    #: WHAT THE RUNTIME REPORTED DOING TO FILES, read from its own stream by
    #: the adapter: each file a write tool named, with whether the runtime
    #: said it was done or refused. Empty where nothing was reported, which
    #: is not proof that nothing changed.
    actions: tuple[dict, ...] = ()
    #: DELETED MATERIAL A QUICK ASK WAS SERVED, filled by
    #: `Foundation.answer_once` from the door's own note -- never from what
    #: the agent wrote. Each is `{ref, deleted: {what, ref, when, by}}`.
    deleted_material: list = field(default_factory=list)
    #: Transport integrity, which is NOT process termination. Measured: a codex
    #: run exited 0 after 107 seconds of successful work and its entire output
    #: was lost to a decode failure, and Foundation reported exit=0, error=None,
    #: reported="". These three are separate observations and are now separate
    #: fields.
    transport_ok: bool = True
    transport_note: str | None = None

    #: WHAT THE RUNTIME ITSELF CALLED A WARNING, kept apart from `error`.
    #: A line the runtime labels a warning is not a statement that the run
    #: failed -- and where it is printed on every run, treating it as the
    #: failure reason names the wrong thing every time something else goes
    #: wrong. Preserved, never discarded, never promoted to `error`.
    warnings: tuple[str, ...] = ()

    #: RAW RUNTIME EVIDENCE, kept distinct from Mentis's interpretation of it.
    #: `error` is what Mentis will say went wrong; this is what the runtime
    #: actually emitted, so a failure can be reconstructed rather than
    #: re-guessed. Bounded, verbatim, and absent rather than invented when
    #: the runtime supplied nothing.
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def result_available(self) -> bool:
        """Did a result actually arrive? Not the same as the process exiting.

        A caller that checks only `exit_code` will read a lost result as
        success. That is the defect this property exists to make hard.
        """
        return bool(self.reported) and self.transport_ok


class RuntimeAdapter(ABC):
    """One measured runtime."""

    kind: str = "unknown"
    #: OTHER NAMES THIS RUNTIME GOES BY -- its executable, its product name --
    #: beside `kind`. Declared in `mentis.runtime_names` and read from there,
    #: so that a Participant can never be called by one of them
    #: (`conversation.participant_names`).
    names: tuple[str, ...] = ()
    #: The wire this runtime uses to reach a LOCAL provider, where one was
    #: measured. None means a model's tool use cannot be demonstrated for it,
    #: which leaves a model-dependent capability unknown -- and unknown
    #: satisfies nothing.
    local_tool_wire: str | None = None

    def dispatch_surface(self) -> dict | None:
        """What decides the tools a dispatched run of this runtime is
        offered, for a tool-use verdict's fingerprint. None: no verdict made
        for this runtime can be shown to still hold."""
        return None
    #: Whether `run` honours `Invocation.transient` -- read tools only, no
    #: built-in tools, no saved session. False refuses a Scratch answer on
    #: this runtime rather than running it with more than it was given.
    transient_ok: bool = False
    #: Whether `run` CONFINES file reads and writes to `Invocation.access`
    #: (and its own private scratch) and offers no unconfined shell. False
    #: refuses Scratch file work on this runtime; `folder_bounds_why` says
    #: what was measured instead. Never claimed without a measurement.
    folder_bounded: bool = False
    folder_bounds_why: str = ("this runtime has not been shown to confine "
                              "file access to selected folders")

    @abstractmethod
    def capabilities(self) -> frozenset[Capability]:
        """What THIS runtime genuinely does, as measured.

        A capability absent here makes the corresponding operation raise
        `Unsupported` at the seam rather than returning a fabricated answer.
        """

    @abstractmethod
    def discover(self, machine_id: str) -> RuntimeInfo: ...

    @abstractmethod
    def run(self, inv: Invocation) -> RunResult: ...

    def list_models(self) -> list[ModelInfo]:
        """Only runtimes that publish a catalogue override this."""
        return []

    def provider_of(self, model: str | None) -> str | None:
        """WHO SERVES THIS MODEL, as distinct from what HARNESSES it.

        THE THREE ARE NOT ONE FACT. `@ShortRound` is a Participant; `codex` is
        the harness that runs the invocation; `ollama` is what serves the
        weights; `llama3.2:latest` is the model. Collapsing provider into
        runtime is what let a local experiment be read as "Codex", and
        collapsing it into the model name would be guessing from a slug.

        None means this runtime serves the model itself, which is the ordinary
        hosted case and is a real answer rather than a missing one. A runtime
        that cannot tell inherits this default and says None honestly.
        """
        return None

    def passive_capacity(self, machine_id: str) -> CapacityReading | None:
        """Capacity this runtime can report WITHOUT SPENDING AN INVOCATION, or
        None. What selection reads; `observe_capacity` may cost a real run
        (Claude's does), and selecting must never pay for itself."""
        return None

    def observe_capacity(self, machine_id: str) -> CapacityReading:
        """Default: nothing established. Honest for a runtime that reports none."""
        import time

        return CapacityReading(
            runtime=self.kind,
            machine_id=machine_id,
            observed_at=time.time(),
            notes=("this runtime exposes no capacity information",),
        )

    def delivery_opportunities(self) -> list[DeliveryOpportunity]:
        """Only moments actually observed to work, each marked verified or not."""
        return []

    # -- consumption --------------------------------------------------------

    #: Names this runtime's token accounting. Two runtimes sharing a field name
    #: do not share its meaning, so the model is labelled rather than assumed.
    accounting = "unknown"

    #: Whether an execution's usage can be read back after the run returns.
    reobservable = False

    def consumption(self, res: "RunResult") -> "Consumption | None":
        """What this one execution consumed, in this runtime's own accounting.

        The base implementation exposes only the one field measured to mean the
        same thing everywhere -- `output_tokens`, reasoning included -- and
        preserves everything else verbatim in `native`. Cost is reported only
        where the runtime itself volunteers it; nothing is priced here.
        """
        from mentis.api.types import Consumption, Observed, Provenance

        usage = res.usage or {}
        if not usage:
            return None
        out = usage.get("output_tokens")
        return Consumption(
            runtime=self.kind,
            accounting=self.accounting,
            native=dict(usage),
            output_tokens=(
                Observed(out, Provenance.PROVIDER_REPORTED,
                         note="generated tokens, reasoning/thinking included")
                if isinstance(out, int)
                else Observed.unknown("runtime reported no output_tokens")
            ),
            reported_cost_usd=Observed.unknown(
                f"{self.kind} reports no monetary cost for an execution"
            ),
            reobservable=self.reobservable,
        )

    def resume_eligibility(self, *, session_ref: str | None,
                           workspace: str | None = None,
                           runtime_home: str | None = None):
        """Can this runtime still continue that session, and on what evidence.

        ASKED, NOT INFERRED. The presence of a session reference says only
        that one was issued once. Whether it can still be continued is a
        fact about the runtime's own storage, so the runtime is asked.

        The default is UNKNOWN because that is the honest answer for a
        runtime that exposes nothing to look at. Nothing is adopted on an
        UNKNOWN, so a runtime that cannot answer costs continuity rather
        than correctness.
        """
        from mentis.api.types import ResumeEligibility
        return ResumeEligibility.unknown(
            f"{self.kind} exposes nothing that says whether a session "
            "can still be continued")

    def project_writable(self) -> bool:
        """Whether this runtime can write a project given beside its scratch."""
        return True

    @staticmethod
    def _discard_scratch(*paths: str | None) -> None:
        """Remove per-invocation scratch once the run is over.

        SCRATCH IS NOT A SESSION, which is the whole distinction. A
        Codex home holds the rollout a thread can be continued from, so
        it is kept until Mentis relinquishes that session. These hold a
        settings file, an MCP registry, a redirected home with neither --
        nothing anybody could continue -- so they go when the process
        that needed them exits.

        MEASURED: 52 `mk4-claude-*`, 16 `mk4-tools-*` and 7
        `mk4-agy-home-*` directories had accumulated in %TEMP%, one per
        run since the beginning, because nothing ever removed them.

        Never raises. Failing to tidy up must not fail a run that worked.
        """
        import shutil
        for path in paths:
            if path:
                shutil.rmtree(path, ignore_errors=True)

    def discard_session_home(self, runtime_home: str | None) -> str | None:
        """Let go of a runtime home THIS adapter provisioned. Says what it did.

        Only ever called when Mentis has declared it will not continue
        that session again, and only for a home Mentis created. A runtime
        that keeps its sessions in the user's own home has nothing to
        discard and says so -- it must never reach into that.
        """
        return None

    def liveness_of_pid(self, pid: int | None) -> bool:
        """Is this process still running? Checked against the OS, not a registry."""
        if pid is None:
            return False
        try:
            import os
            import signal

            if os.name == "nt":
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return str(pid) in out.stdout
            os.kill(pid, 0)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    # -- helpers shared by adapters ----------------------------------------

    @staticmethod
    def _which(name: str) -> str | None:
        import shutil

        return shutil.which(name)

    @staticmethod
    def _partial(exc: subprocess.TimeoutExpired) -> str:
        """What a stopped run had already said, decoded.

        A deadline is not a reason to throw away the session identifier the
        runtime already announced. Review found every adapter discarding
        `TimeoutExpired.stdout`, which on a first run is the only place the
        new session is named -- so a run stopped at a boundary somebody
        chose became unresumable, defeating the point of distinguishing a
        deadline from a crash.
        """
        raw = exc.stdout or b""
        if isinstance(raw, str):
            return raw
        return _decode(raw)[0]

    # -- watching a run while it runs ----------------------------------------

    #: What THIS runtime's own structured stream can establish while it runs,
    #: as measured -- never assumed from another runtime. See each adapter.
    observes: tuple[str, ...] = ()

    def observe_event(self, ev: dict, obs) -> None:
        """Report what one event of this runtime's stream establishes.

        The default establishes only that the runtime said something. An
        adapter that has measured its runtime's stream says more, and nothing
        it does not understand is turned into a claim.
        """
        obs.saw(str(ev.get("type") or ev.get("event") or "event"))

    @staticmethod
    def _run(cmd: list[str], *, cwd: str | None = None,
             timeout: int | None = 60,
             env: dict[str, str] | None = None,
             stdin: str | None = None,
             observer=None, parse=None, cancel_event=None) -> subprocess.CompletedProcess:
        """Run a runtime, reading what it says AS IT SAYS IT.

        `stdin` matters more than it looks. A multiline prompt passed as an argv
        element to Claude's Windows .CMD shim was measured to produce six bytes
        of output and exit code 0 -- a silent total failure. Prompts go on stdin
        where the runtime accepts them there.

        THE OUTPUT IS READ WHILE THE PROCESS RUNS, and that is the only change.
        All three runtimes stream structured events -- a tool starting, a tool
        finishing, a turn ending -- and this used to hold all of it until the
        process exited, so nothing was observable of a run in progress. Each
        stdout line is now handed to `parse(event, observer)` as it arrives.
        What comes back is exactly what came back before: the same bytes,
        decoded the same way, once, at the end. Observation can neither fail
        a run nor change its result: an event that cannot be read is counted
        and skipped, and a parser that raises is counted and ignored.

        A DEADLINE STOPS THE WHOLE TREE. The runtimes are launched through
        shims (`claude.CMD` is `cmd.exe` running `node`), so stopping only the
        direct child left the runtime running and its pipes open -- and the
        read of what it had said then waited on them.
        """
        import os
        import threading

        full_env = None
        if env:
            full_env = dict(os.environ)
            full_env.update(env)
        # Bytes, decoded here rather than by subprocess. Measured: `text=True`
        # decodes with the platform default (cp1252 on Windows), and a single
        # non-decodable byte killed the reader thread and discarded the whole
        # of a successful run's output while the process still exited 0.
        extra = {} if os.name == "nt" else {"start_new_session": True}
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=full_env, shell=False,
            # No input means the child inherits ours, exactly as
            # `subprocess.run(input=None)` did; with input, it is written
            # and closed so a runtime waiting on stdin sees its end.
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **extra)
        if observer is not None:
            _safely(observer.launched, proc.pid)
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []

        def pump_stdout():
            for raw in iter(proc.stdout.readline, b""):
                out_chunks.append(raw)
                if observer is not None:
                    _observe_line(raw, observer, parse)

        def pump_stderr():
            err_chunks.append(proc.stderr.read())

        def feed():
            try:
                proc.stdin.write(stdin.encode("utf-8"))
            except OSError:
                pass            # it exited without reading; its output says why
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        threads = [threading.Thread(target=pump_stdout, daemon=True),
                   threading.Thread(target=pump_stderr, daemon=True)]
        if stdin is not None:
            threads.append(threading.Thread(target=feed, daemon=True))
        for t in threads:
            t.start()
        def finish(bound=None):
            for t in threads:
                t.join(bound)
            # Closing a buffered pipe while its reader still holds its lock
            # can block forever if the OS refused to stop a descendant.
            if not any(t.is_alive() for t in threads):
                for pipe in (proc.stdout, proc.stderr):
                    try:
                        pipe.close()
                    except OSError:
                        pass
            if observer is not None:
                _safely(observer.exited, proc.returncode)

        # A RUN IS OVER WHEN ITS RUNTIME SAYS SO, not only when its process
        # exits. Measured 2026-10-27: a run wrote its answer and ended its
        # turn, and its process lived on indefinitely because of a background
        # shell loop it had left behind -- and with no deadline, this wait
        # never returned and the answer was never recorded. While an observer
        # can say the run has settled (`RunObservation.settle_due`), or that
        # somebody asked for it to be stopped (`halt`), the wait asks it.
        stop = None
        watching = observer is not None and callable(
            getattr(observer, "settle_due", None))
        try:
            if cancel_event is None and not watching:
                proc.wait(timeout=timeout)
            else:
                import time
                end = None if timeout is None else time.monotonic() + timeout
                while proc.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RunCancelled("Scratch answer cancelled")
                    if end is not None and time.monotonic() >= end:
                        raise subprocess.TimeoutExpired(cmd, timeout)
                    if watching:
                        stop = _stop_wanted(observer)
                        if stop is not None:
                            break
                    try:
                        proc.wait(timeout=0.1 if cancel_event is not None
                                  else 1.0)
                    except subprocess.TimeoutExpired:
                        pass
        except subprocess.TimeoutExpired:
            _stop_tree(proc)
            finish(10)
            raise subprocess.TimeoutExpired(
                cmd, timeout, output=b"".join(out_chunks),
                stderr=b"".join(err_chunks))
        except BaseException as exc:
            # Nothing that interrupts the wait may leave a runtime running.
            _stop_tree(proc)
            finish(10)
            if isinstance(exc, RunCancelled):
                # WHAT IT HAD ALREADY SAID, as a deadline carries it: a file
                # written before the cancel is written, and is reported.
                exc.output = b"".join(out_chunks)
            raise
        returncode = None
        if stop is not None and proc.poll() is None:
            # Stopped HERE, whole tree, and said so on the observation. A
            # settled run's runtime already reported success for the turn
            # that answered, so what it said is read as a clean exit; a run
            # stopped on request did not finish and is read as stopped.
            _stop_tree(proc)
            finish(10)
            _safely(observer.stopped, *stop)
            returncode = 0 if stop[0] == "settled" else -1
        else:
            finish()

        stdout, out_ok = _decode(b"".join(out_chunks))
        stderr, err_ok = _decode(b"".join(err_chunks))
        completed = subprocess.CompletedProcess(
            proc.args, proc.returncode if returncode is None else returncode,
            stdout, stderr)
        # Carried out of band so every adapter can report it without each one
        # having to remember to.
        completed.transport_ok = out_ok and err_ok          # type: ignore[attr-defined]
        completed.transport_note = None                      # type: ignore[attr-defined]
        if not (out_ok and err_ok):
            completed.transport_note = (                     # type: ignore[attr-defined]
                "output was not valid UTF-8 and was decoded with replacement; "
                "the result may be incomplete")
        return completed
