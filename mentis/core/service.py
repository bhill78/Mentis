"""The implementation of the public seam.

There is exactly one of these. The CLI does not have its own path to a runtime,
and the HTTP ingress does not get one either -- they both call these methods.

AGENT EXECUTION IS MARS (`mentis.execution`). Mark IV's Foundation -- runtime
adapters, provisioned homes, private scratch, session adoption, capacity
probes -- is gone; this service reaches an agent only through an `Execution`:
its catalogue (`backends`), one blocking run (`perform`), `cancel` and
`running`. What a run may ask of the record is `mentis.authority`, moved here
from Foundation unchanged.

What is kept is the coordination around a run: an `Instance` per summoned
agent, recorded in the instance corpus; the selection and its `because`; the
grant minted for a run and revoked when it ends; and the mapping of what MARS
reported (`RunResult`) onto the `WorkOutcome` callers already read.
"""

from __future__ import annotations

import math
import sys
import threading
import time
import uuid

from dataclasses import replace

from mentis.api.errors import (
    CorpusNotAttached,
    InstanceNotFound,
    RuntimeNotPresent,
    Unsupported,
)
from mentis.api.types import (
    Address,
    Capability,
    CapacityReading,
    DeliveryOpportunity,
    Instance,
    Liveness,
    ModelInfo,
    Observed,
    Provenance,
    ReleaseResult,
    RuntimeInfo,
    Selection,
    UsageWindow,
    WorkOutcome,
)
from mentis.authority import Authority
from mentis.corpus.store import Corpus, machine_id, require
from mentis.execution import Execution, RunEvent, RunResult, RunSpec
from mentis.core import routing
from mentis.core.run_feed import RunFeed

#: What a run's terminal is when MARS reports the turn ended normally.
REPORTED_DONE = "reported_done"

#: Selection's word for a runtime whose capacity MARS did not report.
_NO_CAPACITY = "capacity not reported by MARS"

#: Whether a task's difficulty picks the run's effort (Mark IV's rule). Off:
#: unrequested effort stays the runtime's own default until the owner decides.
_EFFORT_FROM_DIFFICULTY = False

#: How long one `_mars/capacity` answer serves every runtime's `capacity_observe`
#: (the web layer asks runtime by runtime; MARS answers for all at once).
CAPACITY_REUSE_S = 30.0

#: How long a caller that asks to wait for a `_mars/capacity` read waits.
#: Selection never does (WS-P, `prefer_held`): it decides on what is held, or
#: with capacity unknown when nothing is, and a newer answer is read in the
#: background. Waiting here was the 5 s spike in selection -> execution-started,
#: and, with nothing held, the ~1.6 s of a server's first selection.
CAPACITY_WAIT_S = 5.0

#: How long a capacity answer MARS marked `pending` (or an empty one) is held
#: before the next caller asks again.
CAPACITY_PENDING_S = 5.0

#: From what age a held `mars/backends` answer has a newer one read in the
#: background (WS-P). The held one is used meanwhile, whatever its age.
BACKENDS_REFRESH_S = 45.0

#: How often `keep_current` refreshes the held catalogue, and for how long
#: after the last dispatch it goes on doing so. An idle server asks MARS
#: nothing: no probes, and never a capacity read (which starts `/usage`).
KEEP_BACKENDS_S = 50.0
ACTIVE_WINDOW_S = 600.0

#: How old a held answer the judge paths (`execution_usable`, the default
#: `capacity_view`) still use. They never ask MARS; past this they have none.
CAPACITY_STALE_S = 600.0

#: The cooldown a quota failure with no reported reset is held for (owner,
#: 2026-10-29; the holds are made in `mentis.web.quota`). Here only to say
#: when a refusal rests on it alone.
QUOTA_COOLDOWN_S = 3600.0

#: How far past its nominal length a reported reset may lie and the window still
#: be current (#1167): a window nobody has touched reports its reset as the time
#: of the call plus its length, and the reading is stamped before the call. The
#: lower edge only: a window in its last seconds is as live as it ever was.
RESET_WINDOW_SLOP_S = 300

#: The share of its budget left at which a runtime may not be passed over
#: indefinitely (#1167). A chosen number and an intended cliff: at 0.50 the
#: anti-starvation guard applies, just under it never does.
GUARD_SUBSTANTIAL = 0.50


def _number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _span(seconds: float) -> str:
    """A duration as a person reads it: `3d 4h`, `5h 12m`, `40m`."""
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _figure(w: UsageWindow, now: float) -> str:
    """One window as its runtime reported it: used, left, and when it
    resets. Never compared with another runtime's."""
    left = 1.0 - w.used_fraction
    out = (f"{w.group + ' ' if w.group else ''}{w.label} "
           f"{w.used_fraction:.0%} used, {left:.0%} left")
    if _number(w.resets_at):
        out += f", resets in {_span(float(w.resets_at) - now)}"
    return out


