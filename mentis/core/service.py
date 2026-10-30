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

#: How long automatic selection (dispatch's own thread) waits for a fresh
#: `_mars/capacity` read before deciding on what is already held.
CAPACITY_WAIT_S = 5.0

#: How old a held answer the judge paths (`execution_usable`, the default
#: `capacity_view`) still use. They never ask MARS; past this they have none.
CAPACITY_STALE_S = 600.0

#: The cooldown a quota failure with no reported reset is held for (owner,
#: 2026-10-29; the holds are made in `mentis.web.quota`). Here only to say
#: when a refusal rests on it alone.
QUOTA_COOLDOWN_S = 3600.0


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
        #: (run, instance, delivered, mcp_servers) -> the run's tooling
        #: function for MARS execution (`RunSpec.tooling`), or None. Set by
        #: the web layer, beside the consent (docs/tooling-context.md).
        self.run_tooling = None
        self._run_of: dict[str, str] = {}
        #: WHEN EACH RUNTIME WAS LAST SELECTED, as a sequence number, for the
        #: tie-break in `execution_select`. This process only.
        self._last_selected: dict[str, int] = {}
        self._selections = 0
        #: The last `_mars/capacity` answer, when it was read (monotonic) and,
        #: when it is empty because the read failed, why. Failures are kept.
        self._capacity: tuple[float, dict, str | None] | None = None
        #: The `_mars/capacity` read in flight, if one is (single flight).
        self._capacity_flight: threading.Event | None = None
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
        try:
            return [b for b in (self.execution.backends() or [])
                    if isinstance(b, dict) and b.get("id")]
        except Exception:                                 # noqa: BLE001
            return []

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
        with self._lock:
            self._capacity = (time.monotonic(), report, why)
            self._capacity_flight = None
        flight.set()

    def _capacity_answer(self, wait: float | None = None, *,
                         cached_only: bool = False) -> tuple[dict, str | None]:
        """MARS's `_mars/capacity` and, when it says nothing, why.

        SINGLE FLIGHT. `_mars/capacity` can start runtime processes and take
        over a minute, so one read is in flight at a time, on its own
        thread, and every caller shares it. `wait` bounds how long THIS
        caller waits for it (None: until it answers); a caller that stops
        waiting gets the last answer already held, and the read goes on.

        `cached_only` never asks MARS: the answer already held, up to
        `CAPACITY_STALE_S` old, or nothing. What the judge paths use.
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
        ahead) also makes it exhausted, with the hold's own why -- except
        that a hold naming no model does not block a run whose model was
        requested explicitly, and a hold naming a model blocks only a run of
        that model.

        `expires_at`: for an AVAILABLE runtime, the reset instant of its
        budget window (the longest stated window: what is lost at reset);
        for an EXHAUSTED one, when the exhaustion is known to end (the
        exhausted windows' reset, the hold's `until`). None when not known.

        `fresh` reads MARS (single flight, bounded wait) -- only selection on
        dispatch's own thread does. Otherwise only an answer already held is
        used and MARS is never asked: the judge paths must not stall.
        """
        report, why_none = (self._capacity_answer(CAPACITY_WAIT_S) if fresh
                            else self._capacity_answer(cached_only=True))
        return self._view(self._reading(runtime, report, why_none), model,
                          holds, time.time())

    @staticmethod
    def _hold_on(runtime: str, model: str | None, holds, now: float):
        """The quota hold that applies to this run, or None."""
        h = (holds or {}).get(runtime) if isinstance(holds, dict) else None
        if not isinstance(h, dict) or not _number(h.get("until")) \
                or h["until"] <= now:
            return None
        held_model = h.get("model")
        if held_model is None:
            return None if model else h
        return h if model == held_model else None

    @staticmethod
    def _cooldown(hold: dict) -> bool:
        """Whether a hold rests only on the cooldown, not a reported reset."""
        if isinstance(hold.get("cooldown"), bool):
            return hold["cooldown"]
        since = hold.get("since")
        return _number(since) and abs(hold["until"] - since - QUOTA_COOLDOWN_S) < 1

    def _view(self, reading: CapacityReading, model: str | None, holds,
              now: float) -> dict:
        kind = reading.runtime
        v = self._report_view(reading, model, now)
        hold = self._hold_on(kind, model, holds, now)
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
                            w.resets_at - w.window_seconds <= reading.observed_at
                            < w.resets_at)))]
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
                     views: dict) -> tuple[dict, list[str], list[dict], bool]:
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

        Returns the chosen backend, the account, the ranking, and whether
        the last tie-break decided it.
        """
        order = {b["id"]: n for n, b in enumerate(backends)}
        with self._lock:
            last_selected = dict(self._last_selected)
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
        names = {0: "available", 1: "capacity or budget reset unknown"}
        account = []
        for tier, _neg, _last, _o, b, v, pace in rows:
            line = f"{b['id']}: {names[tier]}"
            if v["figures"]:
                line += " (" + "; ".join(v["figures"]) + ")"
            if tier == 0:
                line += (f"; {v['budget_left']:.0%} of its budget window "
                         f"unused with {_span(v['expires_at'] - now)} to its "
                         f"reset: {pace * 100:.2f}% of it per hour would go "
                         f"unused")
            account.append(line)
        tier, neg, chosen = rows[0][0], rows[0][1], rows[0][4]
        tied = [r[4]["id"] for r in rows[1:] if r[0] == tier and r[1] == neg]
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
                    "last_selected": r[2], "catalogue_order": r[3]} for r in rows]
        return chosen, [
            "capacity ranking, each by its own report, no score; expected "
            "task consumption unknown, only exhaustion is judged: "
            + " | ".join(account),
            f"runtime {chosen['id']} chosen: {reason}"], ranking, bool(tied)

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
    ) -> Selection:
        """Resolve a runtime/model/effort, and say what informed the choice.

        Runtimes are MARS backends; one is usable when MARS reports it
        available. `requires` NARROWS who is eligible and nothing else. An
        explicit runtime or model is a constraint: refused, never substituted.

        CAPACITY (Mark IV `Foundation.select`, owner approval 2026-10-29).
        Automatic selection reads each eligible runtime's capacity view --
        its own reported windows, and `holds`, the quota holds the record's
        failures put on it -- and, right after the requirement and model
        filters and BEFORE review avoidance, drops the exhausted ones. If
        that leaves none, it refuses, naming the soonest expiry. Then review
        avoidance, then continuity (`prefer`), then `_by_capacity`, whose
        last tie-break is the runtime selected least recently here, then
        MARS's catalogue order. A NAMED runtime is never substituted: its
        exhaustion is said in `because` and `inputs["disclosed"]`.

        This runs on dispatch's own thread, so it may refresh capacity from
        MARS -- one read in flight, waited for at most `CAPACITY_WAIT_S`.

        `prefer` is CONTINUITY, not a constraint: the runtime of a handle this
        Participant already holds for this binding. Among the eligible it wins
        before the rotation, so a Participant's next request in a Conversation
        stays where its last one ran instead of being rotated onto a runtime
        nothing here has tried (2026-10-27: the Caretaker's search went from
        Codex to Gemini that way, and Gemini's web search hung for 900 s). It
        is ignored when that runtime is not eligible, not available, or is the
        one a review must avoid.
        """
        backends = self._backends()
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
        report, why_none = self._capacity_answer(CAPACITY_WAIT_S)
        now = time.time()
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
            # SAID, NEVER ACTED ON: a named runtime is not substituted.
            view = self._view(self._reading(runtime, report, why_none), model,
                              holds, now)
            inputs["capacity"] = {runtime: self._compact(view)}
            if view["state"] == "exhausted":
                said = f"{view['why']}; run as named, not substituted"
                because.append(said)
                inputs.setdefault("disclosed", []).append(said)
                dims.append("capacity_disclosed")
        else:
            # EXHAUSTION FIRST, BEFORE REVIEW AVOIDANCE (Mark IV's order): a
            # review whose only unexhausted runtime is the author's runs
            # there, saying independence was not achievable.
            views = {b["id"]: self._view(self._reading(b["id"], report,
                                                       why_none),
                                         model, holds, now)
                     for b in present}
            inputs["capacity"] = {k: self._compact(v) for k, v in views.items()}
            because.append("capacity, each by its own report and the quota "
                           "holds: " + "; ".join(v["why"] for v in views.values()))
            dims.append("capacity_gate")
            open_ = [b for b in present if views[b["id"]]["state"] != "exhausted"]
            out = [b["id"] for b in present if views[b["id"]]["state"] == "exhausted"]
            if not open_:
                raise RuntimeNotPresent(_all_exhausted(views, now))
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
                        f"other runtime is available and unexhausted; "
                        f"independence by runtime was not achievable")
                dims.append("review_independence")
            excluded = tuple(out)
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
            inputs["candidates"] = [b["id"] for b in open_]
            continuing = next((b for b in open_ if b["id"] == prefer), None)
            if continuing is not None:
                chosen = continuing
                because.append(f"continuing on {chosen['id']}: the runtime this "
                               f"participant's handle here already runs on")
                dims.append("continuity")
            else:
                if prefer:
                    because.append(f"the handle here runs on {prefer}, which "
                                   f"cannot take this work now; not continued")
                chosen, account, ranking, tied = self._by_capacity(
                    open_, backends, views)
                inputs["ranking"] = ranking
                because.extend(account)
                dims.append("capacity_expiry")
                if tied:
                    dims.append("least_recently_selected")
        inputs["eligible"] = [b["id"] for b in present]
        inputs["excluded"] = list(excluded)
        dims.append("runtime_presence")
        with self._lock:
            self._selections += 1
            self._last_selected[chosen["id"]] = self._selections
        req_effort = effort
        if effort:
            because.append(f"effort {effort!r} was requested explicitly")
            dims.append("requested_effort")
        else:
            # DIFFICULTY DOES NOT SET EFFORT unless that is turned on. MARS now
            # lists ACP agents' efforts, so this Mark IV rule would start
            # running ordinary work at `medium` instead of each runtime's own
            # default -- a change the owner has not decided (2026-10-27).
            word = {"trivial": "low", "ordinary": "medium",
                    "hard": "high"}.get(difficulty, "medium")
            if (_EFFORT_FROM_DIFFICULTY
                    and word in {str(e) for e in chosen.get("efforts") or ()}):
                req_effort = word
                because.append(f"effort {word!r} from difficulty {difficulty!r}"
                               f" using {chosen['id']}'s own effort vocabulary")
                dims.append("difficulty")
        if model:
            because.append(f"model {model!r} was requested explicitly")
            dims.append("requested_model")
        else:
            because.append("no model chosen: the runtime's own default is used")
        return Selection(runtime=chosen["id"], model=model,
                         requested_effort=req_effort, because=tuple(because),
                         dimensions_used=tuple(dims), excluded=excluded,
                         inputs=inputs)

    def execution_usable(self, runtime: str, requires=(),
                         model: str | None = None, holds=None) -> str | None:
        """None when `runtime` could take this work now, else why not:
        unlisted, unavailable, ineligible, or exhausted by its own report or
        a quota hold (Mark IV `Foundation.usable`). What a PREFERENCE -- a
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
                # alternative (found by independent review).
                sure = [x["id"] for x in self._backends()
                        if x["id"] != runtime and x.get("available")
                        and all(r["verdict"] == "supported" for r in
                                self.eligibility(x["id"], requires, model).values())
                        and self.capacity_view(x["id"], None, holds)["state"]
                        != "exhausted"]
                if sure:
                    return (f"whether {runtime} has {unsure} is not established, "
                            f"and {sure} are confirmed for it")
        view = self.capacity_view(runtime, model, holds)
        return view["why"] if view["state"] == "exhausted" else None

    def execution_eligibility(self, runtime: str, requires,
                              model: str | None = None) -> dict:
        return self.eligibility(runtime, requires, model)

    def provider_of(self, runtime: str, model: str | None) -> str | None:
        """Who serves this model under that harness: not reported by MARS."""
        return None

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
        explicit_model: str | None = None,
        explicit_effort: str | None = None,
        open_runs: dict[str, dict] | None = None,
    ) -> Instance:
        """Reuse a handle this process holds for the same binding, or make one.

        A HANDLE, NOT A SESSION. MARS opens a session per run, so continuing
        an instance continues its identity in the record -- the same
        execution id on every act -- and nothing about a provider session.
        The constraints that made reuse safe still apply: the runtime the
        selection chose (an excluded one is never brought back), an explicit
        model or effort, the requirements, and the workspace.
        """
        corpus = require(self._corpus)
        self._thread.notes = []
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
                    elif explicit_model and got.requested_model != explicit_model:
                        why = (f"bound to model {got.requested_model!r}, and "
                               f"{explicit_model!r} was explicitly requested")
                    elif explicit_effort and got.requested_effort != explicit_effort:
                        why = (f"bound to effort {got.requested_effort!r}, and "
                               f"{explicit_effort!r} was explicitly requested")
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
                                     "MARS opens a new session for each run")
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
        asked = bool(self.execution.cancel(obs["instance"]))
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
                       run: str | None = None) -> WorkOutcome:
        """Run the work through MARS, then record what the instance became.

        The grant is minted as the run begins and revoked when it ends: it
        lasts as long as the work it authorises and no longer.
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
        limits = ({"timeout_s": float(deadline_s)}
                  if isinstance(deadline_s, (int, float)) else {})
        consent = None
        if self.run_consent is not None and run:
            try:
                consent = self.run_consent(run, inst.workspace)
            except Exception:                             # noqa: BLE001
                consent = None      # consent is the client's to answer with; MARS is told nothing
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
                       options={k: v for k, v in (
                           ("model", inst.requested_model),
                           ("effort", inst.requested_effort)) if v},
                       limits=limits, consent=consent, tooling=tooling)

        def on_event(ev: RunEvent) -> None:
            if obs is not None:
                obs["last_event"] = {"kind": ev.kind, "at": ev.at,
                                     "what": _event_words(ev)}
                if obs.get("feed") is not None:
                    obs["feed"].add(ev.kind, ev.data, ev.at)

        def on_permission(request: dict) -> str | None:
            # WHO ANSWERS AN AGENT'S PERMISSION REQUEST is the web layer's
            # policy (`permission_policy`, set where the record is): the
            # run's authority, or the owner through a decision form. Without
            # one, MARS's request is answered as MarsExecution always did.
            policy = self.permission_policy
            if policy is None or not run:
                return ...
            return policy(run, instance_id, request, obs)
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
        """
        corpus = require(self._corpus)
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
                                    ("started_at", res.started_at),
                                    ("finished_at", res.finished_at),
                                    # THE QUOTA RESET MARS REPORTED: seconds
                                    # from the failure, and the absolute time.
                                    ("retry_after_s", res.retry_after_s),
                                    ("resets_at", _resets_at(res)))
                  if v is not None})
    updated = replace(
        inst, session_ref=res.session_id or inst.session_ref,
        actual_model=(Observed(model, Provenance.PROVIDER_REPORTED) if model
                      else Observed.unknown("MARS reported no model for this run")),
        actual_effort=Observed.unknown("MARS does not report the effort that ran"),
        liveness=(Liveness.FINISHED if res.started and not res.error_kind
                  else Liveness.FAILED),
        finished_at=res.finished_at or time.time())
    return outcome, updated


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