class MentisService:
    """Implements `mentis.api.MentisAPI` over an `Execution`."""

    def __init__(self, corpus_path: str | None = None, *,
                 execution: Execution | None = None) -> None:
        self._corpus: Corpus | None = None
        self.execution: Execution = execution or unavailable_execution(
            "no execution was configured for this service")
        #: WHAT A RUN MAY ASK, AND FOR HOW LONG (`mentis.authority`).
        self.authority = Authority()
        self._machine = machine_id()
        #: Per-call continuity notes. Dispatch runs on its own thread.
        self._thread = threading.local()
        self._lock = threading.RLock()
        # Live instances, this process, this machine. Never durable.
        self._live: dict[str, Instance] = {}
        #: The run each handle is inside now, and what this process observed
        #: of each run it holds -- keyed by the run (its `execution-started`
        #: act), never by the handle many runs pass through.
        self._runs: dict[str, dict] = {}
        #: (run, instance, request, observation) -> option id, None to
        #: refuse, or ... to leave it to the execution. Set by the web layer.
        self.permission_policy = None
        #: (run, workspace) -> the run's consent for MARS ({"mode",
        #: "workspaces"}) or None. Set by the web layer, beside the policy.
        self.run_consent = None
        #: (run, workspace, runtime) -> what the consent adds to the run's
        #: MARS options. Set by the web layer, beside the consent.
        self.run_options = None
        #: (run, instance, delivered, mcp_servers) -> the run's tooling
        #: function for MARS execution (`RunSpec.tooling`), or None. Set by
        #: the web layer, beside the consent (docs/tooling-context.md).
        self.run_tooling = None
        self._run_of: dict[str, str] = {}
        #: WHEN EACH RUNTIME WAS LAST SELECTED, as a sequence number, for the
        #: tie-break in `execution_select`. This process only.
        self._last_selected: dict[str, int] = {}
        self._selections = 0
        #: HOW MANY AUTOMATIC CHOICES PASSED EACH RUNTIME OVER while it was a
        #: known candidate, for the guard in `_by_capacity`. Named, continuity
        #: and narrowed-away traffic never touch it. This process only.
        self._guard_missed: dict[str, int] = {}
        #: The last `_mars/capacity` answer, when it was read (monotonic) and,
        #: when it is empty because the read failed, why. Failures are kept.
        self._capacity: tuple[float, dict, str | None] | None = None
        #: The `_mars/capacity` read in flight, if one is (single flight).
        self._capacity_flight: threading.Event | None = None
        #: MARS's catalogue as last read: (monotonic, MARS generation,
        #: backends), and whether a background refresh is in flight.
        self._backends_held: tuple[float, object, list[dict]] | None = None
        self._backends_flight = False
        #: `keep_current`'s stop signal, once it runs, and when a dispatch
        #: last began (monotonic; `note_activity`).
        self._keeper: threading.Event | None = None
        self._last_activity: float | None = None
        #: The record dispatched workers may query, and where this process
        #: answers about it (`workers_read`).
        self._record: str | None = None
        self._answers_at: str | None = None
        self._writable: tuple[str, ...] = ()
        if corpus_path:
            self.corpus_attach(corpus_path)

    # -- corpus -------------------------------------------------------------

    def corpus_attach(self, path: str) -> dict:
        c = Corpus(path)
        if not c.is_corpus:
            c.create()
        self._corpus = c
        return {**c.identity(), "attached_path": c.path, "machine_id": self._machine}

    def workers_read(self, corpus_path: str | None,
                     *, answers_at: str | None = None,
                     writable: tuple[str, ...] = ()) -> None:
        """Name the record dispatched workers may query, and where.

        NOT the instance corpus this service attaches. The record a worker is
        asked questions ABOUT is the spine, and only the caller that opened
        the spine knows where it is, so it is said explicitly rather than
        inferred from what happens to be attached here.
        """
        self._record = corpus_path
        self._answers_at = answers_at
        self._writable = tuple(writable)

    def corpus_status(self) -> dict:
        if self._corpus is None:
            raise CorpusNotAttached("no corpus attached")
        return {
            **self._corpus.identity(),
            "attached_path": self._corpus.path,
            "machine_id": self._machine,
            "history_records": len(self._corpus.instance_history()),
        }

    # -- runtimes: MARS backends ---------------------------------------------

    def _backends(self) -> list[dict]:
        """MARS's catalogue (`mars/backends`), HELD (WS-P). One dispatch asks
        for it several times (binding judge, selection, eligibility, summon,
        provider), and each ask was a round trip to MARS -- which itself
        re-probes every backend, up to 10 s (a runtime whose initialize does
        not answer costs all of it), once its own 60 s cache lapses.

        NOTHING ON THE DISPATCH PATH WAITS FOR IT ONCE ANY ANSWER IS HELD: a
        held catalogue is used whatever its age, and one older than
        `BACKENDS_REFRESH_S`, or from a MARS process since replaced
        (`generation`), has a newer one read in the background. Only when
        nothing was ever held does the caller wait for MARS. `keep_current`
        primes it at server start and keeps it current while idle. Kept only
        for an execution that says which MARS process answered
        (`generation`); an empty answer (MARS unreachable) is never kept."""
        gen = getattr(self.execution, "generation", None)
        if gen is None:
            return self._backends_read()
        now = time.monotonic()
        with self._lock:
            held = self._backends_held
            start = (held is not None and (held[1] != gen
                                           or now - held[0] >= BACKENDS_REFRESH_S)
                     and not self._backends_flight)
            if start:
                self._backends_flight = True
        if held is not None:
            if start:
                threading.Thread(target=self._backends_refresh,
                                 name="mentis-backends", daemon=True).start()
            return [dict(b) for b in held[2]]
        got = self._backends_read()
        self._backends_keep(got)
        return got

    def _backends_read(self) -> list[dict]:
        try:
            return [b for b in (self.execution.backends() or [])
                    if isinstance(b, dict) and b.get("id")]
        except Exception:                                 # noqa: BLE001
            return []

    def _backends_keep(self, got: list[dict]) -> None:
        gen = getattr(self.execution, "generation", None)
        with self._lock:
            if got and gen is not None:
                self._backends_held = (time.monotonic(), gen,
                                       [dict(b) for b in got])

    def _backends_refresh(self) -> None:
        try:
            self._backends_keep(self._backends_read())
        finally:
            with self._lock:
                self._backends_flight = False

    def note_activity(self) -> None:
        """A dispatch is happening: `keep_current` keeps the catalogue current
        for `ACTIVE_WINDOW_S` after the latest one."""
        self._last_activity = time.monotonic()

    def keep_current(self) -> None:
        """Prime the held catalogue now, in the background, and keep it current
        every `KEEP_BACKENDS_S` while there has been a dispatch within
        `ACTIVE_WINDOW_S` (`note_activity`); an idle server asks MARS nothing.
        Capacity is never read to keep it warm: selection uses what is held,
        and dispatch starts a read when it begins (`capacity_prime`). Only for
        an execution that says which MARS process answers (`generation`). One
        keeper per service; it stops when the service closes. A refresh that
        fails keeps what is held."""
        if getattr(self.execution, "generation", None) is None:
            return
        with self._lock:
            if self._keeper is not None:
                return
            self._keeper = threading.Event()
            stop = self._keeper

        def keep() -> None:
            first = True
            while not stop.is_set():
                active = (self._last_activity is not None and time.monotonic()
                          - self._last_activity < ACTIVE_WINDOW_S)
                if first or active:
                    first = False
                    try:
                        with self._lock:
                            busy = self._backends_flight
                            if not busy:
                                self._backends_flight = True
                        if not busy:
                            self._backends_refresh()
                    except Exception:                     # noqa: BLE001
                        pass
                stop.wait(KEEP_BACKENDS_S)

        threading.Thread(target=keep, name="mentis-keep-current",
                         daemon=True).start()

    def backends_invalidate(self) -> None:
        """Forget the held catalogue: the next read asks MARS."""
        with self._lock:
            self._backends_held = None

    def _backend(self, runtime: str) -> dict | None:
        return next((b for b in self._backends() if b["id"] == runtime), None)

    def runtime_names(self) -> list[str]:
        """Every runtime MARS lists, available or not."""
        return sorted(b["id"] for b in self._backends())

    def runtimes_discover(self) -> list[RuntimeInfo]:
        out = []
        for b in self._backends():
            caps = {Capability.DISCOVER, Capability.INVOKE_HEADLESS}
            if "stdio" in ((b.get("supports") or {}).get("mcp") or ()):
                caps.add(Capability.CALL_MENTIS_TOOLS)
            if b.get("models"):
                caps.update((Capability.LIST_MODELS, Capability.REQUEST_MODEL))
            if b.get("efforts"):
                caps.add(Capability.REQUEST_EFFORT)
            # WHAT MARS KNOWS OF IT: measured or declared capabilities, and
            # what it is known to lack, with the evidence. Nothing else is
            # claimed; a name in neither is unknown.
            names = {c.value for c in Capability}
            caps.update(Capability(c) for c in b.get("capabilities") or ()
                        if c in names)
            notes = [f"MARS backend ({b.get('kind') or 'unknown kind'})"]
            raw_lacks = b.get("lacks") or {}
            for name, why in (raw_lacks.items() if isinstance(raw_lacks, dict)
                              else ((x, "") for x in raw_lacks)):
                notes.append(f"lacks {name}" + (f": {why}" if why else ""))
            if not b.get("available"):
                notes.append(f"not available: {b.get('reason') or 'MARS gave no reason'}")
            out.append(RuntimeInfo(
                kind=b["id"],
                # PRESENT MEANS MARS CAN RUN IT NOW. Installed but unavailable
                # (signed out, missing a key) is not a runtime work can go to.
                present=bool(b.get("available")),
                version=(Observed(b.get("version"), Provenance.PROVIDER_REPORTED)
                         if b.get("version") else
                         Observed.unknown("MARS reported no version")),
                executable=Observed.unknown("run by MARS"),
                capabilities=frozenset(caps),
                machine_id=self._machine,
                notes=tuple(notes)))
        return out

    def models_list(self, runtime: str) -> list[ModelInfo]:
        b = self._backend(runtime)
        if b is None:
            raise RuntimeNotPresent(f"unknown runtime: {runtime}")
        if not b.get("models"):
            raise Unsupported(runtime, "list_models",
                              "MARS lists no models for this backend")
        efforts = tuple(str(e) for e in b.get("efforts") or ())
        names = b.get("modelNames") if isinstance(b.get("modelNames"), dict) else {}
        # WHO SERVES IT, as MARS's catalogue says (`modelProviders`), never guessed from
        # the slug here: absent means the runtime serves the model itself.
        providers = b.get("modelProviders") if isinstance(b.get("modelProviders"), dict) else {}
        out = []
        for m in b["models"]:
            slug = m.get("id") if isinstance(m, dict) else m
            if not slug:
                continue
            details = dict(m) if isinstance(m, dict) else {}
            # WHERE THE LIST CAME FROM, as MARS says it (`modelsFrom`): an
            # agent's own model option, or `agy models`.
            details.setdefault("catalogue", b.get("modelsFrom"))
            out.append(ModelInfo(
                slug=str(slug), runtime=runtime, efforts=efforts,
                display_name=((m.get("name") if isinstance(m, dict) else None)
                              or names.get(str(slug)) or None),
                provider=providers.get(str(slug)),
                details=details))
        return out

    def _capacity_read(self, flight: threading.Event) -> None:
        """One `_mars/capacity` read, on its own thread. Whatever it gives --
        an answer, an empty one, or a failure -- is kept for
        `CAPACITY_REUSE_S`, so a MARS that cannot answer is not asked again
        by every caller behind it."""
        read = getattr(self.execution, "capacity", None)
        why = None
        try:
            report = read() if callable(read) else {}
        except Exception as exc:                          # noqa: BLE001
            report, why = {}, f"MARS's capacity read failed ({exc})"
        if not isinstance(report, dict):
            report, why = {}, "MARS's capacity answer was not a report"
        # A PENDING OR EMPTY ANSWER IS NOT AN ANSWER TO KEEP: MARS was still
        # taking its reading (`pending: true`). It is held, so nothing waits,
        # but only for `CAPACITY_PENDING_S`, after which the next caller
        # starts another read; its runtimes read as unknown meanwhile.
        at = time.monotonic()
        if (not report and why is None) or any(
                isinstance(v, dict) and v.get("pending") is True
                for v in report.values()):
            at -= max(0.0, CAPACITY_REUSE_S - CAPACITY_PENDING_S)
        with self._lock:
            self._capacity = (at, report, why)
            self._capacity_flight = None
        flight.set()

    def capacity_prime(self) -> None:
        """Start a `_mars/capacity` read in the background if the held answer
        is missing or older than `CAPACITY_REUSE_S` and none is in flight.
        Never waits. Dispatch calls it as it begins, so the read overlaps the
        record reads that come before selection."""
        now = time.monotonic()
        with self._lock:
            held = self._capacity
            if self._capacity_flight is not None or (
                    held is not None and now - held[0] < CAPACITY_REUSE_S):
                return
            flight = self._capacity_flight = threading.Event()
        threading.Thread(target=self._capacity_read, args=(flight,),
                         name="mentis-capacity", daemon=True).start()

    def _capacity_answer(self, wait: float | None = None, *,
                         cached_only: bool = False,
                         prefer_held: bool = False) -> tuple[dict, str | None]:
        """MARS's `_mars/capacity` and, when it says nothing, why.

        SINGLE FLIGHT. `_mars/capacity` can start runtime processes and take
        over a minute, so one read is in flight at a time, on its own
        thread, and every caller shares it. `wait` bounds how long THIS
        caller waits for it (None: until it answers); a caller that stops
        waiting gets the last answer already held, and the read goes on.

        `cached_only` never asks MARS: the answer already held, up to
        `CAPACITY_STALE_S` old, or nothing. What the judge paths use.

        `prefer_held` is selection's (WS-P): any answer already held is used
        AT ONCE, whatever its age, and one older than `CAPACITY_REUSE_S` has a
        newer one read in the background for the next decision. Only when
        nothing is held at all does the caller wait, at most `wait`. Quota
        holds come from the record, not from this, so a runtime that just
        failed for quota is held whatever the capacity answer's age.
        """
        now = time.monotonic()
        with self._lock:
            held = self._capacity
            if cached_only:
                if held is not None and now - held[0] < CAPACITY_STALE_S:
                    return held[1], held[2]
                return {}, ("no capacity report is held yet, and this judgement "
                            "does not ask MARS for one")
            if held is not None and now - held[0] < CAPACITY_REUSE_S:
                return held[1], held[2]
            if prefer_held:
                # NOTHING HELD YET (a server's first dispatch, before its
                # start-up read has landed) is not waited for either: the
                # runtimes read as unknown, as MARS's own first answer for a
                # `/usage` runtime would say anyway (`pending`), and the
                # record's quota holds still apply.
                answer = ((held[1], held[2]) if held is not None else
                          ({}, "no capacity answer is held yet; MARS is being "
                               "asked in the background"))
                start = self._capacity_flight is None
                if start:
                    flight = self._capacity_flight = threading.Event()
                if start:
                    threading.Thread(target=self._capacity_read, args=(flight,),
                                     name="mentis-capacity", daemon=True).start()
                return answer
            flight = self._capacity_flight
            start = flight is None
            if start:
                flight = self._capacity_flight = threading.Event()
        if start:
            threading.Thread(target=self._capacity_read, args=(flight,),
                             name="mentis-capacity", daemon=True).start()
        if flight.wait(wait):
            with self._lock:
                held = self._capacity
            if held is not None:
                return held[1], held[2]
        got, _ = self._capacity_answer(cached_only=True)
        return got, (None if got else
                     f"MARS's capacity answer did not arrive within {wait:g} s")

    def _capacity_report(self) -> dict:
        """MARS's `_mars/capacity`, reused for `CAPACITY_REUSE_S`. An
        Execution without it, or a failed read, is an empty answer."""
        return self._capacity_answer()[0]

    def capacity_observe(self, runtime: str) -> CapacityReading:
        """What MARS says is left of this runtime's quota (`_mars/capacity`),
        windows kept separate and in the runtime's own labels. A runtime MARS
        reports nothing for is an empty reading saying why -- never zero."""
        return self._reading(runtime, *self._capacity_answer())

    def _reading(self, runtime: str, report: dict,
                 why_none: str | None = None) -> CapacityReading:
        """One runtime's reading out of a `_mars/capacity` answer."""
        r = report.get(runtime)
        now = time.time()
        if isinstance(r, dict) and r.get("pending") is True:
            # MARS HAS NO READING YET: unknown, never "no quota" or "plenty",
            # whatever an in-band figure beside it says. Quota holds from the
            # record still apply.
            return CapacityReading(runtime=runtime, machine_id=self._machine,
                                   observed_at=now, notes=(
                                       f"MARS is still taking {runtime}'s capacity "
                                       f"reading (pending)",))
        if not isinstance(r, dict):
            return CapacityReading(runtime=runtime, machine_id=self._machine,
                                   observed_at=now, notes=(
                                       why_none or f"{_NO_CAPACITY} for {runtime}",))
        windows = []
        for w in r.get("windows") or ():
            if not isinstance(w, dict) or not w.get("label"):
                continue
            used = w.get("usedFraction")
            windows.append(UsageWindow(
                label=str(w["label"]),
                used_fraction=float(used) if isinstance(used, (int, float))
                and not isinstance(used, bool) else None,
                window_seconds=w.get("windowSeconds")
                if isinstance(w.get("windowSeconds"), int) else None,
                resets_at=w.get("resetsAt")
                if isinstance(w.get("resetsAt"), (int, float)) else None,
                provenance=Provenance.PROVIDER_REPORTED,
                raw=dict(w.get("raw") or {}),
                group=w.get("group") if isinstance(w.get("group"), str) else None))
        groups = r.get("modelGroups") if isinstance(r.get("modelGroups"), dict) else {}
        observed = r.get("observedAt")
        return CapacityReading(
            runtime=runtime, machine_id=self._machine,
            observed_at=float(observed) if isinstance(observed, (int, float)) else now,
            windows=tuple(windows),
            plan=(Observed(r["plan"], Provenance.PROVIDER_REPORTED)
                  if isinstance(r.get("plan"), str) and r["plan"] else None),
            notes=tuple(str(n) for n in r.get("notes") or ()),
            model_groups=tuple((str(k), str(v)) for k, v in groups.items()),
            local=dict(r["local"]) if isinstance(r.get("local"), dict) else None)

    def delivery_opportunities(self, runtime: str) -> list[DeliveryOpportunity]:
        return []

    # -- capacity, as selection reads it (lifted from Mark IV) ----------------

    def capacity_view(self, runtime: str, model: str | None = None,
                      holds=None, fresh: bool = False) -> dict:
        """What this runtime's OWN report, and any quota hold on it, say about
        taking work now (Mark IV `Foundation.capacity_view`).

        `state` is `exhausted`, `available` or `unknown`, and `why` says it
        with the figures. Never a fraction compared with another runtime's.

        EXHAUSTED means a live, provider-reported window at 100% used. Where
        windows belong to model groups (Antigravity), the group serving
        `model` decides; with no model placed, the runtime is exhausted only
        if every group is. An ACTIVE QUOTA HOLD (`holds[runtime]`, made from
        the record's own quota failures by `mentis.web.quota`, `until` still
        ahead) also makes it exhausted, with the hold's own why: a hold naming
        no model matches every model, and one naming a model matches a run of
        exactly that model (`_hold_on`).

        `expires_at`: for an AVAILABLE runtime, the reset instant of its
        budget window (the longest stated window: what is lost at reset);
        for an EXHAUSTED one, when the exhaustion is known to end (the
        exhausted windows' reset, the hold's `until`). None when not known.

        `fresh` reads MARS (single flight, bounded wait) -- only selection on
        dispatch's own thread does. Otherwise only an answer already held is
        used and MARS is never asked: the judge paths must not stall.
        """
        report, why_none = (self._capacity_answer(CAPACITY_WAIT_S, prefer_held=True) if fresh
                            else self._capacity_answer(cached_only=True))
        # ASKED OF MARS ONLY WHERE A HOLD IS THERE TO BE MATCHED.
        default = (routing.default_model_of(self._backend(runtime))
                   if not model and isinstance(holds, dict) and holds.get(runtime)
                   else None)
        return self._view(self._reading(runtime, report, why_none), model,
                          holds, time.time(), default)

    @staticmethod
    def _hold_on(runtime: str, model: str | None, holds, now: float,
                 default: str | None = None):
        """The quota hold that applies to this run, or None: the
        longest-standing of the runtime's scopes that match.

        A runtime-wide hold matches every model, and a model's hold matches a
        run of exactly that model. The run's model is what was asked, else the
        runtime's advertised default. WITH NEITHER, THE MODEL THAT WOULD RUN IS
        NOT KNOWN, so a model's hold matches conservatively: it may well be the
        one that just ran out."""
        h = (holds or {}).get(runtime) if isinstance(holds, dict) else None
        if not isinstance(h, dict):
            return None
        running = model or default
        scopes = h.get("scopes") if isinstance(h.get("scopes"), list) else [h]
        live = [s for s in scopes if isinstance(s, dict)
                and _number(s.get("until")) and s["until"] > now
                and (s.get("model") is None or running is None
                     or s["model"] == running)]
        return max(live, key=lambda s: s["until"]) if live else None

    @staticmethod
    def _cooldown(hold: dict) -> bool:
        """Whether a hold rests only on the cooldown, not a reported reset."""
        if isinstance(hold.get("cooldown"), bool):
            return hold["cooldown"]
        since = hold.get("since")
        return _number(since) and abs(hold["until"] - since - QUOTA_COOLDOWN_S) < 1

    def _view(self, reading: CapacityReading, model: str | None, holds,
              now: float, default: str | None = None) -> dict:
        kind = reading.runtime
        v = self._report_view(reading, model, now)
        hold = self._hold_on(kind, model, holds, now, default)
        v["cooldown"] = False
        if hold is None:
            return v
        why = str(hold.get("why") or f"{kind}: held after a quota failure")
        if hold.get("model"):
            why += f" (model {hold['model']})"
        why += f", held until {_span(hold['until'] - now)} from now"
        if v["state"] == "exhausted":
            ends = (None if v["expires_at"] is None
                    else max(v["expires_at"], hold["until"]))
            return {**v, "why": f"{v['why']}; {why}", "expires_at": ends,
                    "held": True}
        return {**v, "state": "exhausted", "why": why,
                "expires_at": hold["until"], "budget_left": None,
                "held": True, "cooldown": self._cooldown(hold)}

    def _report_view(self, reading: CapacityReading, model: str | None,
                     now: float) -> dict:
        """Mark IV's `capacity_view` over one reading, adapted: no machine,
        the no-report why from the reading's own note, and the exhausted
        state carrying when it ends."""
        kind = reading.runtime

        def out(state, why, expires_at=None, budget_left=None, figures=()):
            return {"state": state, "why": why, "expires_at": expires_at,
                    "budget_left": budget_left, "figures": list(figures)}

        if not reading.windows:
            note = reading.notes[0] if reading.notes else (
                f"{_NO_CAPACITY} for {kind}")
            return out("unknown", f"{kind}: capacity unknown ({note})")
        valid = [w for w in reading.windows
                 if w.provenance == Provenance.PROVIDER_REPORTED
                 and _number(w.used_fraction)
                 and 0 <= w.used_fraction <= 1
                 and (w.resets_at is None or
                      (_number(w.resets_at)
                       and (not w.window_seconds or
                            w.resets_at - w.window_seconds - RESET_WINDOW_SLOP_S
                            <= reading.observed_at < w.resets_at)))]
        windows = [w for w in valid if w.resets_at is None or w.resets_at > now]
        if not windows:
            return out("unknown", f"{kind}: capacity unknown (no verified "
                                  f"figures in the current reset period)")
        groups = sorted({w.group for w in reading.windows if w.group})
        if groups:
            placed = dict(reading.model_groups).get(model) if model else None
            if model and model in dict(reading.model_groups) and placed not in groups:
                return out("unknown", f"{kind}: model has no verified quota group")
            judged = [placed] if placed in groups else groups
        else:
            judged = [None]
        pools = {g: [w for w in windows if w.group == g] for g in judged}
        full = [g for g, ws in pools.items()
                if any(w.used_fraction >= 1.0 for w in ws)]
        figures = [_figure(w, now) for ws in pools.values() for w in ws]

        def freed(g):
            resets = [w.resets_at for w in pools[g] if w.used_fraction >= 1.0]
            return None if None in resets else max(resets)

        if (groups and full and len(full) == len(judged)) or (not groups and full):
            ends = [e for e in (freed(g) for g in full) if e is not None]
            what = (f"group {', '.join(full)}" if groups else ", ".join(
                w.label for w in windows if w.used_fraction >= 1.0))
            return out("exhausted",
                       f"{kind}: exhausted by its own report ({what} at 100%"
                       + (f", resets in {_span(min(ends) - now)}" if ends else "")
                       + ")", min(ends) if ends else None, None, figures)
        if not any(ws for g, ws in pools.items() if g not in full):
            return out("unknown", f"{kind}: no live figures for the applicable pool",
                       figures=figures)
        expiries, lefts = [], []
        for g, ws in pools.items():
            if g in full and groups:
                continue
            # An expired long window leaves the budget unknown; a still-live
            # short pacing window is not promoted to the budget window.
            sized = [w for w in reading.windows if w.group == g
                     and _number(w.window_seconds) and w.window_seconds > 0]
            longest = max(sized, key=lambda w: w.window_seconds) if sized else None
            live = longest in ws and longest.resets_at is not None
            expiries.append(longest.resets_at if live else None)
            lefts.append(1.0 - longest.used_fraction if live else None)
        expires_at = None if not expiries or None in expiries else max(expiries)
        budget_left = None if not lefts or None in lefts else min(lefts)
        if groups:
            why = (f"{kind}: available by its own report ("
                   + "; ".join(figures) + ")"
                   + (f" (group {', '.join(full)} exhausted, others not)"
                      if full else ""))
        else:
            why = (f"{kind}: available by its own report ("
                   + ", ".join(f"{w.label} {w.used_fraction:.0%}"
                               for w in windows) + ")")
        return out("available", why, expires_at, budget_left, figures)

    @staticmethod
    def _compact(v: dict) -> dict:
        """What `selection_inputs` keeps of a view: never the reading."""
        return {k: v.get(k) for k in ("state", "why", "expires_at", "budget_left")}

    def _by_capacity(self, open_: list[dict], backends: list[dict],
                     views: dict) -> tuple[dict, list[str], list[dict], bool, bool]:
        """Which of the eligible, unexhausted runtimes takes unbound work, and
        the account of why (Mark IV `Foundation._by_capacity`, owner ruling
        ent-809e30307e4c): by actual capacity and reset time, preferring
        capacity that would otherwise expire unused; no invented score;
        unknown stays unknown. In this order, nothing weighted or summed:

          1. AVAILABLE with a known budget reset and budget left: the most
             of its budget that would go unused per hour left to its reset.
          2. UNKNOWN -- no figures, or no reset for its budget window. Kept
             and said; never treated as full or as empty.
        Within a tier, equal (or no) figures fall back to the runtime
        selected least recently by this process, then MARS's catalogue
        order -- the old rule, kept as the last tie-break.

        ONE GUARD AGAINST BEING PASSED OVER FOR GOOD (#1167). A known runtime
        with `GUARD_SUBSTANTIAL` of its budget left is overdue once it has
        missed max(2, known candidates here) automatic choices it was a known
        candidate for. An overdue runtime goes first: the most missed, then
        selected longest ago here, most budget left, the pace above, catalogue.
        Being chosen automatically clears its count; only a choice made here
        changes any count, so named, continuity and narrowed-away traffic age
        nothing. `ranking` is the order applied, guard picks first;
        `normal_order` is where the pace alone would have put each.

        Returns the chosen backend, the account, the ranking, whether the
        last tie-break decided it, and whether the guard did.
        """
        order = {b["id"]: n for n, b in enumerate(backends)}
        with self._lock:
            last_selected = dict(self._last_selected)
            missed = dict(self._guard_missed)
        now = time.time()
        rows = []
        for b in open_:
            v = views[b["id"]]
            known = (v["state"] == "available" and _number(v["expires_at"])
                     and _number(v.get("budget_left")))
            pace = None
            if known:
                hours = max((v["expires_at"] - now) / 3600.0, 1.0 / 60)
                pace = v["budget_left"] / hours
            rows.append((0 if known else 1, -pace if known else 0.0,
                         last_selected.get(b["id"], -1), order[b["id"]],
                         b, v, pace))
        rows.sort(key=lambda r: r[:4])
        normal_order = {r[4]["id"]: n for n, r in enumerate(rows)}
        leader = rows[0][4]["id"]
        known_rows = [r for r in rows if r[0] == 0]
        overdue_at = max(2, len(known_rows))

        def missed_by(r):
            return missed.get(r[4]["id"], 0)

        def substantial(r):
            return r[0] == 0 and r[5]["budget_left"] >= GUARD_SUBSTANTIAL

        overdue = sorted(
            (r for r in known_rows
             if substantial(r) and missed_by(r) >= overdue_at),
            key=lambda r: (-missed_by(r), r[2], -r[5]["budget_left"], r[1], r[3]))
        late = {r[4]["id"] for r in overdue}
        rows = overdue + [r for r in rows if r[4]["id"] not in late]
        names = {0: "available", 1: "capacity or budget reset unknown"}
        account = []
        for r in rows:
            tier, b, v, pace = r[0], r[4], r[5], r[6]
            line = f"{b['id']}: {names[tier]}"
            if v["figures"]:
                line += " (" + "; ".join(v["figures"]) + ")"
            if tier == 0:
                # The exact share beside the rounded one: 49.6% reads as 50%.
                line += (f"; {v['budget_left']:.0%} of its budget window "
                         f"unused with {_span(v['expires_at'] - now)} to its "
                         f"reset: {pace * 100:.2f}% of it per hour would go "
                         f"unused; {v['budget_left']:.6g} left is "
                         f"{'' if substantial(r) else 'not '}substantial "
                         f"(>= {GUARD_SUBSTANTIAL}), {missed_by(r)} automatic "
                         f"choices missed, overdue at {overdue_at}")
            account.append(line)
        guarded = bool(overdue)
        first = rows[0]
        tier, neg, chosen = first[0], first[1], first[4]
        if guarded:
            even = [r for r in overdue[1:] if missed_by(r) == missed_by(first)]
            tied = [r[4]["id"] for r in even]
            lru_decided = any(r[2] != first[2] for r in even)
            reason = (f"anti-starvation guard: {first[5]['budget_left']:.6g} of "
                      f"its budget left is substantial (>= {GUARD_SUBSTANTIAL}) "
                      f"and it missed {missed_by(first)} automatic choices it "
                      f"was a known candidate for (overdue at {overdue_at}); "
                      f"by pace alone it would have been {leader}")
            if tied:
                reason += (f"; tied with {tied} on those, so by the older last "
                           f"selection here, more budget left, pace, then "
                           f"MARS's catalogue order")
        else:
            tied = [r[4]["id"] for r in rows[1:] if r[0] == tier and r[1] == neg]
            lru_decided = bool(tied)
            reason = {0: ("the largest share of its budget would otherwise expire "
                          "unused per hour left to its reset (owner, 2026-10-26: "
                          "time left and amount left, together)"),
                      1: "no eligible runtime has a verified live budget reset"}[tier]
            if tied:
                reason += (f"; tied with {tied} on that, so of those it is the "
                           f"least recently selected here, then by MARS's "
                           f"catalogue order")
        ranking = [{"runtime": r[4]["id"], "tier": r[0],
                    "expires_at": r[5]["expires_at"],
                    "budget_left": r[5].get("budget_left"),
                    "unused_per_hour": r[6],
                    "last_selected": r[2], "catalogue_order": r[3],
                    "normal_order": normal_order[r[4]["id"]],
                    "substantial": substantial(r),
                    "missed_opportunities": missed_by(r),
                    "overdue_at": overdue_at,
                    # Below zero: how many more misses until it is overdue.
                    "overdue_distance": missed_by(r) - overdue_at,
                    "overdue": r[4]["id"] in late,
                    "guard_selected": guarded and r is first} for r in rows]
        with self._lock:
            for r in known_rows:
                self._guard_missed[r[4]["id"]] = (
                    self._guard_missed.get(r[4]["id"], 0) + 1)
            self._guard_missed[chosen["id"]] = 0
        return chosen, [
            "capacity ranking, each by its own report, no score; expected "
            "task consumption unknown, only exhaustion is judged: "
            + " | ".join(account),
            f"runtime {chosen['id']} chosen: {reason}"], ranking, lru_decided, guarded

    # -- selection ----------------------------------------------------------

    def _models_of(self, b: dict) -> set[str]:
        return {str(m.get("id") if isinstance(m, dict) else m)
                for m in b.get("models") or () if m}

    #: THE CAPABILITIES WORK MAY BE TRIED WITHOUT, when nobody has established
    #: them either way (#1268). Trying is harmless and visible for these: a run
    #: that cannot build the UI or drive a browser fails the attempt and says
    #: so (`record_verdict` `lacks`). For every other capability an unknown
    #: still excludes, as it always has: work kept on local compute
    #: (`reach_local_models`) must not reach a hosted runtime because nothing
    #: said otherwise. Widening this is the owner's decision.
    TRIABLE = frozenset({Capability.BUILD_UI.value, Capability.DRIVE_BROWSER.value})

    #: THE RUNTIMES THAT RUN ONLY WHEN NAMED (#1167: Antigravity is used in
    #: gemini's place). Never a candidate for automatic selection, continuity
    #: included; naming one runs it as any other.
    NAMED_ONLY = frozenset({"gemini"})

    def runtime_contract(self, runtime: str, holds=None) -> dict:
        """The runtime capability contract MARS declares for `runtime`
        (`mentis.core.runtime_contract`), with what Mentis knows of its quota
        laid over it: a capacity view that is exhausted -- the runtime's own
        report at 100%, or a quota hold from the record (`holds`, as
        `quota.quota_holds` gives them) -- makes it temporarily unavailable.
        Only capacity already held is read: this never waits on MARS.

        THE STATES DECIDE, NOT THE NAME. New code asks this, never which
        runtime it is (program §12)."""
        from mentis.core import runtime_contract as RC
        contract = RC.of_backend(self._backend(runtime))
        try:
            view = self.capacity_view(runtime, holds=holds)
        except Exception:                                 # noqa: BLE001
            view = {}
        if view.get("state") == "exhausted":
            return RC.with_quota(contract,
                                 held=view.get("why") if view.get("held") else None,
                                 exhausted=view.get("why") or "exhausted by its own report")
        return contract

    def _blocks(self, name: str, verdict: str) -> bool:
        """Whether this verdict keeps work requiring `name` off a runtime."""
        return verdict == "unsupported" or (verdict == "unknown"
                                            and name not in self.TRIABLE)

    def eligibility(self, runtime: str, requires, model: str | None = None) -> dict:
        """Can this backend meet each named requirement -- and is that KNOWN.

        THREE ANSWERS, NEVER TWO. SUPPORTED when MARS's catalogue says so
        (`call_mentis_tools`: the backend takes stdio MCP servers; anything
        else: named in the `capabilities` it reports). UNSUPPORTED when MARS
        reports the backend LACKS it (`lacks`, with its evidence; or, for
        `call_mentis_tools`, an MCP list without stdio). UNKNOWN otherwise:
        nothing measured either way. Unknown is not inability -- treating it
        as one refused every browser review because no runtime had declared
        anything (#1268) -- and it is not ability either: for the capabilities
        work may be tried without (`TRIABLE`) selection prefers what is
        confirmed and says when it chose without it; for the rest an unknown
        still excludes.
        """
        b = self._backend(runtime) or {}
        declared = {str(c) for c in b.get("capabilities") or ()}
        raw_lacks = b.get("lacks") or {}
        lacks = ({str(k): str(v or "") for k, v in raw_lacks.items()}
                 if isinstance(raw_lacks, dict)
                 else {str(k): "" for k in raw_lacks})
        mcp = (b.get("supports") or {}).get("mcp")
        if "stdio" in (mcp or ()):
            declared.add(Capability.CALL_MENTIS_TOOLS.value)
        elif isinstance(mcp, list):
            lacks.setdefault(Capability.CALL_MENTIS_TOOLS.value,
                             f"MARS lists {runtime}'s MCP transports as {mcp}, "
                             f"without stdio")
        known = {c.value for c in Capability}
        out = {}
        for name in requires or ():
            if name in declared:
                out[name] = {"verdict": "supported", "scope": runtime,
                             "evidence": f"MARS lists {runtime} with {name}"}
            elif name in lacks:
                out[name] = {"verdict": "unsupported", "scope": runtime,
                             "evidence": (f"MARS reports {runtime} lacks {name}"
                                          + (f": {lacks[name]}" if lacks[name]
                                             else ""))}
            elif name not in known:
                # NOTHING CAN HAVE A NAME NO RUNTIME CAN DECLARE: known not to
                # be met, everywhere -- not unknown.
                out[name] = {"verdict": "unsupported", "scope": runtime,
                             "evidence": (f"{name!r} is not a capability any "
                                          f"runtime can declare, so nothing "
                                          f"here can judge it")}
            else:
                out[name] = {"verdict": "unknown", "scope": runtime,
                             "evidence": (f"MARS does not say whether {runtime} "
                                          f"has {name}")}
        return out

    def eligible(self, runtime: str, requires, model: str | None = None) -> bool:
        """Whether nothing it requires keeps the work off this runtime: none
        is known missing, and any unknown is one work may be tried without
        (`TRIABLE`). What is confirmed is preferred where a choice is made
        (`execution_select`)."""
        return not any(self._blocks(n, r["verdict"]) for n, r in
                       self.eligibility(runtime, requires, model).items())

    def execution_select(
        self,
        *,
        difficulty: str = "ordinary",
        runtime: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        requires=(),
        avoid: str | None = None,
        considered=(),
        prefer: str | None = None,
        holds=None,
        tier: str | None = None,
        tier_sources=(),
    ) -> Selection:
        """Resolve a runtime/model/effort, and say what informed the choice.

        Runtimes are MARS backends; one is usable when MARS reports it
        available. `requires` NARROWS who is eligible and nothing else. An
        explicit runtime or model is a constraint: refused, never substituted.

        CAPACITY (Mark IV `Foundation.select`, owner approval 2026-10-29).
        Automatic selection reads each eligible runtime's capacity view --
        its own reported windows, and `holds`, the quota holds the record's
        failures put on it -- and, right after the requirement and model
        filters and BEFORE review avoidance, drops the `NAMED_ONLY` ones (if
        that leaves none, it refuses, saying so) and then the exhausted ones.
        If that leaves none, it refuses, naming the soonest expiry. Then review
        avoidance, then continuity (`prefer`), then `_by_capacity`, whose
        last tie-break is the runtime selected least recently here, then
        MARS's catalogue order. A NAMED runtime is never substituted: its
        exhaustion is said in `because` and `inputs["disclosed"]`.

        It never waits on MARS once any capacity answer is held (WS-P): it
        decides on the newest held one, and a newer one is read in the
        background. Only a process's first selection, with nothing held,
        waits for the read, at most `CAPACITY_WAIT_S`.

        `prefer` is CONTINUITY, not a constraint: the runtime of a handle this
        Participant already holds for this binding. Among the eligible it wins
        before the rotation, so a Participant's next request in a Conversation
        stays where its last one ran instead of being rotated onto a runtime
        nothing here has tried (2026-10-27: the Caretaker's search went from
        Codex to Gemini that way, and Gemini's web search hung for 900 s). It
        is ignored when that runtime is not eligible, not available, or is the
        one a review must avoid.

        `tier` IS WHAT THE WORK NEEDS (`mentis.core.routing`), and it fills only
        what nobody named. Among runtimes that advertise tuples:

          * nothing fixed: the least sufficient tuple that survives the gates
            above. None surviving is refused, naming what was considered; it
            is never lowered. No tuple anywhere is the legacy path, recorded
            as `tier_unfulfilled` = `no_catalogue_metadata`.
          * a fixed runtime, model or effort: the tier fills the rest inside
            it. Where it cannot, the fixed fields run with the remainder left
            to the runtime, recorded as `tier_unfulfilled` = `fixed_binding`.
            A fixed field is never replaced.

        Holds are judged per tuple, so a held model yields to its sibling. A
        named model all of whose offering runtimes are held or exhausted still
        runs on the best of them, disclosed. A named effort alone places
        nothing: selection is as it was, and the effort is passed exactly.
        Review independence is a preference among what is adequate, and its
        loss is disclosed. All of it is said in `inputs["routing"]`.

        THE DEFAULT TIER IS SOFT (`"default"` in `tier_sources`): where no
        adequate tuple survives it is not refused but falls through to the
        legacy path, recorded as `tier_unfulfilled` = `no_adequate_tuple`.

        A MODEL AND EFFORT THAT CONFLICT ARE NEVER SENT (`routing.effort_conflicts`):
        such a runtime is dropped before anything judges it, and refused when it
        was named or nothing else is left. Neither field is ever changed to fit.
        """
        # WHERE SELECTION'S OWN TIME GOES (WS-P), in ms: the catalogue, the
        # capacity answer, and the whole decision.
        t0 = time.perf_counter()
        backends = self._backends()
        spent = {"backends_ms": round((time.perf_counter() - t0) * 1000, 1)}
        inputs = {"difficulty": difficulty, "runtime": runtime, "model": model,
                  "effort": effort, "requires": list(requires or ()),
                  "avoid": avoid, "considered": list(considered or ()),
                  "prefer": prefer,
                  "evaluated_at": time.time(),
                  "backends": [{k: b.get(k) for k in ("id", "available", "reason")}
                               for b in backends],
                  "last_selected": dict(self._last_selected)}
        because: list[str] = list(considered or ())
        dims: list[str] = []
        route = {"required_tier": tier,
                 "target_effort": routing.TARGET_EFFORT.get(tier),
                 "tier_sources": list(tier_sources or ()),
                 "tier_unfulfilled": None, "tier_unfulfilled_because": None,
                 "selected_tier": None, "considered": []}
        filled_model = filled_effort = None
        present = [b for b in backends if b.get("available")]
        if not present:
            raise RuntimeNotPresent(
                "MARS reports no available runtime"
                + ("" if backends else " (MARS could not be reached, or "
                   "lists no backends)"))
        requires = tuple(requires or ())
        if requires:
            judged = {b["id"]: self.eligibility(b["id"], requires) for b in present}
            inputs["eligibility"] = judged
            # WHAT KEEPS THE WORK OFF A RUNTIME: a requirement it is known to
            # lack (with MARS's evidence), or one nobody has established that
            # work may not be tried without (`TRIABLE`).
            blocked = {k: [n for n, r in rs.items() if self._blocks(n, r["verdict"])]
                       for k, rs in judged.items()}
            possible = [b for b in present if not blocked[b["id"]]]
            if not possible:
                raise Unsupported(
                    ", ".join(b["id"] for b in present), "execution_select",
                    "no available runtime can be given this work: "
                    + "; ".join(f"{k}: " + "; ".join(
                        rs[n]["evidence"] for n in sorted(blocked[k]))
                        for k, rs in sorted(judged.items())))
            # Which of them are CONFIRMED for every requirement, kept for the
            # choice below: preferred only among runtimes that still have
            # capacity and, for a review, are not the author's (found by
            # independent review: preferring them first refused browser work
            # whenever the one confirmed runtime was out of quota, and turned
            # reviews into self-reviews).
            confirmed_ids = {b["id"] for b in possible
                             if all(r["verdict"] == "supported"
                                    for r in judged[b["id"]].values())}
            unconfirmed = {b["id"]: sorted(n for n, r in judged[b["id"]].items()
                                           if r["verdict"] == "unknown")
                           for b in possible if b["id"] not in confirmed_ids}
            out_blocked = {k: v for k, v in blocked.items() if v}
            if out_blocked:
                because.append("cannot be given this work: "
                               + "; ".join(f"{k} ({', '.join(v)})"
                                           for k, v in sorted(out_blocked.items())))
            present = possible
            dims.append("required_capabilities")
        # TUPLES ANYWHERE THIS WORK COULD GO, asked before a named model narrows
        # the field: whether a fixed binding can be filled is a different
        # question from whether automatic routing has anything to read.
        active = bool(tier) and any(
            routing.tuples_of(b) for b in present
            if b["id"] not in self.NAMED_ONLY)
        if tier and not active:
            route["tier_unfulfilled"] = "no_catalogue_metadata"
            route["tier_unfulfilled_because"] = (
                "no capability-eligible runtime advertises a routing tuple, so "
                "the runtime's own defaults are used")
            because.append(f"tier {tier} not applied: "
                           + route["tier_unfulfilled_because"])
            dims.append("tier_no_metadata")
        if model and not runtime:
            offered = [b for b in present if model in self._models_of(b)]
            if not offered:
                raise Unsupported(
                    ", ".join(b["id"] for b in present), "execution_select",
                    f"model {model!r} was requested explicitly and no eligible "
                    f"runtime's catalogue offers it; refusing rather than "
                    f"running a different model")
            because.append(f"model {model!r} is offered by "
                           f"{[b['id'] for b in offered]}")
            dims.append("requested_model_placement")
            present = offered
        excluded: tuple[str, ...] = ()
        # ONE CAPACITY ANSWER FOR THE WHOLE DECISION, refreshed here only.
        t1 = time.perf_counter()
        report, why_none = self._capacity_answer(CAPACITY_WAIT_S, prefer_held=True)
        spent["capacity_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        inputs["timing"] = spent
        now = time.time()
        # HOW OLD WHAT SELECTION DECIDED ON WAS: MARS's own `ageSeconds` per
        # runtime (None: pending or not said) and how long Mentis has held it.
        with self._lock:
            held_at = self._capacity[0] if self._capacity else None
        inputs["capacity_age"] = {
            "held_s": (round(time.monotonic() - held_at, 1)
                       if held_at is not None else None),
            "mars_age_s": {k: v.get("ageSeconds") for k, v in report.items()
                           if isinstance(v, dict)},
            "pending": sorted(k for k, v in report.items()
                              if isinstance(v, dict) and v.get("pending") is True)}
        inputs["holds"] = {k: dict(v) for k, v in (holds or {}).items()
                           if isinstance(v, dict)}
        if runtime:
            chosen = next((b for b in present if b["id"] == runtime), None)
            if chosen is None:
                known = self._backend(runtime)
                if known is not None and known.get("available"):
                    raise Unsupported(
                        runtime, "execution_select",
                        "it is available but cannot be given this work: "
                        + ", ".join(f"{n} ({r['evidence']})"
                                    for n, r in sorted(self.eligibility(
                                        runtime, requires).items())
                                    if self._blocks(n, r["verdict"])))
                raise RuntimeNotPresent(
                    f"{runtime} is not available: "
                    + ((known or {}).get("reason") or
                       ("MARS lists it unavailable" if known else
                        "MARS does not list it")))
            because.append(f"runtime {runtime} was requested explicitly")
            if routing.effort_conflicts(chosen, model, effort):
                raise Unsupported(
                    runtime, "execution_select",
                    _conflict_words(runtime, model, effort)
                    + "; refused, and nothing was substituted")
            if requires:
                unsure = sorted(n for n, r in self.eligibility(
                    runtime, requires).items() if r["verdict"] == "unknown")
                if unsure:
                    said = (f"{runtime} was named; whether it has {unsure} is "
                            f"NOT established (MARS reports neither)")
                    because.append(said)
                    inputs["unconfirmed"] = {runtime: unsure}
                    inputs.setdefault("disclosed", []).append(said)
                    dims.append("unconfirmed_capabilities")
            if active:
                got, rows = self._tuple_on(chosen, tier, model, effort, report,
                                           why_none, holds, now)
                route["considered"] = rows
                if got:
                    filled_model = None if model else got["model"]
                    filled_effort = None if effort else got["effort"]
                    route["selected_tier"] = got["tier"]
                    because.append(
                        f"tier {tier} filled inside {runtime}: "
                        f"{got['model']} ({got['tier']}) at {got['effort']}")
                    dims.append("tier_within_binding")
                self._unfulfilled_within(route, got, tier, effort, because,
                                         f"runtime {runtime}")
            # SAID, NEVER ACTED ON: a named runtime is not substituted.
            view = self._view(self._reading(runtime, report, why_none),
                              model or filled_model, holds, now,
                              routing.default_model_of(chosen))
            inputs["capacity"] = {runtime: self._compact(view)}
            if view["state"] == "exhausted":
                said = f"{view['why']}; run as named, not substituted"
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
                dims.append("capacity_disclosed")
        else:
            # NAMED ONLY, BEFORE THE GATE: what is left is what the gate, a
            # review and continuity then judge, so none of them can land here.
            named_only = [b["id"] for b in present if b["id"] in self.NAMED_ONLY]
            if named_only:
                present = [b for b in present if b["id"] not in self.NAMED_ONLY]
                if not present:
                    raise RuntimeNotPresent(
                        f"of the available runtimes only {named_only} could "
                        f"take this work, and automatic selection does not use "
                        f"{named_only}: it runs only when named")
                because.append(f"{named_only} not considered: it runs only "
                               f"when named")
                inputs["named_only"] = named_only
                dims.append("named_only")
            # A CONFLICT DIES AT LAUNCH, SO IT IS NOT A CANDIDATE: dropped before
            # the gate, a review or continuity can land on it.
            clashing = [b["id"] for b in present
                        if routing.effort_conflicts(b, model, effort)]
            if clashing:
                said = _conflict_words(", ".join(clashing), model, effort)
                present = [b for b in present if b["id"] not in clashing]
                if not present:
                    raise Unsupported(
                        ", ".join(clashing), "execution_select",
                        said + "; nothing else can take this work, so it is "
                               "refused, and nothing was substituted")
                said += "; not considered"
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
                dims.append("effort_conflict")
            # THE TUPLE EACH RUNTIME WOULD RUN, BEFORE ANYTHING IS JUDGED ON IT:
            # a held model yields to its sibling, so holds are asked per tuple.
            routes: dict = {}
            if active:
                for b in present:
                    got, rows = self._tuple_on(b, tier, model, effort, report,
                                               why_none, holds, now)
                    route["considered"].extend(rows)
                    if got:
                        routes[b["id"]] = got
                if routes:
                    present = [b for b in present if b["id"] in routes]
                    dims.append("tier_tuples")
                elif model or effort:
                    self._unfulfilled_within(
                        route, None, tier, effort, because,
                        "the named " + ("model" if model else "effort"))
                elif "default" in route["tier_sources"]:
                    # NOBODY ASKED FOR THIS TIER, so missing it refuses nothing:
                    # the work still goes wherever it could go without one.
                    why = (f"no adequate model and effort for the default tier "
                           f"{tier} survives: "
                           + _considered_words(route["considered"], present)
                           + "; the runtime's own defaults are used")
                    route["tier_unfulfilled"] = "no_adequate_tuple"
                    route["tier_unfulfilled_because"] = why
                    because.append(why)
                    dims.append("tier_default_yielded")
                else:
                    raise Unsupported(
                        ", ".join(b["id"] for b in present), "execution_select",
                        f"no adequate model and effort for tier {tier} "
                        f"(at least {routing.TARGET_EFFORT[tier]}) survives: "
                        + _considered_words(route["considered"], present)
                        + "; the tier is not lowered, and a coordinator may "
                          "authorize a new execution")
            # EXHAUSTION FIRST, BEFORE REVIEW AVOIDANCE (Mark IV's order): a
            # review whose only unexhausted runtime is the author's runs
            # there, saying independence was not achievable.
            views = {b["id"]: self._view(self._reading(b["id"], report,
                                                       why_none),
                                         routes[b["id"]]["model"]
                                         if b["id"] in routes else model,
                                         holds, now,
                                         routing.default_model_of(b))
                     for b in present}
            inputs["capacity"] = {k: self._compact(v) for k, v in views.items()}
            because.append("capacity, each by its own report and the quota "
                           "holds: " + "; ".join(v["why"] for v in views.values()))
            dims.append("capacity_gate")
            open_ = [b for b in present if views[b["id"]]["state"] != "exhausted"]
            out = [b["id"] for b in present if views[b["id"]]["state"] == "exhausted"]
            if not open_ and not model:
                raise RuntimeNotPresent(_all_exhausted(views, now))
            if not open_:
                # A NAMED MODEL IS NOT SUBSTITUTED AND NOT REFUSED FOR CAPACITY:
                # every runtime offering it is held or exhausted, so the best
                # of them runs it, and that is said.
                said = (f"model {model!r} was named and every runtime offering "
                        f"it is held or exhausted: "
                        + "; ".join(v["why"] for v in views.values())
                        + "; run as named, not substituted")
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
                dims.append("capacity_disclosed")
                open_, out = list(present), []
            if out:
                because.append(f"excluded as exhausted: {out}")
            if avoid:
                others = [b for b in open_ if b["id"] != avoid]
                if others:
                    because.append(
                        f"review: the reviewed work ran on {avoid}; it is "
                        f"avoided so the review runs on a different runtime")
                    out = out + [avoid]
                    open_ = others
                else:
                    because.append(
                        f"review: the reviewed work ran on {avoid} and no "
                        f"other runtime is available and unexhausted"
                        + (f" ({named_only} run only when named)"
                           if named_only else "")
                        + "; independence by runtime was not achievable")
                    inputs.setdefault("disclosed", []).append(
                        f"this review runs on {avoid}, the runtime the reviewed "
                        f"work ran on: nothing else could take it, so it is not "
                        f"independent by runtime")
                dims.append("review_independence")
            excluded = tuple(dict.fromkeys(named_only + out))
            # CONFIRMED BEFORE UNCONFIRMED, among what is left: a runtime known
            # to have every requirement is preferred to one nobody has
            # established it for; with none left, the work goes where it is not
            # known to fail and the record says so.
            if requires:
                sure = [b for b in open_ if b["id"] in confirmed_ids]
                if sure:
                    if len(sure) < len(open_):
                        because.append(
                            f"required {list(requires)}: confirmed on "
                            f"{[b['id'] for b in sure]}, preferred over "
                            f"{sorted(b['id'] for b in open_ if b not in sure)}, "
                            f"where it is not established")
                    open_ = sure
                else:
                    left = {b["id"]: unconfirmed.get(b["id"], []) for b in open_}
                    said = (f"no runtime left to choose from is known to have "
                            f"{list(requires)}; chosen among {sorted(left)}, so "
                            f"whether the chosen one can do it is NOT established")
                    because.append(said)
                    inputs["unconfirmed"] = left
                    inputs.setdefault("disclosed", []).append(said)
                    dims.append("unconfirmed_capabilities")
            # THE LEAST SUFFICIENT, AFTER EVERY GATE AND PREFERENCE ABOVE: an
            # efficient model for work it can do, not always the strongest.
            if routes:
                least = min(routing.rank_of(routes[b["id"]]) for b in open_)
                because.append(
                    f"tier {tier}: least sufficient of "
                    + ", ".join(f"{b['id']} {routes[b['id']]['model']} at "
                                f"{routes[b['id']]['effort']}" for b in open_))
                open_ = [b for b in open_
                         if routing.rank_of(routes[b["id"]]) == least]
            inputs["candidates"] = [b["id"] for b in open_]
            continuing = next((b for b in open_ if b["id"] == prefer), None)
            if continuing is not None:
                chosen = continuing
                because.append(f"continuing on {chosen['id']}: the runtime this "
                               f"participant's handle here already runs on")
                dims.append("continuity")
            else:
                if prefer in named_only:
                    because.append(f"the handle here runs on {prefer}, which "
                                   f"runs only when named; not continued")
                elif prefer:
                    because.append(f"the handle here runs on {prefer}, which "
                                   f"cannot take this work now; not continued")
                chosen, account, ranking, tied, guarded = self._by_capacity(
                    open_, backends, views)
                inputs["ranking"] = ranking
                because.extend(account)
                dims.append("anti_starvation_guard" if guarded
                            else "capacity_expiry")
                if tied:
                    dims.append("least_recently_selected")
            if routes:
                got = routes[chosen["id"]]
                filled_model = None if model else got["model"]
                filled_effort = None if effort else got["effort"]
                route["selected_tier"] = got["tier"]
                self._unfulfilled_within(route, got, tier, effort, because,
                                         "the named effort")
        inputs["eligible"] = [b["id"] for b in present]
        inputs["excluded"] = list(excluded)
        dims.append("runtime_presence")
        with self._lock:
            self._selections += 1
            self._last_selected[chosen["id"]] = self._selections
        req_effort = effort or filled_effort
        running = model or filled_model
        if effort:
            because.append(f"effort {effort!r} was requested explicitly")
            dims.append("requested_effort")
            support = _effort_support(chosen, running, effort)
            inputs["effort_support"] = support
            if support != "supported":
                said = (f"effort {effort!r} is {support} on {chosen['id']}"
                        + (f" for {running}" if running else "")
                        + "; passed exactly as named")
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
        elif filled_effort:
            because.append(f"effort {filled_effort!r} from tier {tier}")
            dims.append("tier_effort")
        else:
            # DIFFICULTY DOES NOT SET EFFORT unless that is turned on. MARS now
            # lists ACP agents' efforts, so this Mark IV rule would start
            # running ordinary work at `medium` instead of each runtime's own
            # default -- a change the owner has not decided (2026-10-27).
            word = {"trivial": "low", "ordinary": "medium",
                    "hard": "high"}.get(difficulty, "medium")
            if (_EFFORT_FROM_DIFFICULTY
                    and word in {str(e) for e in chosen.get("efforts") or ()}
                    and not routing.effort_conflicts(chosen, running, word)):
                req_effort = word
                because.append(f"effort {word!r} from difficulty {difficulty!r}"
                               f" using {chosen['id']}'s own effort vocabulary")
                dims.append("difficulty")
        if model:
            because.append(f"model {model!r} was requested explicitly")
            dims.append("requested_model")
            if runtime and model not in self._models_of(chosen):
                said = (f"model {model!r} is not in {runtime}'s catalogue; run "
                        f"exactly as named")
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
        elif filled_model:
            because.append(f"model {filled_model!r} from tier {tier}")
            dims.append("tier_model")
        else:
            because.append("no model chosen: the runtime's own default is used")
        # WHAT WILL RUN, AS FAR AS IS KNOWN BEFORE IT DOES: read back by the
        # quota holds and by handle reuse.
        inputs["effective_model"] = running or routing.default_model_of(chosen)
        inputs["routing"] = route
        spent["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return Selection(runtime=chosen["id"], model=running,
                         requested_effort=req_effort, because=tuple(because),
                         dimensions_used=tuple(dims), excluded=excluded,
                         inputs=inputs)

    @staticmethod
    def _unfulfilled_within(route, got, tier, effort, because, fixed) -> None:
        """Say that a fixed binding could not meet the tier; it runs anyway.
        Either no tuple fits inside it, or the named effort is below the target."""
        if got and not (effort and routing.effort_short(effort, tier)):
            return
        why = (f"{fixed} has no adequate model and effort for tier {tier}, so "
               f"it runs with the rest left to the runtime" if not got else
               f"the named effort {effort!r} is below tier {tier}'s target "
               f"{routing.TARGET_EFFORT[tier]}, and it is kept as named")
        route["tier_unfulfilled"] = "fixed_binding"
        route["tier_unfulfilled_because"] = why
        because.append(why)

    def _tuple_on(self, b, tier, model, effort, report, why_none, holds,
                  now) -> tuple:
        """The tuple this backend would run for `tier`, or None, and every one
        considered with what capacity said of it. A model nobody named is passed
        over when it is held or exhausted; a named one is judged later."""
        got, rows = None, []
        for row in routing.adequate(b, tier, model, effort):
            view = self._view(self._reading(b["id"], report, why_none),
                              row["model"], holds, now)
            rows.append({"runtime": b["id"], **row, "capacity": view["state"],
                         "why": view["why"]})
            if got is None and (model or view["state"] != "exhausted"):
                got = row
        return got, rows

    def _tier_declines(self, runtime, tier, requires, model, holds) -> str | None:
        """Why a preferred runtime has no usable tuple for this tier, or None:
        always None when no runtime advertises any, since then nothing is
        routed by tier at all. Capacity here is only what is already held."""
        backends = [b for b in self._backends() if b.get("available")
                    and b["id"] not in self.NAMED_ONLY
                    and self.eligible(b["id"], requires, model)]
        if not any(routing.tuples_of(b) for b in backends):
            return None
        rows = routing.adequate(self._backend(runtime), tier, model)
        if any(self.capacity_view(runtime, r["model"], holds)["state"]
               != "exhausted" for r in rows):
            return None
        return (f"{runtime} has no available model and effort adequate for "
                f"tier {tier}")

    def execution_usable(self, runtime: str, requires=(),
                         model: str | None = None, holds=None,
                         tier: str | None = None) -> str | None:
        """None when `runtime` could take this work now, else why not:
        unlisted, unavailable, ineligible, exhausted by its own report or
        a quota hold (Mark IV `Foundation.usable`), or, given a `tier`, with no
        tuple adequate for it where tuples are advertised. What a PREFERENCE -- a
        Participant's declared default -- is judged by before it binds.
        Capacity here is only what is already held: this never asks MARS."""
        b = self._backend(runtime)
        if b is None:
            return f"{runtime} is not a runtime MARS lists"
        if not b.get("available"):
            return f"{runtime} is not available: {b.get('reason') or 'MARS gave no reason'}"
        requires = tuple(requires or ())
        if requires and not self.eligible(runtime, requires, model):
            unmet = [n for n, r in self.eligibility(runtime, requires, model).items()
                     if self._blocks(n, r["verdict"])]
            return f"{runtime} cannot be given work requiring {unmet}"
        # A PREFERENCE DOES NOT OUTRANK WHAT IS CONFIRMED: a default nobody has
        # established can do this work yields to an available runtime that is
        # confirmed for all of it, as automatic selection prefers it. With
        # nothing confirmed anywhere, the default binds.
        if requires:
            unsure = sorted(n for n, r in self.eligibility(
                runtime, requires, model).items() if r["verdict"] == "unknown")
            if unsure:
                # ...and that could take it now: one out of quota is no
                # alternative (found by independent review), and neither is one
                # automatic selection would not choose.
                sure = [x["id"] for x in self._backends()
                        if x["id"] != runtime and x.get("available")
                        and x["id"] not in self.NAMED_ONLY
                        and all(r["verdict"] == "supported" for r in
                                self.eligibility(x["id"], requires, model).values())
                        and self.capacity_view(x["id"], model, holds)["state"]
                        != "exhausted"]
                if sure:
                    return (f"whether {runtime} has {unsure} is not established, "
                            f"and {sure} are confirmed for it")
        view = self.capacity_view(runtime, model, holds)
        if view["state"] == "exhausted":
            return view["why"]
        # A PREFERENCE MUST ALSO BE ABLE TO DO THE WORK AT THE TIER IT NEEDS.
        return self._tier_declines(runtime, tier, requires, model, holds) if tier else None

    def execution_eligibility(self, runtime: str, requires,
                              model: str | None = None) -> dict:
        return self.eligibility(runtime, requires, model)

    def provider_of(self, runtime: str, model: str | None) -> str | None:
        """Who serves this model under that harness, as the catalogue says (never
        guessed from the slug here): `None` where the model is unknown, or the
        catalogue has no provider for it -- which is also what a runtime that only
        ever serves its own models looks like, correctly."""
        if not model:
            return None
        try:
            models = self.models_list(runtime)
        except (RuntimeNotPresent, Unsupported):
            return None
        return next((m.provider for m in models if m.slug == model), None)

    # -- agents -------------------------------------------------------------

    def _notes(self) -> list:
        """The continuity notes for the call running on this thread."""
        if not hasattr(self._thread, "notes"):
            self._thread.notes = []
        return self._thread.notes

    def summon_notes_here(self) -> list[str]:
        """What the summon on THIS thread decided, and why."""
        return list(self._notes())

    def known(self, instance_id: str) -> Instance | None:
        """The instance this process holds under that id, if any."""
        return self._live.get(instance_id)

    def agents_resolve(self, address: Address, *,
                       participant: str | None = None) -> dict:
        """What summoning this address would do, without doing it: the
        instances this process holds whose binding matches.

        WHEN THE CALLER KNOWS WHICH PARTICIPANT IT MEANS, THAT DECIDES: two
        Participants may share an alias, and the reference is the identity.
        """
        with self._lock:
            held = list(self._live.values())
        verified = [i for i in held
                    if (i.participant == participant if participant
                        else i.address.name == address.name)
                    and i.liveness in (Liveness.STARTING, Liveness.FINISHED)]
        exact = [i for i in verified
                 if i.participant == participant
                 and i.address.binding_key(i.participant)
                 == address.binding_key(participant)]
        return {
            "address": str(address),
            "binding_key": address.binding_key(participant),
            "live_same_name": [i.instance_id for i in verified],
            "live_same_binding": [i.instance_id for i in exact],
            "would_reuse": exact[0].instance_id if exact else None,
            "would_reuse_runtime": exact[0].runtime if exact else None,
            "dormant": [i.instance_id for i in exact
                        if i.liveness is Liveness.FINISHED],
            "note": ("a live instance under the same name but a different "
                     "binding is legitimate concurrency, not a duplicate"),
        }

    def agents_summon(
        self,
        address: Address,
        selection: Selection,
        *,
        workspace: str,
        deliver: str | None = None,
        reuse: bool = True,
        participant: str | None = None,
        requires=(),
        open_runs: dict[str, dict] | None = None,
    ) -> Instance:
        """Reuse a handle this process holds for the same binding, or make one.

        A HANDLE, NOT A SESSION. MARS opens a session per run, so continuing
        an instance continues its identity in the record -- the same
        execution id on every act -- and nothing about a provider session.
        The constraints that made reuse safe still apply: the runtime the
        selection chose (an excluded one is never brought back), the same
        model and effort as this selection, the requirements, and the
        workspace. A run takes its model and effort from the handle, so a
        handle holding anything else would run the wrong thing; two unset
        values are equal, and a model is compared as what would actually run.
        """
        corpus = require(self._corpus)
        self._thread.notes = []
        default = routing.default_model_of(self._backend(selection.runtime))
        if reuse:
            res = self.agents_resolve(address, participant=participant)
            for candidate in res["live_same_binding"]:
                with self._lock:
                    got = self._live.get(candidate)
                    if got is None or got.liveness not in (Liveness.STARTING,
                                                           Liveness.FINISHED):
                        self._notes().append(f"{candidate}: in use or gone, not claimed")
                        continue
                    why = None
                    if got.runtime != selection.runtime:
                        why = (f"runs on {got.runtime}, and this selection chose "
                               f"{selection.runtime}")
                    elif (got.requested_model or default) != (selection.model or default):
                        why = (f"holds model {got.requested_model!r}, and this "
                               f"selection chose {selection.model!r}")
                    elif got.requested_effort != selection.requested_effort:
                        why = (f"holds effort {got.requested_effort!r}, and this "
                               f"selection chose {selection.requested_effort!r}")
                    elif got.workspace != workspace:
                        why = f"working in {got.workspace!r}, not {workspace!r}"
                    elif requires and not self.eligible(got.runtime, requires,
                                                        got.requested_model):
                        why = (f"runs on {got.runtime}, which cannot be given "
                               f"work requiring {list(requires)}")
                    if why:
                        self._notes().append(f"{candidate}: {why}; not eligible "
                                             f"for this work")
                        continue
                    claimed = replace(got, liveness=Liveness.BUSY)
                    self._live[candidate] = claimed
                self._notes().append("continued: the same execution handle; "
                                     "MARS opens a session for each run")
                return claimed
        inst = Instance(
            instance_id=str(uuid.uuid4()),
            address=address,
            participant=participant,
            runtime=selection.runtime,
            machine_id=self._machine,
            session_ref=None,
            requested_model=selection.model,
            actual_model=Observed.unknown("not invoked yet"),
            requested_effort=selection.requested_effort,
            actual_effort=Observed.unknown("not invoked yet"),
            liveness=Liveness.BUSY,
            started_at=time.time(),
            workspace=workspace,
            notes=(f"deliver={'yes' if deliver else 'no'}",),
        )
        with self._lock:
            self._live[inst.instance_id] = inst
        try:
            corpus.record_instance(inst)
        except Exception:
            with self._lock:
                self._live.pop(inst.instance_id, None)
            raise
        self._notes().append("started fresh")
        return inst

    # -- runs, as this process holds them -------------------------------------

    def agents_open_run(self, instance_id: str, run: str) -> None:
        """This process has recorded `run` as started on that handle."""
        with self._lock:
            self._runs[run] = {"run": run, "instance": instance_id,
                               "opened_at": time.time(),
                               "performing_since": None, "last_event": None,
                               "ended_at": None, "feed": RunFeed(),
                               "stop": None, "outcome": None,
                               "permissions": {}}
            self._run_of[instance_id] = run
            self._prune_runs()

    def agents_end_run(self, run: str) -> None:
        """This process no longer holds `run`, however it ended."""
        with self._lock:
            obs = self._runs.get(run)
            if obs is not None:
                obs["ended_at"] = obs.get("ended_at") or time.time()
                if self._run_of.get(obs["instance"]) == run:
                    self._run_of.pop(obs["instance"], None)
            self._prune_runs()

    #: How many ENDED run observations are kept.
    _ENDED_KEPT = 32

    def _prune_runs(self) -> None:
        ended = [r for r, o in self._runs.items() if o.get("ended_at")]
        for r in ended[:max(0, len(ended) - self._ENDED_KEPT)]:
            self._runs.pop(r, None)

    def agents_runs(self) -> dict[str, dict]:
        """What this process observes of each run it holds, by run, with
        whether MARS reports it running now (`Execution.running`)."""
        try:
            running = set(self.execution.running())
        except Exception:                                 # noqa: BLE001
            running = set()
        with self._lock:
            return {run: {**{k: v for k, v in o.items()
                             if k not in ("feed", "permissions")},
                          "permission": next(iter(dict(o.get("permissions") or {}).values()), None),
                          "permissions": list(dict(o.get("permissions") or {}).values()),
                          "activity": o["feed"].activity if o.get("feed") else None,
                          "activity_at": o["feed"].activity_at if o.get("feed") else None,
                          "running": o["instance"] in running}
                    for run, o in self._runs.items()}

    #: The members of a held run `run_observations` copies, in the order
    #: `agents_runs` gives them. A member a run hasn't reached stays absent.
    _OBSERVED = ("run", "instance", "opened_at", "performing_since",
                 "last_event", "ended_at", "stop", "outcome",
                 "consent_applied", "tooling")

    def run_observations(self) -> dict[str, dict]:
        """`agents_runs`, for `/private/live`'s `run_observations` field
        (`docs/rust/R4-R6-live-fields.md`): the same answer, holding one lock
        at a time.

        MARS's `running()` is read first, under MARS's lock alone. The named
        members are then copied under the service's lock alone, with the
        waiting permissions copied by `dict(...)`, and the lock is let go
        before anything is encoded. Whoever changes a member copied here
        replaces it whole and never changes it in place, so what was copied
        can't move under the encoder. Nothing here reads the record or calls
        MARS beyond that one local set."""
        try:
            running = set(self.execution.running())
        except Exception:                                 # noqa: BLE001
            running = set()
        with self._lock:
            copied = []
            for run, o in self._runs.items():
                feed = o.get("feed")
                copied.append((run, {k: o[k] for k in self._OBSERVED if k in o},
                               dict(o.get("permissions") or {}),
                               feed.activity if feed else None,
                               feed.activity_at if feed else None))
        rows = {}
        for run, row, permissions, activity, activity_at in copied:
            waiting = list(permissions.values())
            rows[run] = {**row, "permission": next(iter(waiting), None),
                         "permissions": waiting, "activity": activity,
                         "activity_at": activity_at,
                         "running": row["instance"] in running}
        return rows

    def agents_run_feed(self, run: str, after: int = 0) -> dict | None:
        """What MARS has reported of one run held here, since `after`
        (`mentis.core.run_feed`). None when this process does not hold it."""
        with self._lock:
            obs = self._runs.get(run)
        if obs is None:
            return None
        try:
            running = obs["instance"] in set(self.execution.running())
        except Exception:                                 # noqa: BLE001
            running = False
        feed = obs.get("feed")
        events, seq, activity, activity_at = (feed.read(after) if feed
                                              else ([], after, None, None))
        waiting = list((obs.get("permissions") or {}).values())
        return {"run": run, "held_here": True, "running": running,
                "performing_since": obs.get("performing_since"),
                "ended_at": obs.get("ended_at"),
                "activity": activity, "activity_at": activity_at,
                "stop": obs.get("stop"), "outcome": obs.get("outcome"),
                "permission": waiting[0] if waiting else None,
                "permissions": waiting,
                "events": events, "next": seq}

    def live_now(self) -> list[tuple[str, str]]:
        """What this process holds, as (instance, liveness) pairs. Cheap."""
        with self._lock:
            return sorted((i, inst.liveness.value)
                          for i, inst in self._live.items())

    def run_marks(self) -> list[tuple]:
        """Something that changes whenever a held run's observation does, for
        the pulse to compare. Not a status."""
        with self._lock:
            return sorted((run, o.get("performing_since"),
                           (o.get("last_event") or {}).get("at"),
                           o.get("ended_at"), bool(o.get("stop")),
                           len(o.get("permissions") or ()),
                           o["feed"].activity if o.get("feed") else None)
                          for run, o in self._runs.items())

    def agents_halt_run(self, run: str, *, by: str, why: str) -> bool:
        """Ask MARS to cancel a run this process holds.

        STOPPING A SESSION IS NOT FINISHING THE WORK. MARS ends the turn
        (`cancelled`, or the session is killed when the agent does not stop
        within its grace); the run then ends as cancelled and whatever it was
        asked to do stays open in the record, to be addressed again."""
        with self._lock:
            obs = self._runs.get(run)
        if obs is None or obs.get("ended_at"):
            return False
        # A RUN NOT YET PERFORMING is held to the cancel as it begins, where
        # the execution can (`MarsExecution.precancel`).
        precancel = getattr(self.execution, "precancel", None)
        asked = bool(precancel(obs["instance"]) if precancel is not None
                     else self.execution.cancel(obs["instance"]))
        if asked:
            with self._lock:
                obs["stop"] = obs.get("stop") or {"by": by, "why": why,
                                                  "at": time.time()}
        return asked

    def mcp_servers_for(self, instance_id: str, workspace: str | None) -> tuple:
        """The ONE MCP server a run is given: the Mentis bridge, under this
        run's grant, asking this server over `/api/worker` (`via`). Empty with
        no record attached: then a run has no Mentis surface, honestly."""
        token = self.authority.grant_of(instance_id)
        if not (self._record and token):
            return ()
        from mentis.worker import boot_command
        return ({"name": "mentis", "command": sys.executable,
                 "args": ["-I", "-c", boot_command(
                     self._record, via=self._answers_at, capability=token,
                     permits=self.authority.permits_for(instance_id),
                     project=workspace)],
                 "env": []},)

    def agents_perform(self, instance_id: str, work: str, *,
                       deadline_s: int | None = ...,
                       run: str | None = None,
                       resume: dict | None = None,
                       continuation: str | None = None,
                       timing: dict | None = None) -> WorkOutcome:
        """Run the work through MARS, then record what the instance became.

        The grant is minted as the run begins and revoked when it ends: it
        lasts as long as the work it authorises and no longer.

        SESSION CONTINUITY (WS-P): `resume` is the runtime session an earlier
        run of the same work left (`{"token"}`), and `continuation` what to
        send instead of `work` if MARS resumes it. `timing`, when given, is
        filled with `perform_called` (when the execution was asked).
        """
        corpus = require(self._corpus)
        with self._lock:
            inst = self._live.get(instance_id)
            if inst is None:
                raise RuntimeNotPresent(f"instance {instance_id} is not live here")
            inst = replace(inst, liveness=Liveness.BUSY)
            self._live[instance_id] = inst
        if self._record:
            self.authority._grant(instance_id, self._record)
        obs = self._runs.get(run) if run else None
        if obs is not None:
            obs["performing_since"] = time.time()
        # A DEADLINE IS MARS's `hard_s` (MARS contract §3.4: `startup_s`, `idle_s`,
        # `hard_s`, `permission_s`, `cancel_grace_s`, `session_ttl_s`; any other key is
        # refused -32602). It was sent as `timeout_s`, which MARS refused, so every run
        # with a deadline failed to open (found by Builder M, round 2).
        limits = ({"hard_s": float(deadline_s)}
                  if isinstance(deadline_s, (int, float)) and deadline_s > 0 else {})
        consent = None
        if self.run_consent is not None and run:
            try:
                consent = self.run_consent(run, inst.workspace)
            except Exception:                             # noqa: BLE001
                consent = None      # consent is the client's to answer with; MARS is told nothing
        consent_options = {}
        if self.run_options is not None and run:
            try:
                consent_options = self.run_options(run, inst.workspace, inst.runtime) or {}
            except Exception:                             # noqa: BLE001
                consent_options = {}    # as above: nothing is allowed that was not read
        mcp_servers = self.mcp_servers_for(instance_id, inst.workspace)
        tooling = None
        if self.run_tooling is not None and run:
            try:
                tooling = self.run_tooling(run, inst,
                                           self.authority.delivered_for(instance_id),
                                           mcp_servers)
            except Exception:                             # noqa: BLE001
                tooling = None      # the run is told nothing it could rely on
        spec = RunSpec(run_id=instance_id, backend=inst.runtime,
                       workspace=inst.workspace or ".", prompt=work,
                       mcp_servers=mcp_servers,
                       options={**{k: v for k, v in (
                           ("model", inst.requested_model),
                           ("effort", inst.requested_effort)) if v},
                           **consent_options},
                       limits=limits, consent=consent, tooling=tooling,
                       resume=dict(resume) if resume else None,
                       continuation=continuation if resume else None)

        def on_event(ev: RunEvent) -> None:
            if obs is not None:
                obs["last_event"] = {"kind": ev.kind, "at": ev.at,
                                     "what": _event_words(ev)}
                if obs.get("feed") is not None:
                    obs["feed"].add(ev.kind, ev.data, ev.at)
            # WHAT A RUN UNDER COMPILED RULES DID, recorded as it goes
            # (`web.permissions`, WS-A). Never fails the event.
            tap = getattr(self.permission_policy, "observe_event", None)
            if tap is not None and run:
                try:
                    tap(run, ev.kind, ev.data, ev.at)
                except Exception:                         # noqa: BLE001
                    pass

        def on_permission(request: dict) -> str | None:
            # WHO ANSWERS AN AGENT'S PERMISSION REQUEST is the web layer's
            # policy (`permission_policy`, set where the record is): the
            # run's authority, or the owner through a decision form. Without
            # one, MARS's request is answered as MarsExecution always did.
            policy = self.permission_policy
            if policy is None or not run:
                return ...
            return policy(run, instance_id, request, obs)
        if timing is not None:
            timing["perform_called"] = time.time()
        # THE CONSENT AS IT STANDS NOW, as the session opens: a narrowing
        # since it was first read reaches the runtime's rules (`web.permissions`).
        # FROM HERE A CANCEL IS HELD FOR THE RUN until its perform begins
        # (`MarsExecution.expect`/`precancel`); after it returns, none is.
        expect = getattr(self.execution, "expect", None)
        if expect is not None:
            expect(inst.instance_id)
        before_open = getattr(self.permission_policy, "before_open", None)
        if before_open is not None and run and isinstance(consent, dict):
            try:
                before_open(run, inst.workspace, consent)
            except Exception:                             # noqa: BLE001
                consent.pop("runtime_rules", None)        # fail closed: no compiled rules
        try:
            res = self.execution.perform(spec, on_event, on_permission)
        except Exception as exc:                          # noqa: BLE001
            # `perform` never raises for an agent failure; anything here is
            # the boundary itself failing, and is said as a run that did not
            # start rather than raised into the dispatch thread.
            res = RunResult(run_id=instance_id, backend=inst.runtime,
                            started=False, error_kind="execution_error",
                            error=f"{type(exc).__name__}: {exc}",
                            started_at=time.time(), finished_at=time.time())
        finally:
            self.authority.revoke(instance_id)
            if obs is not None:
                obs["ended_at"] = time.time()
        if obs is not None:
            obs["consent_applied"] = res.consent_applied
            obs["tooling"] = res.tooling
            obs["outcome"] = {"stop_reason": res.stop_reason,
                              "error_kind": res.error_kind,
                              "error": res.error,
                              "stopped": bool(obs.get("stop")),
                              "session_ended": res.error_kind in (
                                  "cancel_forced", "cleanup_failed")}
        outcome, updated = _outcome_of(inst, res)
        # PERMISSION ANSWERS WRITTEN BEFORE THE RUN'S END, and what compiled
        # rules let it do without asking (`web.permissions.end_of_run`).
        end_of_run = getattr(self.permission_policy, "end_of_run", None)
        if end_of_run is not None and run:
            try:
                end_of_run(run, consent, res.tool_calls, outcome.evidence)
            except Exception:                             # noqa: BLE001
                pass        # an audit summary never fails the run's end
        with self._lock:
            held = self._live.get(instance_id) is not None
            if held:
                self._live[instance_id] = updated
        # RELEASE IS FINAL: a run that ends after its handle was let go is
        # still reported -- the work happened -- but what is recorded says
        # GONE, so the latest observation never contradicts the release.
        if not held:
            updated = replace(updated, liveness=Liveness.GONE)
        corpus.record_instance(updated)
        return outcome

    def agents_observe(self, instance_id: str) -> Instance:
        corpus = require(self._corpus)
        live = self._live.get(instance_id)
        if live is not None:
            return live
        for rec in reversed(corpus.instance_history()):
            if rec.get("instance_id") == instance_id:
                return _from_record(rec, self._machine)
        raise InstanceNotFound(instance_id)

    def agents_list(self, *, include_finished: bool = False) -> list[Instance]:
        """What this process holds that is live, unless history is asked for.

        A record nothing here holds is not live: nothing outlives a run.

        SO THE LIVE ONES ARE READ FROM WHAT IS HELD, NOT THE HISTORY: every
        held handle was recorded when it was taken, and `_from_record` never
        reads a record as live. The history file only grows (6.6 MB on the
        2026-10-31 Brain, ~120 ms to parse), and the server observes runs
        on every work read (`web._runtime_observation`).
        """
        corpus = require(self._corpus)
        if not include_finished:
            with self._lock:
                held = list(self._live.values())
            return [i for i in held if i.liveness in (
                Liveness.ALIVE, Liveness.STARTING, Liveness.BUSY)]
        seen: dict[str, Instance] = {}
        for rec in corpus.instance_history():
            inst = _from_record(rec, self._machine)
            seen[inst.instance_id] = self._live.get(inst.instance_id) or inst
        out = list(seen.values())
        if not include_finished:
            out = [i for i in out if i.liveness in (
                Liveness.ALIVE, Liveness.STARTING, Liveness.BUSY)]
        return out

    def agents_release(self, instance_id: str) -> ReleaseResult:
        """Let go of the handle, and RECORD that we did (`GONE`), so no later
        run continues it. A run still inside it is cancelled through MARS."""
        corpus = require(self._corpus)
        with self._lock:
            inst = self._live.pop(instance_id, None)
        self.authority.revoke(instance_id)
        if inst is None:
            return ReleaseResult(instance_id=instance_id, released=True,
                                 verified_against_machine=False,
                                 notes=("nothing live here under that id",))
        notes = []
        try:
            if instance_id in set(self.execution.running()):
                self.execution.cancel(instance_id)
                notes.append("a run was inside it; MARS was asked to cancel it")
        except Exception as exc:                          # noqa: BLE001
            notes.append(f"whether a run was inside it could not be asked: {exc}")
        corpus.record_instance(replace(inst, liveness=Liveness.GONE,
                                       finished_at=inst.finished_at or time.time()))
        return ReleaseResult(instance_id=instance_id, released=True,
                             verified_against_machine=False, notes=tuple(notes))

    def close(self) -> None:
        with self._lock:
            keeper, self._keeper = self._keeper, None
        if keeper is not None:
            keeper.set()
        try:
            self.execution.close()
        except Exception:                                 # noqa: BLE001
            pass


def _all_exhausted(views: dict, now: float) -> str:
    """The refusal when every eligible runtime is exhausted: each one's why,
    the soonest known expiry, and whether that rests only on the cooldown
    held after a quota failure that reported no reset."""
    words = ("every eligible runtime is exhausted: "
             + "; ".join(v["why"] for v in views.values()))
    ends = [(v["expires_at"], k) for k, v in views.items()
            if _number(v.get("expires_at"))]
    if not ends:
        return words + "; when any of them comes back is not known"
    at, first = min(ends)
    words += (f"; the soonest back is {first}, in {_span(at - now)} "
              f"({time.strftime('%Y-%m-%d %H:%M', time.localtime(at))})")
    if views[first].get("cooldown"):
        words += (f" -- and that rests only on the "
                  f"{int(QUOTA_COOLDOWN_S // 60)}-minute cooldown after a "
                  f"quota failure that reported no reset time, not on a "
                  f"reported reset")
    return words


def _effort_support(backend: dict, model: str | None, effort: str) -> str:
    """What the catalogue says of a named effort: `supported`, `unadvertised`
    (it lists efforts, and not this one), or `unknown` (it says nothing). A
    model MARS walked is judged by its own efforts, never the backend's list."""
    running = model or routing.default_model_of(backend)
    walked = next((r for r in routing.tuples_of(backend)
                   if r["model"] == running), None)
    if walked is not None:
        return "supported" if effort in walked["efforts"] else "unadvertised"
    listed = [str(e) for e in backend.get("efforts") or ()]
    if not listed:
        return "unknown"
    return "supported" if effort in listed else "unadvertised"


def _conflict_words(runtime: str, model: str | None, effort: str) -> str:
    """Why this model and effort cannot go to a runtime that names efforts in its
    models, in words."""
    return (f"effort {effort!r} "
            + (f"with model {model!r}" if model else "with no model")
            + f" is a hard error on {runtime}, whose models carry their effort "
              f"in their id")


def _considered_words(rows: list, present: list) -> str:
    """What was considered for a tier nothing could meet, in words."""
    said = [f"{r['runtime']} {r['model']} ({r['tier']}, {r['effort']}): {r['why']}"
            for r in rows]
    bare = sorted({b["id"] for b in present} - {r["runtime"] for r in rows})
    if bare:
        said.append(f"nothing adequate is advertised by {bare}")
    return "; ".join(said) or "nothing adequate is advertised"


def _event_words(ev: RunEvent) -> str:
    d = ev.data or {}
    if ev.kind in ("tool_call", "tool_call_update"):
        return f"{ev.kind}: {d.get('title') or d.get('kind') or 'a tool'}" + (
            f" ({d['status']})" if d.get("status") else "")
    if ev.kind == "agent_message_chunk":
        return "the agent is writing"
    return ev.kind


def _outcome_of(inst: Instance, res: RunResult) -> tuple[WorkOutcome, Instance]:
    """What MARS reported, as the `WorkOutcome` callers already read.

    `terminal` is `reported_done` only when the turn ended normally
    (stop_reason `end_turn`). A cancelled turn is `cancelled`, any other stop
    reason is named as itself, and an error is `failed` (`stopped_at_deadline`
    where MARS says a limit stopped it). None of these says the work is done:
    that is decided by the record, not by how a turn ended.
    """
    timed_out = bool(res.error_kind and "timeout" in res.error_kind)
    if res.error_kind or res.error:
        terminal = "stopped_at_deadline" if timed_out else "failed"
    elif res.stop_reason == "end_turn":
        terminal = REPORTED_DONE
    else:
        terminal = res.stop_reason or "failed"
    error = None
    if res.error_kind or res.error:
        error = f"{res.error_kind or 'error'}: {res.error or 'MARS gave no detail'}"
    elif terminal != REPORTED_DONE:
        error = f"the turn ended with stop reason {res.stop_reason!r}"
    usage = dict(res.usage or {})
    model = usage.get("model") if isinstance(usage.get("model"), str) else None
    notes = [f"MARS backend {res.backend}"
             + (f", session {res.session_id}" if res.session_id else "")]
    if not res.started:
        notes.append("no agent session opened")
    notes.append("`reported` is the agent's own claim and is not evidence that "
                 "the work happened; verify the artifact")
    outcome = WorkOutcome(
        instance_id=inst.instance_id, terminal=terminal,
        reported=res.text or None, exit_code=None, started=bool(res.started),
        timed_out=timed_out, error=error,
        tool_calls=tuple(res.tool_calls or ()),
        # MARS reports tool calls (ACP tool_call updates), so their absence
        # is an observation too.
        tool_calls_observable=bool(res.started),
        usage=usage, notes=tuple(notes),
        evidence={k: v for k, v in (("stop_reason", res.stop_reason),
                                    ("error_kind", res.error_kind),
                                    ("error", res.error),
                                    ("session_id", res.session_id),
                                    # HOW MARS SAID THE RUN'S CONSENT WAS
                                    # ENFORCED (`none`: it could not be).
                                    ("consent_applied", res.consent_applied),
                                    # WHAT THE RUN WAS TOLD IT COULD REACH
                                    # (docs/tooling-context.md).
                                    ("tooling", res.tooling),
                                    # WHAT THE TURN LEFT BEHIND, as MARS read
                                    # it: background work (stopped with the
                                    # session) and the git trees it edited.
                                    ("background", getattr(res, "background", None)),
                                    ("workspace", getattr(res, "workspace", None)),
                                    ("started_at", res.started_at),
                                    ("finished_at", res.finished_at),
                                    # THE QUOTA RESET MARS REPORTED: seconds
                                    # from the failure, and the absolute time.
                                    ("retry_after_s", res.retry_after_s),
                                    ("resets_at", _resets_at(res)),
                                    # WHICH REQUESTED OPTION MARS SAID IS NOT
                                    # OFFERED, and what it does offer. Kept as
                                    # reported; dispatch says what it means.
                                    ("option", res.option),
                                    ("offered", res.offered),
                                    # SESSION CONTINUITY (WS-P): the runtime
                                    # session a later run may continue, and
                                    # whether this one continued one.
                                    ("runtime_session",
                                     getattr(res, "runtime_session", None)),
                                    ("resumed", getattr(res, "resumed", None)),
                                    # WHERE THE TIME WENT inside the boundary.
                                    ("timing", getattr(res, "timing", None) or None))
                  if v is not None})
    updated = replace(
        inst, session_ref=res.session_id or inst.session_ref,
        actual_model=_actual_model_of(model, res),
        actual_effort=Observed.unknown("MARS does not report the effort that ran"),
        liveness=(Liveness.FINISHED if res.started and not res.error_kind
                  else Liveness.FAILED),
        finished_at=res.finished_at or time.time())
    return outcome, updated


DECLARED_BY_MARS = "declared by MARS"


def _actual_model_of(model: str | None, res) -> Observed:
    """The model that ran: the provider's usage report first; otherwise the model
    MARS declares in its tooling report, marked as declared (not provider-reported)."""
    if model:
        return Observed(model, Provenance.PROVIDER_REPORTED)
    declared = (getattr(res, "tooling", None) or {}).get("model")
    # `by: mentis` is the request echoed back by Mentis's own tooling record,
    # not something MARS said ran.
    if not isinstance(declared, dict) or declared.get("by") == "mentis":
        declared = None
    else:
        declared = declared.get("id")
    if isinstance(declared, str) and declared:
        return Observed(declared, Provenance.LOCALLY_INFERRED, note=DECLARED_BY_MARS)
    return Observed.unknown("MARS reported no model for this run")


def _resets_at(res) -> float | None:
    """When the runtime said its quota resets: the run's end plus MARS's reported
    `retryAfterSeconds`; None when no reset was reported."""
    retry = getattr(res, "retry_after_s", None)
    if retry is None:
        return None
    return (res.finished_at or time.time()) + retry


def _observed_from(raw) -> Observed:
    if isinstance(raw, dict):
        try:
            prov = Provenance(raw.get("provenance", "unknown"))
        except ValueError:
            prov = Provenance.UNKNOWN
        return Observed(value=raw.get("value"), provenance=prov,
                        observed_at=raw.get("observed_at", 0.0),
                        note=raw.get("note"))
    return Observed.unknown("not recorded")


def _from_record(rec: dict, machine: str) -> Instance:
    """A corpus record back as an Instance. Nothing outlives a run, so a
    record this process does not hold is never live: GONE unless it ended."""
    addr = rec.get("address") or {}
    recorded = rec.get("liveness", "unknown")
    liveness = (Liveness(recorded) if recorded in ("finished", "failed", "gone")
                else Liveness.GONE)
    return Instance(
        instance_id=rec.get("instance_id", ""),
        address=Address(name=addr.get("name", "?"), runtime=addr.get("runtime"),
                        persona=addr.get("persona"), context=addr.get("context")),
        participant=rec.get("participant"),
        runtime=rec.get("runtime", "?"),
        machine_id=rec.get("machine_id", "?"),
        session_ref=rec.get("session_ref"),
        requested_model=rec.get("requested_model"),
        actual_model=_observed_from(rec.get("actual_model")),
        requested_effort=rec.get("requested_effort"),
        actual_effort=_observed_from(rec.get("actual_effort")),
        liveness=liveness,
        started_at=rec.get("started_at", 0.0),
        workspace=rec.get("workspace"),
        finished_at=rec.get("finished_at"),
        notes=("recorded; not held by this process",))


class _Unavailable:
    """An `Execution` with nothing behind it: no backends, and every run
    refused with `backend_unavailable` and the reason, so a server without
    MARS still serves the record and says why no agent answers."""

    def __init__(self, why: str) -> None:
        self.why = why

    def backends(self) -> list[dict]:
        return []

    def perform(self, spec: RunSpec, on_event=None, on_permission=None) -> RunResult:
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="backend_unavailable",
                         error=self.why, started_at=now, finished_at=now)

    def cancel(self, run_id: str) -> bool:
        return False

    def running(self) -> set[str]:
        return set()

    def close(self) -> None:
        pass


def unavailable_execution(why: str) -> Execution:
    return _Unavailable(why)


def mars_argv(command: str | list[str] | None) -> list[str]:
    """The MARS command line as an argument list. A string is split the way this
    platform's shell would: on Windows backslashes are path separators, not escapes
    (`C:\\Work\\MARS-venv\\Scripts\\mars.exe stdio`), and quotes group a path with
    spaces."""
    import os
    import shlex
    if not command:
        return []
    if not isinstance(command, str):
        return list(command)
    if os.name == "nt":
        return [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p
                for p in shlex.split(command, posix=False)]
    return shlex.split(command)


def mars_execution(command: str | None) -> Execution:
    """`mentis.execution.mars.MarsExecution(command)`, imported BY NAME and
    lazily, so this package works before that module exists. Without it, or
    if it cannot start, an Execution that says why no agent can run."""
    import importlib
    try:
        mod = importlib.import_module("mentis.execution.mars")
    except ImportError as exc:
        return unavailable_execution(
            f"MARS is not available: mentis.execution.mars cannot be imported "
            f"({exc})")
    try:
        return mod.MarsExecution(mars_argv(command))
    except Exception as exc:                              # noqa: BLE001
        return unavailable_execution(
            f"MARS could not be started with {command!r}: "
            f"{type(exc).__name__}: {exc}")
