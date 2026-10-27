"""Foundation: runtime execution on THIS machine.

Everything Foundation holds is machine-local. It never writes to the corpus --
`mentis.core` does that, and it writes observations, not machine truth.

Foundation contains no behavioural or operational prose. It discovers and uses
delivery mechanisms; it does not author what gets delivered.
"""

from __future__ import annotations

from mentis.foundation import scratch as _scratch

import secrets
import math
import threading
import time
import uuid
from dataclasses import asdict, replace
from typing import Any

from mentis.api.errors import RuntimeNotPresent, Unsupported
from mentis.api.types import (
    Address,
    Capability,
    Instance,
    Liveness,
    Observed,
    Provenance,
    ReleaseResult,
    RuntimeInfo,
    Selection,
    WorkOutcome,
)

from .observe import RunObservation
from .runtimes import adapter_classes
from .runtimes.antigravity import AntigravityAdapter
from .runtimes.base import Invocation, RuntimeAdapter
from .runtimes.claude import ClaudeAdapter
from .runtimes.codex import CodexAdapter
from . import tool_use as _tool_use

# Difficulty is Foundation's only vocabulary for "how hard is this work".
# It is not an effort level: each runtime's effort vocabulary is its own, and
# the mapping happens per runtime because the three genuinely differ.
_DIFFICULTY_ORDER = ("trivial", "ordinary", "hard")

#: The terminal of a run whose process tree Mentis stopped because it had
#: stopped making progress (`mentis.watchdog`): it did not finish its work.
STALLED = "stalled"


class Foundation:
    def __init__(self) -> None:
        self._adapters: dict[str, RuntimeAdapter] = {
            a.kind: a for a in (cls() for cls in adapter_classes())
        }
        #: What each locally served model has DEMONSTRATED it can do behind
        #: each runtime. See `tool_use`.
        self.tool_use = _tool_use.Ledger()
        # Live instances, this process, this machine. Never durable.
        self._live: dict[str, Instance] = {}
        self._deliver: dict[str, str | None] = {}
        #: The record workers dispatched from here may query. Set by whoever
        #: attached a corpus; unset means workers get no query surface, which
        #: is the old behaviour and still an honest one.
        self._record: str | None = None
        #: Scratch answers running now, by the caller's key (`answer_once`).
        self._answering: dict = {}
        #: WHERE THE OWNER OF THAT RECORD ANSWERS. A worker that cannot
        #: open the corpus has to be able to reach something that can, and
        #: only the process that opened it knows where it is listening.
        #: Unset means workers get no query surface -- the honest gap.
        self._answers_at: str | None = None
        self._writable: tuple[str, ...] = ()
        #: WHAT A DISPATCHED WORKER IS AUTHORISED TO ASK: token -> grant.
        #:
        #: Live, this process, never durable -- the same bookkeeping as
        #: `_live` above, for the same reason. An execution is a machine-
        #: local fact, and a runtime's authorisation is not something the
        #: record should ever be asked to carry.
        self._grants: dict[str, dict[str, Any]] = {}
        self._granted_to: dict[str, str] = {}
        #: WHY AN EXECUTION WAS DISPATCHED, which is what decides how much it
        #: may do. Set at summon by the caller that knows -- intake -- and read
        #: when the grant is minted, so authority rides on the grant rather than
        #: on who the Participant is or what it is called. An execution nobody
        #: set this for gets the ordinary worker scope, which is the four reads
        #: plus asking the owner for a decision about its own work.
        self._authority: dict[str, dict[str, Any]] = {}
        #: ONE LOCK OVER THE LIVE BOOKKEEPING. Selecting an instance and
        #: then running it were two steps with nothing in between, so two
        #: dispatches could choose the same dormant session and both use
        #: it. Claiming is now a single indivisible step.
        self._lock = threading.RLock()
        #: Instances this process has let go of. Kept because a perform
        #: already inside `adapter.run` when release happened used to write
        #: its instance back afterwards -- reproduced: release reported
        #: released, the handle vanished, and then reappeared as FINISHED
        #: with its grant already revoked. Release has to be final.
        self._released: set[str] = set()
        #: Instances a perform is INSIDE right now. Separate from being
        #: claimed: a claim is a reservation made by whoever selected the
        #: instance, and this is the runtime actually running. Keeping them
        #: apart is what lets a caller claim an instance and then perform it
        #: while a second caller is refused both.
        self._inflight: set[str] = set()
        #: HOW LONG A RUN MAY TAKE, as policy rather than as a constant
        #: buried in a dataclass. None means no deadline: a run ends when
        #: the process ends. A number is a boundary somebody chose, and it
        #: can be overridden for one dispatch.
        self.deadline_s: int | None = None
        #: WHAT THIS PROCESS OBSERVES OF EACH RUN IT HOLDS, keyed by the run
        #: -- the `execution-started` act -- and never by the instance, which
        #: is a handle many runs pass through. See `mentis.foundation.observe`.
        #: An ended run's observation is kept a little while (`_ENDED_KEPT`)
        #: so the interval between its process exiting and its end being
        #: recorded is still readable, and then dropped: memory here is
        #: bounded by what is running, not by what has ever run.
        self._runs: dict[str, RunObservation] = {}
        self._run_of: dict[str, str] = {}
        #: The observation of the run a perform is inside, by handle.
        self._performing: dict[str, RunObservation] = {}
        #: THE LATEST CAPACITY EACH RUNTIME REPORTED WITHOUT BEING ASKED: in
        #: band on a run this process performed (Claude's rate-limit event,
        #: Codex's rollout), or through `capacity_observe`. Machine-local and
        #: never durable; after a restart a runtime is `unknown` until it
        #: reports again, which is the honest answer. See `capacity_state`.
        self._capacity_seen: dict[tuple[str, str], Any] = {}
        #: WHEN EACH RUNTIME WAS LAST SELECTED, as a sequence number, for the
        #: tie-break in `select`. Ordinal rather than clock time so the rule
        #: is deterministic; this process only, like everything above.
        self._last_selected: dict[str, int] = {}
        self._selections = 0

    #: How many ENDED run observations are kept. Enough to cover the moment
    #: between a process exiting and its end act being written; nothing reads
    #: an observation of a run the record has closed.
    _ENDED_KEPT = 32

    # -- runs, as this process holds them -----------------------------------

    def open_run(self, instance_id: str, run: str) -> RunObservation:
        """Say which run this process has just taken on, on which handle.

        Called by whoever recorded the run's start, as soon as it has, so the
        interval before a runtime is launched is visible as exactly that
        rather than as a run nobody holds.
        """
        with self._lock:
            inst = self._live.get(instance_id)
            obs = RunObservation(run, instance_id,
                                 inst.runtime if inst else None)
            self._runs[run] = obs
            self._run_of[instance_id] = run
            self._prune_runs()
            return obs

    def end_run(self, run: str, exit_code: int | None = None) -> None:
        """This process no longer holds that run, whatever became of it."""
        with self._lock:
            obs = self._runs.get(run)
            if obs is not None:
                obs.ended(exit_code)
                if self._run_of.get(obs.instance) == run:
                    self._run_of.pop(obs.instance, None)
            self._prune_runs()

    def run_observation(self, run: str) -> dict | None:
        """What this process has observed of one run, or None if it holds none."""
        with self._lock:
            obs = self._runs.get(run)
        return obs.snapshot() if obs is not None else None

    def run_observations(self) -> dict[str, dict]:
        """Every run this process holds or has just finished, by run."""
        with self._lock:
            held = list(self._runs.items())
        return {run: obs.snapshot() for run, obs in held}

    def halt_run(self, run: str, *, by: str, why: str) -> bool:
        """Ask the waiter of a run this process is performing to stop its
        process tree (`RunObservation.halt`). False when it holds no such
        run, or the run has already ended."""
        with self._lock:
            obs = self._runs.get(run)
        if obs is None or obs.is_ended:
            return False
        obs.halt(by, why)
        return True

    def run_marks(self) -> list[tuple]:
        """CHEAP: something that changes whenever a held run's observation
        does, for the pulse to compare. Not a status; nothing reads it as one."""
        with self._lock:
            held = list(self._runs.items())
        return sorted((run, obs.mark()) for run, obs in held)

    def _prune_runs(self) -> None:
        ended = [r for r, o in self._runs.items() if o.is_ended]
        for r in ended[:max(0, len(ended) - self._ENDED_KEPT)]:
            self._runs.pop(r, None)

    def reads(self, corpus_path: str | None,
              *, answers_at: str | None = None,
              writable: tuple[str, ...] = ()) -> None:
        """Name the corpus that dispatched workers may ask about, and where,
        and the roots beside their own scratch and project they may write."""
        self._record = corpus_path
        self._answers_at = answers_at
        self._writable = tuple(writable)

    # -- discovery ----------------------------------------------------------

    def adapter(self, runtime: str) -> RuntimeAdapter:
        ad = self._adapters.get(runtime)
        if ad is None:
            raise RuntimeNotPresent(f"unknown runtime: {runtime}")
        return ad

    def discover(self, machine: str) -> list[RuntimeInfo]:
        return [ad.discover(machine) for ad in self._adapters.values()]

    # -- selection ----------------------------------------------------------

    def eligibility(self, kind: str, requires, model: str | None = None) -> dict:
        """Can this runtime meet each named requirement -- and is that KNOWN.

        THREE ANSWERS, AND THE THIRD IS THE ONE THAT MATTERS. A requirement is
        SUPPORTED when the adapter declares the capability, UNSUPPORTED when it
        is a capability nothing here declares, and UNKNOWN when the name is not
        a declared capability at all -- a requirement Mentis has no way to judge.
        The three are never collapsed, and **UNKNOWN DOES NOT SATISFY ANYTHING**:
        an unrecognised requirement is a reason to refuse, not a reason to
        proceed hopefully.

        The evidence is the adapter's own declaration, never prose about the
        runtime. A briefing note claiming Antigravity sees a different record
        was already contradicted by Antigravity's own measured report; that is
        exactly why this reads declarations.
        """
        ad = self.adapter(kind)
        declared = {c.value for c in ad.capabilities()}
        known = {c.value for c in Capability}
        # WHO SERVES THE MODEL, asked only when a model-dependent capability
        # is actually required -- asking is a local HTTP read.
        provider = (ad.provider_of(model)
                    if model and set(requires or ()) & _tool_use.MODEL_DEPENDENT
                    else None)
        out = {}
        for name in requires or ():
            if (name in declared and provider
                    and name in _tool_use.MODEL_DEPENDENT):
                # THE RUNTIME'S DECLARATION IS NOT THE MODEL'S. A harness that
                # offers tools to a model a separate provider serves has said
                # nothing about whether that model will call them; only a
                # demonstrated call says that -- made by THIS adapter on the
                # surface it dispatches with. See `tool_use`.
                got = self.tool_use.judge(kind, provider, model, ad)
                out[name] = {"verdict": got["verdict"],
                             "scope": f"{kind}+{provider}+{model}",
                             "evidence": (f"{kind} declares {name}; whether "
                                          f"{model} served by {provider} "
                                          f"makes tool calls was judged by "
                                          f"{got.get('how', 'probe')}: "
                                          f"{got['evidence']}")}
                continue
            if name not in known:
                out[name] = {"verdict": "unknown", "scope": kind,
                             "evidence": (f"{name!r} is not a capability any "
                                          f"runtime can declare, so nothing "
                                          f"here can judge it")}
            elif name in declared:
                out[name] = {"verdict": "supported", "scope": kind,
                             "evidence": f"{kind} declares {name}"}
            else:
                out[name] = {"verdict": "unsupported", "scope": kind,
                             "evidence": f"{kind} does not declare {name}"}
        return out

    def eligible(self, kind: str, requires, model: str | None = None) -> bool:
        """Only where every hard requirement is SUPPORTED. See `eligibility`."""
        return all(r["verdict"] == "supported"
                   for r in self.eligibility(kind, requires, model).values())

    # -- capacity, as a gate and never as a score ---------------------------

    def note_capacity(self, reading) -> None:
        """Keep the newest reading per runtime and stated machine.

        Quota deltas include other executions, not expected task cost.
        No adapter reports task estimates in quota-window units today.
        """
        if reading is None or not getattr(reading, "runtime", None):
            return
        if not self._number(reading.observed_at):
            return
        key = (reading.machine_id, reading.runtime)
        with self._lock:
            held = self._capacity_seen.get(key)
            if held is None or reading.observed_at >= held.observed_at:
                self._capacity_seen[key] = reading

    @staticmethod
    def _number(value) -> bool:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value))

    def _reading(self, machine: str, kind: str):
        """Read for free; never borrow an explicitly different machine's report.

        Empty ids are the adapters' in-band observations on this Foundation.
        """
        ad = self.adapter(kind)
        try:
            free = getattr(ad, "passive_capacity", lambda m: None)(machine)
        except Exception as exc:  # noqa: BLE001
            free = None
            failure = f"{kind}: its capacity could not be read ({exc})"
        else:
            failure = None
        if (free is not None and free.runtime == kind
                and free.machine_id in ("", machine)):
            self.note_capacity(free)
        now = time.time()
        with self._lock:
            got = [self._capacity_seen.get((m, kind)) for m in (machine, "")]
        got = [r for r in got if r is not None and r.observed_at <= now]
        if not got:
            return None, failure or (f"{kind}: capacity unknown (no report for "
                                    "this machine can be read without spending "
                                    "an invocation)")
        return max(got, key=lambda r: r.observed_at), None

    @staticmethod
    def _figure(w, now: float) -> str:
        """One window as its runtime reported it: used, left, and when it
        resets. Never compared with another runtime's."""
        left = 1.0 - w.used_fraction
        out = (f"{w.group + ' ' if w.group else ''}{w.label} "
               f"{w.used_fraction:.0%} used, {left:.0%} left")
        if w.resets_at is not None:
            try:
                out += f", resets in {_span(float(w.resets_at) - now)}"
            except (TypeError, ValueError):
                pass
        return out

    def capacity_state(self, machine: str, kind: str,
                       model: str | None = None) -> tuple[str, str]:
        """`exhausted`, `available` or `unknown`, by THIS runtime's own report,
        and why. The first two facts of `capacity_view`."""
        v = self.capacity_view(machine, kind, model)
        return v["state"], v["why"]

    def capacity_view(self, machine: str, kind: str,
                      model: str | None = None) -> dict:
        """What this runtime's OWN report says about taking work now.

        `state` is `exhausted`, `available` or `unknown`, and `why` says it
        with the figures. Never a fraction compared with another runtime's:
        Claude's account windows, Codex's primary/secondary slots and
        Antigravity's per-group buckets measure different things. Claude has
        no free source, so until a run of it reports, it is `unknown` --
        which is neither full nor empty, and is said as such.

        EXHAUSTED means a live window reports 100% used. Where windows belong
        to model groups (Antigravity), the group serving `model` decides; with
        no model placed, the runtime is exhausted only if every group is.

        FOR CHOOSING AMONG RUNTIMES, a comparable reset instant:

        `expires_at` -- the reset instant of the window holding the budget
        that would otherwise go unused: the LONGEST stated window the runtime
        states a length for (Claude's seven_day, Codex's 10080-minute slot,
        Antigravity's weekly bucket). Shorter windows refill within hours and
        pace spending; it is the long window's remainder that is lost at its
        reset. None when no such window states its reset: the runtime's
        expiry is then unknown, and is said so.

        Expected consumption remains unknown: tokens and account quota deltas
        do not establish how much of a window this task will consume.
        Exact provider observations are retained in inputs.

        With windows in groups and the model not placed in one, which pool
        the work draws on is not known; every group with headroom is judged
        and the LEAST favourable stands (latest expiry), so
        no expiring capacity is claimed that the work might not draw on.
        """
        reading, why_none = self._reading(machine, kind)
        if reading is None:
            return {"state": "unknown", "why": why_none, "expires_at": None,
                    "short": [], "figures": [], "inputs": None}
        now = time.time()
        inputs = {"reading": asdict(reading), "evaluated_at": now,
                  "expected_consumption": None}
        valid = [w for w in reading.windows
                 if w.provenance == Provenance.PROVIDER_REPORTED
                 and self._number(w.used_fraction)
                 and 0 <= w.used_fraction <= 1
                 and (w.resets_at is None or
                      (self._number(w.resets_at)
                       and (not w.window_seconds or
                            w.resets_at - w.window_seconds <= reading.observed_at
                            < w.resets_at)))]
        windows = [w for w in valid
                   if w.resets_at is None or w.resets_at > now]
        if not windows:
            why = "no verified figures in the current reset period"
            return {"state": "unknown",
                    "why": f"{kind}: capacity unknown ({why})",
                    "expires_at": None, "short": [], "figures": [], "inputs": inputs}
        groups = sorted({w.group for w in reading.windows if w.group})
        if groups:
            placed = dict(reading.model_groups).get(model) if model else None
            if model and model in dict(reading.model_groups) and placed not in groups:
                return {"state": "unknown", "why": f"{kind}: model has no verified quota group",
                        "expires_at": None, "short": [], "figures": [], "inputs": inputs}
            judged = [placed] if placed in groups else groups
        else:
            judged = [None]
        pools = {g: [w for w in windows if w.group == g] for g in judged}
        full = [g for g, ws in pools.items()
                if any(w.used_fraction >= 1.0 for w in ws)]
        figures = [self._figure(w, now) for ws in pools.values() for w in ws]
        if groups:
            if full and len(full) == len(judged):
                return {"state": "exhausted",
                        "why": (f"{kind}: exhausted by its own report (group "
                                f"{', '.join(full)} at 100%)"),
                        "expires_at": None, "short": [], "figures": figures,
                    "inputs": inputs}
        elif full:
            return {"state": "exhausted",
                    "why": (f"{kind}: exhausted by its own report ("
                            + ", ".join(w.label for w in windows
                                        if w.used_fraction >= 1.0)
                            + " at 100%)"),
                    "expires_at": None, "short": [], "figures": figures,
                    "inputs": inputs}
        if not any(ws for g, ws in pools.items() if g not in full):
            return {"state": "unknown", "why": f"{kind}: no live figures for the applicable pool",
                    "expires_at": None, "short": [], "figures": figures, "inputs": inputs}
        expiries, short, lefts = [], [], []
        for g, ws in pools.items():
            if g in full and groups:
                continue
            # An expired long window leaves the budget unknown; do not
            # promote a still-live short pacing window to budget window.
            sized = [w for w in reading.windows if w.group == g
                     and self._number(w.window_seconds) and w.window_seconds > 0]
            longest = max(sized, key=lambda w: w.window_seconds) if sized else None
            live = longest in ws and longest.resets_at is not None
            expiries.append(longest.resets_at if live else None)
            lefts.append(1.0 - longest.used_fraction if live else None)
        expires_at = (None if not expiries or None in expiries
                      else max(expiries))
        # WHAT IS LEFT OF THE BUDGET WINDOW, as the runtime reports it: with
        # several pools judged, the least favourable stands here too.
        budget_left = (None if not lefts or None in lefts else min(lefts))
        if groups:
            why = (f"{kind}: available by its own report ("
                   + "; ".join(figures) + ")"
                   + (f" (group {', '.join(full)} exhausted, others not)"
                      if full else ""))
        else:
            why = (f"{kind}: available by its own report ("
                   + ", ".join(f"{w.label} {w.used_fraction:.0%}"
                               for w in windows) + ")")
        return {"state": "available", "why": why, "expires_at": expires_at,
                "budget_left": budget_left,
                "short": short, "figures": figures, "inputs": inputs}

    def usable(self, machine: str, kind: str, requires=(),
               model: str | None = None) -> str | None:
        """None when `kind` could take this work now, else why not: absent,
        ineligible, or exhausted by its own report. What a PREFERENCE -- a
        Participant's declared default -- is judged by before it binds."""
        info = next((i for i in self.discover(machine) if i.kind == kind), None)
        if info is None or not info.present:
            return f"{kind} is not present on this machine"
        requires = tuple(requires or ())
        if requires and not self.eligible(kind, requires, model):
            unmet = [n for n, r in self.eligibility(kind, requires, model).items()
                     if r["verdict"] != "supported"]
            return f"{kind} does not meet {unmet}"
        state, why = self.capacity_state(machine, kind, model)
        return why if state == "exhausted" else None

    def _by_capacity(self, machine, open_, present, model, views):
        """Which of the eligible, unexhausted runtimes takes unbound work, and
        the account of why. OWNER RULING (Turn ent-809e30307e4c): select by
        actual available capacity and reset time, preferring suitable
        capacity that would otherwise expire unused, accounting for headroom
        and expected consumption where observable; no invented score, no
        universal reserve; unknown stays unknown.

        So, in this order, with nothing weighted or summed:

          1. AVAILABLE -- its own report gives the budget window's reset
             (`expires_at`) and does not report exhaustion. Soonest reset first:
             that runtime's unused
             budget is the next to be lost. Reset instants are the one thing
             the three runtimes report that IS comparable.
          2. UNKNOWN -- no figures, or no reset for its budget window. Kept
             and said; never treated as full or as empty, so it is neither
             preferred over capacity known to be expiring nor dropped.
        Within a tier, equal resets (or none) fall back to the runtime
        selected least recently by this process, then discovery order --
        the old rule, kept only as the last tie-break.
        """
        order = {i.kind: n for n, i in enumerate(present)}
        with self._lock:
            last_selected = dict(self._last_selected)
        now = time.time()
        rows = []
        for i in open_:
            v = views.get(i.kind) or self.capacity_view(machine, i.kind, model)
            known = (v["state"] == "available" and v["expires_at"] is not None
                     and self._number(v.get("budget_left")))
            tier = 0 if known else 1
            # WHAT WOULD GO UNUSED PER HOUR LEFT: the unused share of the
            # budget window over the hours to its reset. Both figures are
            # the runtime's own; nothing is weighted, and a runtime whose
            # budget reset is unknown has no such figure and ranks after.
            pace = None
            if known:
                hours = max((v["expires_at"] - now) / 3600.0, 1.0 / 60)
                pace = v["budget_left"] / hours
            rows.append((tier, -pace if known else 0.0,
                         last_selected.get(i.kind, -1),
                         order[i.kind], i, v, pace))
        rows.sort(key=lambda r: r[:4])
        names = {0: "available", 1: "capacity or budget reset unknown"}
        account = []
        for tier, _neg, _last, _o, i, v, pace in rows:
            line = f"{i.kind}: {names[tier]}"
            if v.get("judged_model"):
                line += f" judged by {v['judged_model']}"
            if v["figures"]:
                line += " (" + "; ".join(v["figures"]) + ")"
            if tier != 1:
                line += (f"; {v['budget_left']:.0%} of its budget window "
                         f"unused with {_span(v['expires_at'] - now)} to its "
                         f"reset: {pace * 100:.2f}% of it per hour would go "
                         f"unused")
            line += "; expected task consumption unknown; only exhaustion is judged"
            account.append(line)
        tier, neg, chosen = rows[0][0], rows[0][1], rows[0][4]
        tied = [r[4].kind for r in rows[1:] if r[0] == tier and r[1] == neg]
        reason = {0: ("the largest share of its budget would otherwise expire "
                      "unused per hour left to its reset (owner, 2026-10-26: "
                      "time left and amount left, together)"),
                  1: "no eligible runtime has a verified live budget reset"}[tier]
        if tied:
            reason += (f"; tied with {tied} on that, so of those the least "
                       f"recently selected here wins")
        ranking = [{"runtime": r[4].kind, "tier": r[0],
                    "expires_at": r[5]["expires_at"],
                    "budget_left": r[5].get("budget_left"),
                    "unused_per_hour": r[6],
                    "judged_model": r[5].get("judged_model"),
                    "last_selected": r[2], "discovery_order": r[3]} for r in rows]
        return chosen, [
            "capacity ranking, each by its own report, no score: "
            + " | ".join(account),
            f"runtime {chosen.kind} chosen: {reason}"], ranking

    def select(
        self,
        *,
        machine: str,
        difficulty: str,
        runtime: str | None,
        model: str | None,
        effort: str | None,
        requires=(),
        avoid: str | None = None,
        considered=(),
    ) -> Selection:
        """Pick runtime/model/effort and record which dimensions were used.

        Capacity is consulted only for runtimes that report it, and the fact
        that a runtime reports none is itself part of the reasoning rather than
        a silently assumed zero.

        `requires` NARROWS WHO IS ELIGIBLE AND NOTHING ELSE. It is not a score,
        a ranking or a preference: a runtime either meets every hard requirement
        or is not a candidate. Having a capability is not a reason to prefer a
        runtime, and a request that needs none is not thereby restricted.

        AMONG THE ELIGIBLE, WHEN NOBODY CHOSE (owner ruling: capacity-aware,
        not Claude-first and not blind rotation). A runtime whose own report
        says it is exhausted is excluded; `unknown` is kept and said. Work
        that is review, given the author's runtime as `avoid`, goes elsewhere
        when anything else is eligible. Of what remains, the runtime whose
        unused budget is the SOONEST TO EXPIRE by its own report wins, with
        expected task consumption unknown; unknown capacity ranks after known
        (`_by_capacity`). Reset
        instants are compared, never fractions: "most headroom" would be a
        ratio between unlike things. The runtime selected least recently by
        this process is only the last tie-break, and explicitly chosen runs
        still count as use for it. Exhaustion, eligibility, explicit choices,
        preferences and session continuity all come first. `considered` is
        what the caller already weighed (a declined preference, the review
        signal), said first so `because` is the whole account.
        """
        inputs = {"machine": machine, "difficulty": difficulty,
                  "runtime": runtime, "model": model, "effort": effort,
                  "requires": list(requires or ()), "avoid": avoid,
                  "considered": list(considered or ()),
                  "evaluated_at": time.time(),
                  "last_selected": dict(self._last_selected)}
        because: list[str] = list(considered or ())
        dims: list[str] = []

        present = [i for i in self.discover(machine) if i.present]
        if not present:
            raise RuntimeNotPresent("no runtime is installed on this machine")

        requires = tuple(requires or ())
        installed = [i.kind for i in present]
        inputs["installed"] = installed
        if requires:
            # WHY EACH ONE WAS RULED OUT, KEPT FOR THE REFUSAL. A selection that
            # fails must be able to say which requirement nobody met, because
            # that is what gets recorded against the expectation and it is the
            # only thing that tells the owner what to do about it.
            judged = {i.kind: self.eligibility(i.kind, requires)
                      for i in present}
            inputs["eligibility"] = judged
            qualified = [i for i in present
                         if all(r["verdict"] == "supported"
                                for r in judged[i.kind].values())]
            if not qualified:
                raise Unsupported(
                    ", ".join(i.kind for i in present), "execution_select",
                    "no present runtime meets every requirement: "
                    + "; ".join(
                        f"{kind}: " + ", ".join(
                            f"{n} {r['verdict']}" for n, r in sorted(rs.items())
                            if r["verdict"] != "supported")
                        for kind, rs in sorted(judged.items())))
            because.append(
                f"required {list(requires)}; eligible "
                f"{[i.kind for i in qualified]} of present "
                f"{[i.kind for i in present]}; a capability is a filter, not a "
                f"preference")
            dims.append("required_capabilities")
            present = qualified

        if model and not runtime:
            # AN EXPLICIT MODEL IS A CONSTRAINT ON WHO CAN RUN IT, NOT A LABEL.
            # Without this, a model named with no runtime went to the first
            # present runtime whatever it could serve -- a local model handed to
            # a hosted harness, which then either fails or runs its own default.
            # So it narrows exactly as `requires` does: a runtime whose own
            # catalogue offers the model is eligible, one that cannot list its
            # models cannot be KNOWN to serve it and is not, and none eligible
            # is a refusal. First present among the eligible, as ever.
            offered = []
            for i in present:
                ad_i = self.adapter(i.kind)
                if Capability.LIST_MODELS not in ad_i.capabilities():
                    continue
                try:
                    slugs = {m.slug for m in ad_i.list_models()}
                except Exception:
                    continue
                if model in slugs:
                    offered.append(i)
            if not offered:
                raise Unsupported(
                    ", ".join(i.kind for i in present), "execution_select",
                    f"model {model!r} was requested explicitly and no eligible "
                    f"runtime's catalogue offers it; refusing rather than "
                    f"running a different model")
            because.append(
                f"model {model!r} is offered by "
                f"{[i.kind for i in offered]} of eligible "
                f"{[i.kind for i in present]}; an explicit model narrows who "
                f"may run it")
            dims.append("requested_model_placement")
            present = offered

        if runtime:
            chosen = next((i for i in present if i.kind == runtime), None)
            if chosen is None:
                # WHICH OF THE TWO REFUSALS THIS IS. A runtime that is absent
                # and one that is installed but cannot meet the requirements are
                # different problems with different answers, and reporting the
                # second as the first sends the owner to install something they
                # already have. Either way it is refused: an explicit runtime is
                # a constraint, and quietly substituting another would be the
                # one thing selection must never do.
                if runtime in installed:
                    raise Unsupported(
                        runtime, "execution_select",
                        "it is present but does not meet every requirement: "
                        + ", ".join(
                            f"{n} {r['verdict']} ({r['evidence']})"
                            for n, r in sorted(
                                self.eligibility(runtime, requires).items())
                            if r["verdict"] != "supported"))
                raise RuntimeNotPresent(f"{runtime} is not present on this machine")
            because.append(f"runtime {runtime} was requested explicitly")
            # SAID, NEVER ACTED ON: an explicit runtime is not substituted.
            view = self.capacity_view(machine, runtime, model)
            inputs["capacity"] = {runtime: view}
            state, why = view["state"], view["why"]
            if state == "exhausted":
                because.append(f"{why}; run as chosen, not substituted")
            excluded: tuple[str, ...] = ()
        else:
            # EACH RUNTIME JUDGED BY THE POOL THE WORK WOULD DRAW ON: the
            # model named, or the one selection would pick there
            # (`would_pick`); with neither, every pool, as before.
            views = {}
            for i in present:
                placed = model or self.would_pick(
                    machine, i.kind,
                    effort or self._effort_for(self.adapter(i.kind), difficulty))
                views[i.kind] = self.capacity_view(machine, i.kind, placed)
                if placed and not model:
                    views[i.kind]["judged_model"] = placed
            inputs["capacity"] = views
            states = {k: (v["state"], v["why"]) for k, v in views.items()}
            because.append("capacity, each by its own report: " + "; ".join(
                why for _, why in states.values()))
            dims.append("capacity_gate")
            open_ = [i for i in present if states[i.kind][0] != "exhausted"]
            out = [i.kind for i in present if i not in open_]
            # THE OWNER'S GROUP RULE: a runtime whose models it cannot place
            # is not used for unbound work (`unplaced`).
            unplaced = {i.kind: self.unplaced(
                machine, i.kind,
                effort or self._effort_for(self.adapter(i.kind), difficulty))
                for i in open_}
            gone = [k for k, w in unplaced.items() if w]
            if gone:
                because.extend(unplaced[k] for k in gone)
                open_ = [i for i in open_ if i.kind not in gone]
            if not open_:
                raise Unsupported(
                    ", ".join(i.kind for i in present), "execution_select",
                    "every eligible runtime reports its capacity exhausted"
                    + (" or cannot place its models in the groups the owner "
                       "allows" if gone else "") + ": "
                    + "; ".join(unplaced.get(k) or why
                                for k, (_, why) in states.items()))
            if out:
                because.append(f"excluded as exhausted: {out}")
            if gone:
                because.append(f"excluded as unplaced: {gone}")
            if avoid:
                others = [i for i in open_ if i.kind != avoid]
                if others:
                    because.append(
                        f"review: the reviewed work ran on {avoid}; it is "
                        f"avoided so the review runs on a different runtime")
                    out = out + [avoid]
                    open_ = others
                else:
                    because.append(
                        f"review: the reviewed work ran on {avoid} and no "
                        f"other runtime is eligible and available; "
                        f"independence by runtime was not achievable")
                dims.append("review_independence")
            excluded = tuple(out)
            inputs["candidates"] = [i.kind for i in open_]
            chosen, account, ranking = self._by_capacity(machine, open_, present,
                                                         model, views)
            inputs["ranking"] = ranking
            because.extend(account)
            dims.append("capacity_expiry")
        inputs["eligible"] = [i.kind for i in present]
        inputs["excluded"] = list(excluded)
        dims.append("runtime_presence")
        with self._lock:
            self._selections += 1
            self._last_selected[chosen.kind] = self._selections

        ad = self.adapter(chosen.kind)

        # Effort: each runtime's own vocabulary, never a shared scale.
        req_effort = effort
        if req_effort is None:
            req_effort = self._effort_for(ad, difficulty)
            if req_effort:
                because.append(
                    f"effort {req_effort!r} from difficulty {difficulty!r} using "
                    f"{chosen.kind}'s own effort vocabulary"
                )
                dims.append("difficulty")
        else:
            because.append(f"effort {req_effort!r} was requested explicitly")
            dims.append("requested_effort")

        chosen_model = model
        if chosen_model is None and Capability.LIST_MODELS in ad.capabilities():
            # THE CATALOGUE IS READ ONLY WHERE IT CAN DECIDE SOMETHING. Every
            # other runtime gets "no model chosen" whatever its list says, and
            # reading it anyway cost Claude eleven CLI launches per selection
            # -- measured: ~1,400 launches across the test suite, which
            # tripled its running time.
            # NOT the only catalogue read in selection -- see the model
            # PLACEMENT block above, which asks every eligible runtime what it
            # offers when a model is named with no runtime. This guard governs
            # THIS block: choosing a model for an already-chosen runtime.
            if not self._catalogue_decides(ad, req_effort):
                because.append(self._NO_MODEL)
            else:
                # A catalogue that cannot be read does not stop the work: no
                # model is chosen, the runtime's own default runs, and the
                # selection says why.
                try:
                    models = ad.list_models()
                except Exception as exc:  # noqa: BLE001
                    models = []
                    because.append(f"{chosen.kind}'s model catalogue could not be "
                                   f"read ({exc}); its own default model is used")
                # A RUNTIME'S CAPACITY WAS JUDGED WITH NO MODEL PLACED: it is
                # open while any of its quota groups is. The model picked here
                # places the work in one group, so a model whose own group
                # reports exhaustion is not picked -- otherwise the work is
                # dispatched into the exhausted pool the gate above avoided.
                spent = [m.slug for m in models if self.capacity_view(
                    machine, chosen.kind, m.slug)["state"] == "exhausted"]
                if spent:
                    models = [m for m in models if m.slug not in spent]
                    because.append(f"models whose own quota group reports "
                                   f"exhaustion are not picked: {spent}")
                # ONLY THE GROUPS THE OWNER ALLOWS, IN THEIR ORDER
                # (`_models_in_owners_groups`): the first model with the
                # asked effort is then the preferred group's.
                had = bool(models)
                models, notes = self._models_in_owners_groups(
                    machine, ad, models)
                because.extend(notes)
                if had and not models:
                    why_un = self.unplaced(machine, chosen.kind, req_effort)
                    if why_un:
                        raise Unsupported(
                            chosen.kind, "execution_select",
                            why_un + "; refusing rather than running its "
                                     "default model")
                if models:
                    chosen_model, note = self._pick_model(ad, models, req_effort)
                    because.append(note)
                    dims.append("model_catalogue")
        elif chosen_model:
            because.append(f"model {chosen_model!r} was requested explicitly")
            dims.append("requested_model")

        # THE REQUIREMENTS ARE ASKED OF THE MODEL TOO, ONCE THERE IS ONE. The
        # runtime filter above judged the harness; a model a separate provider
        # serves has to have demonstrated a model-dependent capability itself.
        # Refused, never substituted: the model is a constraint where it was
        # named, and Mentis did not pick it where it was not.
        if requires and chosen_model:
            judged_m = self.eligibility(chosen.kind, requires, chosen_model)
            unmet = {n: r for n, r in judged_m.items()
                     if r["verdict"] != "supported"}
            if unmet:
                raise Unsupported(
                    chosen.kind, "execution_select",
                    f"model {chosen_model!r} does not meet every requirement "
                    f"for this work: " + "; ".join(
                        f"{n} {r['verdict']} ({r['evidence']})"
                        for n, r in sorted(unmet.items()))
                    + ". Refusing rather than dispatching tool-dependent work "
                      "to a model that has not shown it can call tools.")
            model_level = {n: r for n, r in judged_m.items()
                           if r["scope"] != chosen.kind}
            if model_level:
                because.append("demonstrated at model level: " + "; ".join(
                    f"{n} ({r['evidence']})"
                    for n, r in sorted(model_level.items())))
                dims.append("model_capability")

        # A LOCAL MODEL GETS ONLY THE EFFORT SOMEBODY ASKED FOR. Difficulty
        # words were never sent to one -- nothing measured says a local
        # provider honours them, and Ollama was measured ignoring `low` and
        # `minimal` -- so recording `medium` here claimed a request that never
        # crossed. An explicit effort is different: it is the owner's
        # constraint, and it is sent as asked.
        served_by = (ad.provider_of(chosen_model)
                     if effort is None and req_effort is not None
                     and chosen_model else None)
        if served_by:
            because[:] = [b for b in because
                          if not b.startswith(f"effort {req_effort!r} from")]
            if "difficulty" in dims:
                dims.remove("difficulty")
            req_effort = None
            because.append(
                f"no effort derived for a model served by {served_by}: only an "
                f"explicitly requested effort is sent to a local provider")

        if runtime and Capability.OBSERVE_CAPACITY not in ad.capabilities():
            because.append(
                f"{chosen.kind} reports no capacity, so no capacity dimension "
                f"influenced this selection"
            )
        elif runtime:
            because.append(
                f"{chosen.kind} was chosen explicitly, so capacity did not "
                f"decide this selection"
            )

        # Antigravity fuses effort into the slug. Sending both is a hard error,
        # so the request is normalised here rather than in the adapter guessing.
        if chosen_model and ad.kind == "antigravity":
            from .runtimes.antigravity import AntigravityAdapter as _AG

            if _AG._slug_carries_effort(chosen_model):
                because.append(
                    "effort is fused into the antigravity model slug; it is not "
                    "sent as a separate flag"
                )

        return Selection(
            runtime=chosen.kind,
            model=chosen_model,
            requested_effort=req_effort,
            because=tuple(because),
            dimensions_used=tuple(dims),
            excluded=excluded,
            inputs=inputs,
        )

    @staticmethod
    def _effort_for(ad: RuntimeAdapter, difficulty: str) -> str | None:
        """Map difficulty onto whatever effort words this runtime actually has."""
        if Capability.REQUEST_EFFORT not in ad.capabilities():
            return None
        table = {"trivial": "low", "ordinary": "medium", "hard": "high"}
        return table.get(difficulty, "medium")

    _NO_MODEL = (
        "no model chosen: Mentis has no evidence ranking this runtime's models "
        "by capability or cost, so the runtime's own default is used rather "
        "than guessing"
    )

    @staticmethod
    def _catalogue_decides(ad, effort) -> bool:
        """Whether this runtime's catalogue can change the choice: only where
        effort is fused into the slug and an effort was asked for. The one
        rule `_pick_model` acts on, so the two cannot drift apart.

        SCOPE, SAID PLAINLY: this decides whether to read a catalogue in order
        to PICK a model for a runtime already chosen. It does not govern the
        placement read, which must ask every eligible runtime what it offers
        before it can say which runtime serves a named model.

        Keyed on the runtime's name, which this codebase otherwise refuses to
        reason from -- there is no declaration for "fuses effort into the
        slug". If Antigravity stops fusing, or a fourth runtime starts, this
        is silently wrong and the only symptom is a model quietly not chosen.
        """
        return ad.kind == "antigravity" and bool(effort)

    @staticmethod
    def _pick_model(ad, models, effort) -> tuple[str | None, str]:
        """Choose a model only where not choosing one would be wrong.

        Mentis has no evidence on which to rank models by capability or cost, so
        it does not rank them. An earlier version took the first entry in the
        catalogue and thereby selected the most capable model for trivial work --
        the opposite of what a selector should do, and expensive.

        Where the runtime fuses effort into the slug, a choice is unavoidable,
        because choosing an effort IS choosing a model.
        """
        if Foundation._catalogue_decides(ad, effort):
            for m in models:
                if m.default_effort == effort:
                    return m.slug, (
                        f"model {m.slug!r} chosen because this runtime fuses effort "
                        f"into the slug, so requesting {effort!r} requires picking one"
                    )
        return None, Foundation._NO_MODEL

    def _models_in_owners_groups(self, machine, ad, models) -> tuple[list, list[str]]:
        """The catalogue narrowed and ordered by the quota groups the owner
        allows this runtime to draw on (`ad.groups_in_order`), with the
        account of it.

        OWNER RULING (2026-10-26, from the CLI): Mentis draws only on
        Antigravity's Gemini quota -- Argon while its group has headroom,
        Flash otherwise -- and never on its Claude or GPT capacity. The
        adapter declares the groups in order of preference, by the names agy
        reports them under; a model is placed in a group by the runtime's own
        capacity report (`CapacityReading.model_groups`), never by its slug.

        A runtime that declares no groups, or whose report places no model,
        is left exactly as it was: nothing is narrowed on a guess, and the
        account says so.
        """
        allowed = tuple(getattr(ad, "groups_in_order", ()) or ())
        if not allowed or not models:
            return list(models), []
        reading, why = self._reading(machine, ad.kind)
        placed = dict(reading.model_groups) if reading else {}
        if not placed:
            # NOTHING OUTSIDE THE RULE RUNS. With no report placing its
            # models, the adapter's slug families stand in for the groups --
            # the same rule, the same order, said as such -- and a model in
            # none of them is not picked. With no families either, nothing
            # is picked and the runtime is not used (`unplaced`): its own
            # default model could be one the owner excluded (found by
            # review).
            fams = tuple(getattr(ad, "families_in_order", ()) or ())
            why = why or "its report places no model in a group"
            if not fams:
                return [], [
                    f"{ad.kind}'s models could not be placed in quota groups "
                    f"({why}); the owner allows only {', '.join(allowed)}, so "
                    f"no model is picked and {ad.kind} is not used until its "
                    f"report can be read"]
            rank = {f: n for n, f in enumerate(fams)}
            fam_of = {m.slug: next((f for f in fams if m.slug.startswith(f)),
                                   None) for m in models}
            kept = [m for m in models if fam_of[m.slug] is not None]
            dropped = [m.slug for m in models if fam_of[m.slug] is None]
            kept.sort(key=lambda m: rank[fam_of[m.slug]])
            notes = [f"{ad.kind}'s models could not be placed in quota groups "
                     f"({why}), so the owner's rule is applied by slug family "
                     f"({', '.join(fams)}, in that order): "
                     f"{[m.slug for m in kept]}"]
            if dropped:
                notes.append("models in none of those families are not picked "
                             f"(owner, 2026-10-26): {dropped}")
            return kept, notes
        rank = {g: n for n, g in enumerate(allowed)}
        kept = [m for m in models if placed.get(m.slug) in rank]
        dropped = [m.slug for m in models if m.slug not in {k.slug for k in kept}]
        kept.sort(key=lambda m: rank[placed[m.slug]])
        notes = [f"models in quota groups the owner allows ({', '.join(allowed)}"
                 f", in that order): {[m.slug for m in kept]}"]
        if dropped:
            notes.append("models outside those groups are not picked (owner, "
                         f"2026-10-26): {dropped}")
        return kept, notes

    def unplaced(self, machine, kind, effort=None) -> str | None:
        """Why this runtime may not take unbound work by the owner's group
        rule: it declares `groups_in_order`, its catalogue lists models, and
        none of them can be picked -- neither placed in an allowed group by
        its own report nor in a declared slug family. None otherwise, None
        for a runtime with no such rule, and None where the catalogue is not
        read for this runtime (`_catalogue_decides`)."""
        ad = self.adapter(kind)
        allowed = tuple(getattr(ad, "groups_in_order", ()) or ())
        if not allowed or not self._catalogue_decides(ad, effort) \
                or Capability.LIST_MODELS not in ad.capabilities():
            return None
        try:
            models = list(ad.list_models())
        except Exception:  # noqa: BLE001
            return None
        if not models:
            return None
        kept, _ = self._models_in_owners_groups(machine, ad, models)
        if kept:
            return None
        return (f"{kind}: none of its models can be placed in the quota groups "
                f"the owner allows ({', '.join(allowed)}) or their slug "
                f"families; not used until its report can be read")

    def would_pick(self, machine, kind, effort) -> str | None:
        """The model `select` WOULD pick on this runtime for this effort, read
        the same way `select` picks it -- the catalogue narrowed to models
        whose own quota group has headroom and to the groups the owner allows,
        in the owner's order -- or None where the runtime's default would run.

        Asked before a runtime is ranked, so its capacity is judged by the
        pool the work would actually draw on and not by the emptiest group it
        has (owner, 2026-10-26: Antigravity's untouched Claude/GPT group
        made it read as the fullest runtime while its Gemini pools emptied).
        """
        ad = self.adapter(kind)
        if not self._catalogue_decides(ad, effort) \
                or Capability.LIST_MODELS not in ad.capabilities():
            return None
        try:
            models = list(ad.list_models())
        except Exception:  # noqa: BLE001
            return None
        models = [m for m in models if self.capacity_view(
            machine, kind, m.slug)["state"] != "exhausted"]
        models, _ = self._models_in_owners_groups(machine, ad, models)
        picked, _ = self._pick_model(ad, models, effort)
        return picked

    # -- lifecycle ----------------------------------------------------------

    def authorise_for(self, instance_id: str, authority: dict | None) -> None:
        """Say why this execution was dispatched, before it is performed.

        The grant is minted at perform and this is what it reads. Kept apart
        from `register` because an instance may be REUSED, and a reused instance
        carries the previous run's reason until this replaces it: authority
        belongs to the run, not to the session.
        """
        with self._lock:
            if authority is None:
                self._authority.pop(instance_id, None)
            else:
                self._authority[instance_id] = dict(authority)

    def register(self, inst: Instance, *, deliver: str | None = None,
                 claimed: bool = False) -> Instance:
        """Take ownership of an instance, optionally already claimed.

        `claimed` closes a window rather than adding a feature: registering
        and then claiming were two steps, and a second caller could claim in
        between -- reproduced, with both callers holding the same instance.
        """
        with self._lock:
            if claimed:
                inst = replace(inst, liveness=Liveness.BUSY)
            self._live[inst.instance_id] = inst
            self._deliver[inst.instance_id] = deliver
        return inst

    # -- what a worker may ask, and for how long ----------------------------

    def _grant(self, instance_id: str, corpus: str) -> str:
        """Authorise one execution to ask the four reads about one corpus.

        AN OPAQUE STRING AND NOT AN IDENTITY. There are no users here, no
        roles and nothing to look anybody up in. A grant says one thing --
        this execution may ask these four questions about this corpus --
        and holding it is the whole of the claim. That is the smallest
        thing that can be checked, and checking it is the point: a worker
        must not be authorised by WHERE it is calling from.

        LIFETIME IS AN OBSERVED FACT, NOT A CLOCK: the run it authorises.
        Minted when a perform begins and revoked when it ends, because that
        is when a worker exists to use it. No expiry is chosen, and none is
        needed. It used to last as long as the instance was live in this
        process, which meant an instance kept dormant for reuse carried a
        usable capability with nothing running to use it.
        """
        token = secrets.token_urlsafe(32)
        # WHAT THE WORK IS, TRAVELLING WITH THE PERMISSION TO DO IT. The grant
        # already said which execution and which corpus; it now also carries WHY
        # the execution was dispatched -- its scope, the expectation it is
        # carrying, and where. That is what lets the server derive an actor, a
        # cause and a provenance instead of believing a worker's claim about any
        # of them, and it is why none of those is ever a parameter a worker
        # supplies. Authority is a property of the dispatch, not of the
        # Participant, its alias or its Persona.
        authority = dict(self._authority.get(instance_id) or {})
        self._grants[token] = {"instance": instance_id, "corpus": corpus,
                               "scope": authority.get("scope") or "worker",
                               "operations": authority.get("operations"),
                               "expectation": authority.get("expectation"),
                               "conversation": authority.get("conversation"),
                               "participant": authority.get("participant"),
                               "runtime": authority.get("runtime"),
                               # THE PERSONA IT WEARS, for what it records.
                               "persona": authority.get("persona"),
                               # WHAT THIS RUN WAS TOLD, by source id, as
                               # composed for it (`dispatch._dispatch`).
                               "delivered": list(authority.get("delivered")
                                                 or ())}
        self._granted_to[instance_id] = token
        return token

    def grant_session(self, corpus: str, *, runtime: str,
                      participant: str,
                      execution: str | None = None) -> tuple[str, str]:
        """A grant for a session somebody started by hand: (token, execution).

        THE SAME TABLE, THE SAME DOOR. A dispatched run's grant is minted at
        perform from why it was dispatched; a hand-started session has no
        dispatch, so its grant names its own new execution, the runtime it was
        registered for and `SESSION_SCOPE`, and carries no expectation and no
        Conversation. `/api/worker` reads it exactly as it reads any other.

        LIFETIME: until `end_session` or this process ends. In memory like
        every grant, so a restart drops it and the session asks again --
        naming `execution`, the one it already is, so what it opened stays
        its own (`_where` reads ownership by execution). Whether it may name
        that execution is decided by the caller, from the record.
        """
        from mentis.worker import AUTHORITY, SESSION_SCOPE
        token = secrets.token_urlsafe(32)
        # A uuid like every instance id, because provenance keeps only its
        # first eight characters (`written_by`); a shared prefix would make
        # every session's writes read alike. That it is a session is said by
        # the grant's scope and the `manual-session-started` act.
        execution = execution or str(uuid.uuid4())
        with self._lock:
            self._grants[token] = {"instance": execution, "corpus": corpus,
                                   "scope": SESSION_SCOPE,
                                   # WHAT A REQUEST ADDRESSED TO NOBODY -- the
                                   # one @Caretaker carries -- is granted.
                                   "operations": list(AUTHORITY),
                                   "expectation": None, "conversation": None,
                                   "participant": participant,
                                   "runtime": runtime, "delivered": []}
        return token, execution

    def session_held(self, execution: str, corpus: str) -> bool:
        """Whether a live session grant already names this execution."""
        from mentis.worker import SESSION_SCOPE
        with self._lock:
            return any(g["instance"] == execution and g["corpus"] == corpus
                       and g.get("scope") == SESSION_SCOPE
                       for g in self._grants.values())

    def end_session(self, token: str | None, corpus: str) -> dict | None:
        """Revoke a hand-started session's grant. The grant it was, or None.

        Only a session grant: a dispatched run's grant ends with its run.
        """
        from mentis.worker import SESSION_SCOPE
        with self._lock:
            grant = self._grants.get(token or "")
            if (grant is None or grant["corpus"] != corpus
                    or grant.get("scope") != SESSION_SCOPE):
                return None
            self._grants.pop(token, None)
            return dict(grant)

    def grant_of(self, instance_id: str) -> str | None:
        """The grant this execution was started with, if it has one."""
        return self._granted_to.get(instance_id)

    def _permits_for(self, instance_id: str) -> tuple[str, ...]:
        """The operations this run may perform, from why it was dispatched.

        ONE DECISION, READ IN TWO PLACES. `worker.permitted` maps a scope to a
        set of operation names; the HTTP door uses it to ADMIT a call and this
        uses it to decide what the run is SHOWN. Deriving both from the same
        function is what stops the visible surface and the real authority
        drifting apart -- which they did, and an ordinary worker was shown
        organising tools it could never have used.
        """
        from mentis.worker import permitted
        authority = self._authority.get(instance_id) or {}
        return tuple(permitted(authority.get("scope"),
                               authority.get("operations")))

    def authorises(self, token: str | None, corpus: str) -> str | None:
        """The execution this token authorises FOR THIS CORPUS, or None.

        Scope is checked here rather than trusted from the caller: a grant
        is for the record its execution was dispatched from, so presenting
        it against a different one is refused rather than quietly served.
        """
        grant = self.grant_for(token, corpus)
        return grant["instance"] if grant else None

    def grant_for(self, token: str | None, corpus: str) -> dict | None:
        """The whole grant this token carries for this corpus, or None.

        `authorises` answers "may this ask at all"; this answers "what was it
        dispatched to do", which is a different question and the one an
        operation beyond the four reads has to ask. A copy, so nothing a caller
        does to it can reach the live bookkeeping.
        """
        grant = self._grants.get(token or "")
        if grant is None or grant["corpus"] != corpus:
            return None
        return dict(grant)

    def live_now(self) -> list[tuple[str, str]]:
        """What this process is running, as (instance, liveness) pairs.

        CHEAP ON PURPOSE. This is the in-memory set, which is what `live`
        means: an execution this process started and has not finished with.
        `agents_list` answers a different question -- it reads the whole
        instance history off disk and verifies each record against the
        machine -- and something asked repeatedly must not do that. Found by
        review: the pulse was re-parsing every instance observation ever
        written, fifty times a minute per open tab, and would have grown
        heavier for the life of the corpus.
        """
        with self._lock:
            return sorted((i, inst.liveness.value)
                          for i, inst in self._live.items())

    def known(self, instance_id: str) -> Instance | None:
        return self._live.get(instance_id)

    #: What may be claimed for new work: never STARTING-but-claimed, never
    #: one a perform is already inside, never one that ended badly.
    CLAIMABLE = (Liveness.STARTING, Liveness.FINISHED)

    def claim(self, instance_id: str) -> Instance | None:
        """Take this instance for one piece of work, or refuse. Indivisible.

        THE MISSING INTERVAL. `FINISHED` says the last call returned, not
        that the session is free: two dispatches reading that state could
        both decide to continue the same conversation. BUSY is the interval
        between choosing an instance and finishing with it, and because the
        transition happens under one lock only one caller can hold it.

        A claimed instance must be performed or released. It is not a lease
        and it does not time out, because a timeout would be a guess about
        a runtime this process can no longer see.
        """
        with self._lock:
            inst = self._live.get(instance_id)
            if inst is None or inst.liveness not in self.CLAIMABLE:
                return None
            claimed = replace(inst, liveness=Liveness.BUSY)
            self._live[instance_id] = claimed
            return claimed

    def was_released(self, instance_id: str) -> bool:
        """Has this process relinquished that handle. Asked, not assumed."""
        with self._lock:
            return instance_id in self._released

    def mark_released(self, instance_id: str) -> None:
        """Record a relinquishment made from the RECORD rather than a handle.

        FOUND BY REVIEW. Releasing a session nothing here owned wrote the
        durable GONE but told this process nothing -- so an adoption
        already holding the older record sailed past its final check and
        took the session anyway, in the same process that had just let it
        go.
        """
        with self._lock:
            self._released.add(instance_id)

    def unclaim(self, instance_id: str) -> Instance | None:
        """Give a reservation back WITHOUT relinquishing the session.

        The difference matters: `release` says nobody will continue this
        session and discards what it can, and that is far too strong an
        answer to `I could not tell whether it is continuable`. This just
        puts the handle down again.
        """
        with self._lock:
            inst = self._live.get(instance_id)
            if inst is None or inst.liveness is not Liveness.BUSY:
                return inst
            back = replace(inst, liveness=(Liveness.FINISHED
                                          if inst.session_ref
                                          else Liveness.STARTING))
            self._live[instance_id] = back
            return back

    def _scratch_of(self, instance_id: str) -> str | None:
        """This execution's private scratch path, or None with no record."""
        if not self._record:
            return None
        return str(_scratch.path_for(self._record, instance_id))

    def resume_eligibility(self, inst: Instance):
        """Ask the runtime whether that session can still be continued.

        Asked about the directory the run is STARTED in, which is its scratch
        where it has one: a runtime that resumes per directory recorded the
        session there, not in the project.
        """
        return self.adapter(inst.runtime).resume_eligibility(
            session_ref=inst.session_ref,
            workspace=self._scratch_of(inst.instance_id) or inst.workspace,
            runtime_home=inst.runtime_home)

    def answer_once(self, prompt: str, *, runtime: str,
                    model: str | None = None, effort: str | None = None,
                    deadline_s: int | None = 180, live_key=None,
                    cancel_event=None, access=(), read_only=(), files="",
                    stage=None, collect=None):
        """ONE ANSWER, AND NOTHING LEFT BEHIND. For Scratch (`mentis.scratch_store`).

        Not `perform`. There is no Instance, no session to resume, no
        registration in `_live`, no authority and no observation: a Scratch
        question is not work, so nothing here can make it look like work. The
        run is given a grant scoped `transient-read` -- the record reads, the
        source reads and `read_artifact`, none of which writes anything for
        it (`mentis.worker.permitted`) -- for exactly as long as it
        runs, and a private scratch directory that is discarded when it ends.
        The adapter is asked to run with no built-in action or filesystem tools and no saved
        session, and an adapter that cannot promise that is refused rather
        than used.

        `access` is the folders the owner SELECTED for this question. With
        none, the run has no built-in tools at all, as above. With some, it
        is given file tools confined to exactly those folders -- and only on
        an adapter that enforces that (`folder_bounded`); any other is
        refused here, before launch, with what it cannot enforce. The grant
        is the same `transient-read`: file access is not coordination.
        `read_only` names the folders of `access` it must not change, and
        `files` is "read" when the run writes nothing at all (see
        `Invocation.files`).

        `stage(scratch)` runs before the runtime starts and `collect(scratch,
        res)` after it returns -- both while the private scratch still exists,
        which is how Scratch copies a file in, and copies a file out or builds
        a ZIP, without the runtime ever being given the folders involved.

        Returns the adapter's `RunResult`. `live_key` names the run while it
        is going (`answering_now`), so a restart can tell an answer nobody is
        producing from one that is still coming.
        """
        from mentis.worker import TRANSIENT_SCOPE, permitted
        ad = self.adapter(runtime)
        if not getattr(ad, "transient_ok", False):
            raise Unsupported(
                runtime, "a transient read-only answer",
                "no built-in tools and no saved session cannot be promised, "
                "so it is not used for Scratch")
        access = tuple(access or ())
        files = files or ("write" if access else "")
        if files not in ("", "read", "write"):
            raise ValueError(f"files is '', 'read' or 'write', not {files!r}")
        if (access or files) and not getattr(ad, "folder_bounded", False):
            raise Unsupported(
                runtime, "Scratch file work in selected folders",
                getattr(ad, "folder_bounds_why", "")
                or "it does not confine file access to selected folders")
        cancel_event = cancel_event or threading.Event()
        if cancel_event.is_set():
            raise RuntimeError("Scratch answer cancelled")
        tid = "transient-" + secrets.token_hex(8)
        token = secrets.token_urlsafe(32)
        scratch = (_scratch.provision(self._record, tid, runtime=runtime)
                   if self._record else None)
        with self._lock:
            self._grants[token] = {"instance": tid, "corpus": self._record,
                                   "scope": TRANSIENT_SCOPE,
                                   "operations": (), "expectation": None,
                                   "conversation": None, "participant": None,
                                   "runtime": runtime}
            if live_key is not None:
                self._answering[live_key] = tid
        from mentis.worker import take_deleted_served
        try:
            if stage is not None:
                if not scratch:
                    raise Unsupported(
                        runtime, "Scratch files copied in or out",
                        "no private scratch: no record is attached")
                stage(scratch)
            res = ad.run(Invocation(
                workspace=scratch or ".", prompt=prompt, model=model,
                effort=effort, record=self._record,
                answers_at=self._answers_at, capability=token,
                # THROUGH `permitted`, not a literal. What a Quick Ask is
                # SHOWN and what the door ADMITS have to come from one
                # place, or granting it something later would admit it at
                # the door while `tools/list` never offered it.
                permits=permitted(TRANSIENT_SCOPE),
                scratch=scratch, timeout_s=deadline_s, transient=True,
                access=access, read_only=tuple(read_only or ()),
                files=files, cancel_event=cancel_event))
            if collect is not None and scratch:
                collect(scratch, res)
            # WHAT DELETED MATERIAL THIS RUN WAS SERVED, from the door that
            # served it (`mentis.worker`, "deleted material a Quick Ask was
            # served"), so the answer can say so whatever the agent wrote.
            res.deleted_material = take_deleted_served(tid)
            return res
        finally:
            take_deleted_served(tid)
            with self._lock:
                self._grants.pop(token, None)
                if live_key is not None:
                    self._answering.pop(live_key, None)
            if scratch:
                _scratch.discard(self._record, tid)
                forget = getattr(ad, "forget_transient", None)
                if forget:
                    try:
                        forget(scratch)
                    except Exception:                     # noqa: BLE001
                        pass

    def answering_now(self) -> set:
        """The `live_key`s of Scratch answers this process is producing."""
        with self._lock:
            return set(self._answering)

    def perform(self, instance_id: str, work: str, *,
                deadline_s: int | None = ...,
                run: str | None = None) -> tuple[WorkOutcome, Instance]:
        """Perform one run on this handle.

        `run` names the run -- its `execution-started` act -- where somebody
        recorded one. What this process observes while performing it is kept
        against that run, not against the handle. A caller that recorded no
        start (a probe, the CLI) gets an observation nobody can look up,
        which is the truth: there is no run in the record to attach it to.
        """
        with self._lock:
            # ONE RUN AT A TIME, decided indivisibly. A caller that already
            # claimed this instance may run it; a caller arriving while a
            # run is in flight may not, and neither may one whose instance
            # has been released.
            if instance_id in self._inflight:
                raise RuntimeNotPresent(
                    f"instance {instance_id} is already performing")
            inst = self._live.get(instance_id)
            if inst is None:
                raise RuntimeNotPresent(
                    f"instance {instance_id} is not live here")
            if inst.liveness is not Liveness.BUSY:
                inst = replace(inst, liveness=Liveness.BUSY)
                self._live[instance_id] = inst
            self._inflight.add(instance_id)
            # A GRANT LASTS AS LONG AS THE WORK IT AUTHORISES, and no
            # longer. It used to be minted when an instance was registered
            # and revoked only at release -- so an instance kept dormant for
            # reuse carried a usable worker capability between runs, with
            # nothing running to use it. Minted here, revoked in `finally`,
            # which needs no timeout because the run's own end is the fact.
            if self._record:
                self._grant(instance_id, self._record)
            obs = self._runs.get(run) if run else None
            if obs is None:
                obs = RunObservation(run, instance_id, inst.runtime)
                if run:
                    self._runs[run] = obs
                    self._run_of[instance_id] = run
            obs.performing()
            # ONE RUN IN FLIGHT PER HANDLE (`_inflight` above), so the handle
            # names the observation for as long as the run is inside it.
            self._performing[instance_id] = obs
        if deadline_s is ...:
            deadline_s = self.deadline_s
        exit_code = None
        try:
            outcome, updated = self._perform(instance_id, inst, work,
                                             deadline_s)
            exit_code = outcome.exit_code
            return outcome, updated
        except BaseException:
            # A RESERVATION MUST NOT OUTLIVE ITS RUN. An adapter that threw
            # left the instance BUSY with nothing inside it, so no later
            # work could ever claim that session again. The invocation
            # ended badly, which is what FAILED means.
            with self._lock:
                held = self._live.get(instance_id)
                if held is not None and instance_id not in self._released:
                    self._live[instance_id] = replace(
                        held, liveness=Liveness.FAILED,
                        finished_at=time.time())
            raise
        finally:
            # THE RUN'S OWN END, as this process saw it: the call returned
            # (or raised). What that means for the record is the recorder's
            # to write; this only stops the run reading as in progress here.
            obs.ended(exit_code)
            with self._lock:
                self._performing.pop(instance_id, None)
                if self._run_of.get(instance_id) == obs.run:
                    self._run_of.pop(instance_id, None)
                self._prune_runs()
                self._inflight.discard(instance_id)
                spent = self._granted_to.pop(instance_id, None)
                if spent:
                    self._grants.pop(spent, None)
                # AND THE REASON GOES WITH IT. Authority is the run's, so a
                # reused session must not carry the previous run's scope into
                # the next one -- which is exactly how an ordinary worker would
                # have inherited organising authority by being summoned twice.
                self._authority.pop(instance_id, None)

    def _perform(self, instance_id: str, inst: Instance, work: str,
                 deadline_s: int | None) -> tuple[WorkOutcome, Instance]:
        ad = self.adapter(inst.runtime)
        # PRIVATE SCRATCH, ONE PER EXECUTION, the same one on every run of it.
        scratch = (_scratch.provision(self._record, instance_id,
                                      participant=inst.participant,
                                      runtime=inst.runtime)
                   if self._record else None)
        resume_ref, resume_why = None, "no session to continue"
        if inst.session_ref:
            elig = self.resume_eligibility(inst)
            resume_why = f"{elig.state.value}: {elig.why}"
            if elig.eligible:
                resume_ref = inst.session_ref
        permits = self._permits_for(instance_id)
        if scratch:
            # WHERE IT IS WORKING, AS FACTS. Without this a run starts in a
            # directory it did not choose and does not know is private. And
            # whether it can reach the web, from the same permits it is given.
            work = (f"{work}\n\n---\n"
                    + _scratch.note(scratch, inst.workspace,
                                    project_writable=getattr(
                                        ad, "project_writable",
                                        lambda: True)(),
                                    permits=permits))
        # WHAT THIS RUNTIME'S STREAM CAN ESTABLISH, said before it says anything,
        # so a runtime that cannot report (say) helpers is not read as having none.
        observer = self._performing.get(instance_id)
        if observer is not None:
            observer.declare(getattr(ad, "observes", ()))
        res = ad.run(
            Invocation(
                workspace=inst.workspace or ".",
                prompt=work,
                model=inst.requested_model,
                effort=inst.requested_effort,
                deliver=self._deliver.get(instance_id),
                record=self._record,
                answers_at=self._answers_at,
                capability=self._granted_to.get(instance_id),
                writable=self._writable,
                # WHAT THIS RUN MAY DO, derived HERE from why it was
                # dispatched -- the same fact the grant carries, so the tools
                # a worker is shown and the operations the door admits come
                # from one decision rather than two that can drift apart.
                permits=permits,
                # VERIFIED HERE, NOT ONLY WHERE THE INSTANCE WAS CHOSEN.
                # A caller reaching perform directly used to have its
                # session reference passed straight to the runtime with no
                # eligibility asked -- which is exactly the inference this
                # repair exists to remove. A session that cannot be shown
                # to be continuable is not continued: the run starts a new
                # one instead of claiming a continuity nobody verified.
                resume_ref=resume_ref,
                timeout_s=deadline_s,
                # The same home, so the session is the same session.
                runtime_home=inst.runtime_home,
                scratch=scratch,
                # Read while it runs; see `RuntimeAdapter._run`.
                observer=observer,
            )
        )
        if res.capacity is not None:
            self.note_capacity(res.capacity)

        terminal = "failed" if (res.exit_code != 0 or res.error) else "reported_done"
        # STOPPED HERE, AND WHY (`RuntimeAdapter._run`): settled -- the
        # runtime ended its turn and its process lingered -- is an ordinary
        # finish; stopped on request (the watchdog) is a run that did not
        # finish, named as itself so recovery can tell it from a failure of
        # the work (`dispatch.recovery_of`).
        stopped_by = getattr(observer, "stopped_by", None)             if observer is not None else None
        if not isinstance(stopped_by, dict):
            stopped_by = None
        run_error = res.error
        if stopped_by and stopped_by.get("by") != "settled":
            terminal = STALLED
            run_error = run_error or (f"stopped by the Mentis {stopped_by['by']}: "
                                      f"{stopped_by['why']}")
        if res.timed_out:
            # ITS OWN NAME. Every reader compares against "reported_done",
            # so this still counts as `did not report`, which is true --
            # but nothing has to read a boundary out of an error string.
            terminal = "stopped_at_deadline"
        # DID ANYTHING ACTUALLY RUN. Decided here, once, because a caller
        # recording evidence of delivery must not have to guess -- and
        # because the adapters report a runtime that is absent as an
        # ordinary failed result rather than an exception.
        #
        # FOUND BY REVIEW: keying on the sentinels 127 and -1 was too
        # narrow. A launch that fails another way -- a shim returning 9009
        # on Windows, for instance -- looked like a process that had run,
        # and a persona would have been recorded as delivered to it. The
        # test is now what a run that happened actually leaves behind:
        # something said, a session, or accounting. An error with none of
        # those is not evidence that anything started, and under-recording
        # is the right direction to be wrong in.
        started = not (res.error and res.session_ref is None
                       and not (res.reported or "").strip()
                       and not res.usage)
        if res.timed_out:
            # A deadline stopped a process that was running. Whatever had
            # been delivered to it genuinely crossed, so this is not the
            # `nothing started` case however little it managed to say.
            started = True
        updated = Instance(
            instance_id=inst.instance_id,
            address=inst.address,
            participant=inst.participant,
            runtime=inst.runtime,
            machine_id=inst.machine_id,
            session_ref=res.session_ref or inst.session_ref,
            requested_model=inst.requested_model,
            # Read back. Never the request echoed.
            actual_model=res.actual_model,
            requested_effort=inst.requested_effort,
            actual_effort=res.actual_effort,
            # A DEADLINE STOP IS AN ENDED INVOCATION, NOT A CRASH, and
            # FINISHED is already defined as exactly that: this invocation
            # ended, and whether the session can be continued is a separate
            # question with its own answer. Review found the alternative:
            # FAILED is excluded from CLAIMABLE and refused by `adopt`, so a
            # boundary the owner deliberately set destroyed the continuity of
            # the work it was meant to bound -- while the note claimed "work
            # already done may stand". Now it may.
            liveness=(Liveness.FINISHED
                      if res.exit_code == 0 or res.timed_out
                      else Liveness.FAILED),
            started_at=inst.started_at,
            workspace=inst.workspace,
            # Where the session this run created can be found again.
            runtime_home=res.runtime_home or inst.runtime_home,
            finished_at=time.time(),
            exit_code=res.exit_code,
            notes=inst.notes,
        )
        with self._lock:
            # RELEASE IS FINAL. If this instance was let go while the run
            # was in flight, the result is still reported -- the work
            # happened -- but the handle is not put back, and what goes out
            # to be RECORDED says GONE rather than FINISHED. Otherwise the
            # latest observation would contradict the release, and a later
            # process would find a deliberately released handle and adopt it.
            if instance_id in self._released:
                updated = replace(updated, liveness=Liveness.GONE)
            else:
                self._live[instance_id] = updated

        notes = []
        if updated.model_matched_request is False:
            notes.append(
                f"requested model {inst.requested_model!r} but "
                f"{res.actual_model.value!r} actually ran"
            )
        if not res.actual_effort.is_established:
            notes.append(f"actual effort not observable: {res.actual_effort.note}")
        if stopped_by:
            notes.append(f"process stopped by Mentis "
                         f"({stopped_by.get('by')}): {stopped_by.get('why')}")
        if res.timed_out:
            notes.append(
                f"the deadline of {deadline_s}s was reached and the run was "
                "stopped; this is the boundary somebody asked for, not a "
                "failure of the runtime, and work already done may stand")
        elif res.error:
            notes.append(f"runtime error: {res.error}")
        # PRESERVED, AND NAMED FOR WHAT IT IS. These used to reach the record
        # only by being the whole of `error`, which is how a warning came to
        # be recorded as a failure's cause. They are kept on every run -- a
        # warning on a run that SUCCEEDED was previously dropped entirely.
        for warning in res.warnings:
            notes.append(
                f"runtime warning, which the runtime said it was proceeding "
                f"past and is not the failure reason: {warning}")
        notes.append(
            "`reported` is the agent's own claim and is not evidence that the "
            "work happened; verify the artifact"
        )

        return (
            WorkOutcome(
                instance_id=instance_id,
                terminal=terminal,
                reported=res.reported,
                exit_code=res.exit_code,
                started=started,
                timed_out=res.timed_out,
                error=run_error,
                tool_calls=res.tool_calls,
                tool_calls_observable=res.tool_calls_observable,
                reasoning_items=res.reasoning_items,
                usage=res.usage,
                # What THIS execution consumed, in the runtime's own accounting.
                # Never derived from capacity, and never priced locally.
                consumption=ad.consumption(res),
                warnings=res.warnings,
                evidence=res.evidence,
                notes=tuple(notes),
            ),
            updated,
        )

    #: NOT SETTLED, AND SAID SO RATHER THAN LEFT TO BE DISCOVERED. Found by
    #: independent review and deliberately NOT fixed, because each needs a
    #: decision rather than a correction:
    #:
    #:  * CODEX'S ELEVATED WINDOWS SANDBOX CANNOT RUN UNATTENDED HERE, and
    #:    it is an upstream defect rather than anything this code can fix.
    #:    On codex-cli 0.153.0 a per-workspace `setup refresh` succeeds
    #:    (`errors=[]`, `setup binary completed`) and then the sandbox user
    #:    credential it had just validated is DELETED and not replaced:
    #:      t+0.58  .sandbox-secrets/sandbox_users.json present, sha 1c07fcb6
    #:      t+8.77  the same file deleted
    #:      +0.4s   `sandbox setup required: sandbox users missing or
    #:              incompatible with marker version`
    #:      t+9.24  consent.exe -- a UAC prompt, with nobody there
    #:    Reproduced four ways: a disposable home under %TEMP%, one under
    #:    %LOCALAPPDATA%, one carrying `.sandbox-secrets`, and a STABLE
    #:    per-workspace home carrying the marker too. With one refresh and no
    #:    concurrency it still happens, so it is not a race -- and codex never
    #:    writes the processed write roots back into its own marker, so the
    #:    refresh cannot converge however stable the home is.
    #:
    #:    A stable-home model was built to fix this and is NOT kept: the
    #:    hypothesis was falsified by the above, and speculative production
    #:    code is worse than a written-down measurement. Unattended codex work
    #:    that runs a shell command is therefore not available on this machine
    #:    until the runtime is fixed. Work that needs no shell is unaffected.
    #:
    #:  * A SANDBOXED TEST RUN LEAVES RESIDUE NOBODY HERE CAN REMOVE.
    #:    The Windows sandbox executes commands as its own local user, so
    #:    anything that user creates in the workspace is owned by it. An
    #:    ordinary file is still deletable, but a pytest temp tree is not:
    #:    reproduced twice, `pytest-of-bhill/` and a workspace-local
    #:    `--basetemp`, both ACL-denied to the owner -- `takeown` itself
    #:    returns Access Denied -- and the first blocked pytest COLLECTION
    #:    in the repo until the owner removed it with elevation.
    #:
    #:    Not fixed here, and deliberately not by loosening any ACL. It
    #:    needs a decision about where a dispatched test run puts its temp
    #:    files: the sandbox refuses paths outside its writable root, so
    #:    `C:/tmp` was denied too, and the writable root is the workspace.
    #:    Choosing a basetemp inside the workspace that is disposable by
    #:    the sandbox user, or giving the sandbox a second writable root
    #:    for temp, are both policy, not a correction. Until then a
    #:    dispatched agent should not be asked to run a test suite whose
    #:    temp tree lands in the workspace.
    #:
    #:  * TWO PROCESSES CAN BOTH ADOPT ONE SESSION. Every exclusion here is
    #:    process-local: the lock, `_inflight`, `_released`. Two Foundations
    #:    over one corpus were reproduced both adopting the same record, and
    #:    then one may relinquish a home the other is using. Closing it
    #:    needs a claim that outlives a process -- a lock file or a durable
    #:    reservation -- which is a new mechanism and an owner's decision,
    #:    not something to invent here. One server per corpus is the
    #:    supported shape; two is unsupported rather than safe.
    #:
    #:  * `GONE` CARRIES TWO MEANINGS. Recorded, it means Mentis
    #:    relinquished the session, which is durable and deliberate.
    #:    Computed by `verify_liveness` for a record this process does not
    #:    own, it means only `not live here` -- and that value is never
    #:    written, which is what keeps the two apart. It is one word for two
    #:    facts and a reader could conflate them. Splitting it is a state
    #:    change to a deliberately short enum, so it is reported instead.
    #:
    #: Still open from the previous pass:
    #: independent review of this repair and deliberately not fixed here,
    #: because each needs a decision rather than a correction:
    #:
    #:  * An artifact existing is weaker than `eligible` sounds. Both
    #:    adapters glob for a path; neither reads the file, checks that the
    #:    session inside it is the one named, or asks the provider. A
    #:    corrupt or half-written session would pass. What the providers do
    #:    with a malformed artifact was not measured.
    #:  * A provisioned CODEX_HOME is now retained so its session can be
    #:    continued, and nothing ever removes one. Fewer than before -- one
    #:    per instance instead of one per run -- but unbounded, and they
    #:    hold a copy of the runtime's auth. Cleaning them up would destroy
    #:    provider sessions, which this repair is not allowed to do.
    #:  * A grant outlives the work it was minted for. It ends at release,
    #:    which ordinary completion does not perform, so an instance left
    #:    dormant for reuse keeps a usable worker capability.
    #:  * `_released` is in-process. A release IS now recorded as GONE, so a
    #:    later process will not adopt it, but the two facts are kept in two
    #:    places and only one of them survives a restart.
    def adopt(self, rec: dict[str, Any], *, machine: str,
              participant: str | None = None,
              address=None, workspace: str | None = None,
              open_run: dict | None = None):
        """Take a recorded session back under this process, if it checks out.

        WHY THIS IS A SEPARATE, EXPLICIT ACT. `verify_liveness` reports
        GONE for anything this process does not own, and that must stay
        true -- it is the rule that stops a corpus carried to another
        machine from resurrecting handles. Adoption does not soften it.
        It asks a different question: the runtime is asked whether the
        session is still there, and only an answer of `eligible` is acted
        on. UNKNOWN is not adopted, so a runtime that cannot answer costs
        continuity and never correctness.

        SCOPE IS CHECKED, NOT ASSUMED. A session belongs to one identity,
        one runtime, one binding and one workspace. Continuing somebody
        else's conversation, or this Participant's conversation from
        another Conversation entirely, would be worse than starting fresh.

        Returns the adopted Instance, already claimed, or None with the
        reason recorded on the refusal.
        """
        if rec.get("_observed_on") != machine:
            return None, "observed on another machine"
        if rec.get("instance_id") in self._released:
            return None, "this process has released that handle"
        # AND WHAT THE RECORD SAYS, which is the half that survives. The
        # set above dies with the process; a relinquished session must not
        # come back just because nothing here remembers letting it go.
        # `resumable_candidates` already declines to offer these, and this
        # is the same refusal at the point where the decision is made, for
        # a caller that brought its own record.
        if rec.get("liveness") == "gone":
            return None, "that session was relinquished; the record says so"
        # AND THE SAME RULE AS IN-PROCESS REUSE. `CLAIMABLE` excludes FAILED
        # because a run that went wrong leaves a conversation nobody should
        # presume is clean -- and it would have been adopted anyway after a
        # restart, which is the two paths disagreeing about the same fact.
        if rec.get("liveness") == "failed":
            return None, ("that session's last run failed, so it is not "
                          "presumed clean enough to continue")
        # AN OPEN RUN IS NOT A FINISHED ONE, whatever the handle's last row
        # says. That row is written when a run ENDS and nothing is written
        # when a reused handle starts another, so after a crash mid-run it
        # still reads `finished, exit 0` -- about the run BEFORE. Adopting on
        # that would continue a session whose last run may still be inside
        # it: a process this one never started, and that the crash did not
        # necessarily stop. The record's own boundaries decide instead, and
        # an open run costs continuity rather than correctness.
        if open_run is not None:
            return None, (
                f"run {open_run.get('id')} on that session was recorded as "
                f"started and nothing has recorded its end; the handle's last "
                f"row describes an earlier run, and no process here holds this "
                f"one, so whether it is still using the session is unknown")
        if not rec.get("session_ref"):
            return None, "no session reference to continue"
        # Identity decides where either side has one. A record that carries a
        # Participant is never adopted for a caller that named a different
        # one, and a caller that named one is never given a session whose
        # record cannot say whose it was.
        if (participant is not None or rec.get("participant") is not None) \
                and rec.get("participant") != participant:
            return None, "that session belongs to a different Participant"
        if address is not None:
            recorded = rec.get("address") or {}
            # The NAME as well. Without it a name-only request could be
            # handed a differently named agent's session whenever the other
            # components happened to line up -- reproduced.
            if (recorded.get("name") != address.name
                    or recorded.get("runtime") != address.runtime
                    or recorded.get("persona") != address.persona
                    or recorded.get("context") != address.context):
                return None, "that session is a different binding"
        if workspace is not None and rec.get("workspace") != workspace:
            return None, "that session was working somewhere else"

        candidate = self.verify_liveness(rec)
        # The record says GONE because nothing here owns it. The runtime
        # is the one that knows whether the session survived.
        eligibility = self.adapter(candidate.runtime).resume_eligibility(
            session_ref=candidate.session_ref,
            workspace=candidate.workspace,
            runtime_home=rec.get("runtime_home"))
        if not eligibility.eligible:
            return None, f"{eligibility.state.value}: {eligibility.why}"

        with self._lock:
            # EVERYTHING DECIDED AGAIN, HERE. Verification took time, and in
            # that time the handle could have been released, adopted by
            # another caller, or put to work. Checking before the look and
            # installing after it let two adoptions both succeed and let an
            # adoption restore a handle that had just been released -- both
            # reproduced. The decision and the installation are now one step.
            iid = candidate.instance_id
            if iid in self._released:
                return None, "this process has released that handle"
            if iid in self._live or iid in self._inflight:
                return None, "another caller took that session first"
            adopted = replace(
                candidate, liveness=Liveness.BUSY,
                runtime_home=rec.get("runtime_home"),
                notes=(f"adopted: {eligibility.why}",))
            self._live[iid] = adopted
            self._deliver.setdefault(iid, None)
            # NO GRANT IS MINTED HERE. Adopting a session is taking
            # ownership, which is not the same as authorising a worker to
            # ask questions: that belongs to a run, and the run mints its
            # own. Anything stale from a previous life is dropped.
            old = self._granted_to.pop(iid, None)
            if old:
                self._grants.pop(old, None)
        return adopted, eligibility.why

    def verify_liveness(self, rec: dict[str, Any], *, other_machine: bool = False) -> Instance:
        """Turn a corpus record back into an Instance, checking the machine.

        A record from another machine is reported GONE here regardless of what it
        said when written. That is the rule that stops a moved corpus from
        resurrecting handles.
        """
        addr_raw = rec.get("address") or {}
        address = Address(
            name=addr_raw.get("name", "?"),
            runtime=addr_raw.get("runtime"),
            persona=addr_raw.get("persona"),
            context=addr_raw.get("context"),
        )
        recorded = rec.get("liveness", "unknown")
        iid = rec.get("instance_id", "")

        if other_machine:
            liveness = Liveness.GONE
            note = "observed on another machine; not live here"
        elif iid in self._live and not other_machine:
            # WHAT THIS PROCESS HOLDS IS NEWER THAN WHAT A FILE REMEMBERS.
            # Reading the recorded state first reported FINISHED for an
            # instance that was BUSY right now, which is the opposite of the
            # truth and hid running work from the live list.
            liveness = self._live[iid].liveness
            note = "tracked by this Foundation process"
        elif recorded in ("finished", "failed"):
            liveness = Liveness(recorded)
            note = "terminal state recorded"
        else:
            iid = rec.get("instance_id", "")
            if iid in self._live:
                liveness = self._live[iid].liveness
                note = "tracked by this Foundation process"
            else:
                # Recorded alive, but nothing in this process owns it. We do not
                # claim it is alive on the strength of a file.
                liveness = Liveness.GONE
                note = (
                    "recorded as live, but no process here owns it; reported GONE "
                    "rather than trusting the record"
                )

        return Instance(
            instance_id=rec.get("instance_id", ""),
            address=address,
            # Carried back, so identity survives a round trip through the
            # record. Absent on anything written before this existed.
            participant=rec.get("participant"),
            runtime_home=rec.get("runtime_home"),
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
            exit_code=rec.get("exit_code"),
            notes=(note,),
        )

    def release(self, instance_id: str) -> tuple[ReleaseResult, Instance | None]:
        """RELINQUISH CONTINUITY. Five facts, and this is exactly one of them.

        These are separate and stay separate, because collapsing any two of
        them would make Mentis claim something it cannot see:

          1. THE INVOCATION ENDED -- recorded `Liveness.FINISHED`/`FAILED`.
             Says nothing about the session.
          2. THE SESSION CAN BE CONTINUED -- `ResumeEligibility`, asked of
             the runtime when somebody wants to continue it. Never stored,
             because it is a fact about the provider NOW and a stored copy
             would be a claim about the past.
          3. MENTIS OWNS THE HANDLE -- membership of `_live`, in this
             process, on this machine. Never durable: ownership of a live
             thing cannot survive the thing that held it.
          4. MENTIS HAS RELINQUISHED IT -- this call, recorded as `GONE`.
             Durable, deliberate, and the one the owner cares about: a
             release must not quietly come back after a restart.
          5. THE PROVIDER'S SESSION IS DESTROYED -- almost never known, and
             never asserted. The one case where it becomes true is a Codex
             home that Mentis provisioned and then discarded, and even then
             what is recorded is (4), with the discard reported as what was
             done rather than as a state.

        So this ends 3 and asserts 4. It does not delete or close the
        provider's session, except by discarding a home Mentis itself made,
        which happens only here because only here has Mentis said nobody
        will continue that session.

        It is also FINAL. A perform already inside `adapter.run` used to
        write its instance back afterwards, so a released handle reappeared
        as FINISHED with its grant already revoked.


        It is also FINAL. A perform already inside `adapter.run` used to
        write its instance back afterwards, so a released handle
        reappeared as FINISHED with its grant already revoked.
        """
        # THE REASON THE RUN EXISTED GOES FIRST, AND UNCONDITIONALLY. Releasing
        # means nothing will continue this execution, so its authority is over
        # whichever branch below is taken -- including the early return for an
        # id nothing here holds, which is exactly the path a dispatch that fails
        # between summon and perform takes.
        self._authority.pop(instance_id, None)
        inst = self._live.get(instance_id)
        if inst is None:
            return (
                ReleaseResult(
                    instance_id=instance_id, released=True,
                    verified_against_machine=False,
                    notes=("nothing live here under that id",),
                ),
                None,
            )
        ad = self.adapter(inst.runtime)
        residue: list[str] = []
        if inst.pid is not None and ad.liveness_of_pid(inst.pid):
            residue.append(f"process {inst.pid} still running")

        updated = Instance(
            instance_id=inst.instance_id, address=inst.address,
            participant=inst.participant, runtime=inst.runtime,
            runtime_home=inst.runtime_home,
            machine_id=inst.machine_id, session_ref=inst.session_ref,
            requested_model=inst.requested_model, actual_model=inst.actual_model,
            requested_effort=inst.requested_effort, actual_effort=inst.actual_effort,
            liveness=Liveness.GONE, started_at=inst.started_at,
            workspace=inst.workspace, finished_at=inst.finished_at or time.time(),
            exit_code=inst.exit_code, notes=inst.notes,
        )
        with self._lock:
            self._released.add(instance_id)
            self._live.pop(instance_id, None)
        self._deliver.pop(instance_id, None)
        # The execution is over, so its authorisation is too.
        gone = self._granted_to.pop(instance_id, None)
        if gone:
            self._grants.pop(gone, None)

        # THE ONE MOMENT A PROVISIONED HOME IS DISCARDED. Nobody will
        # continue this session now, so the rollout it holds -- and the copy
        # of the runtime's auth beside it -- stop being worth keeping. Said
        # out loud in the result rather than done quietly, because it is the
        # only point where releasing a handle also ends a provider session.
        # NOT WHILE SOMETHING IS INSIDE IT. Release does not wait for a run,
        # and deleting the home under a live invocation would take the
        # rollout it is writing. The relinquishment still stands; the home is
        # left for the sweep, which removes homes this record names AND says
        # were relinquished -- which is now exactly this one.
        if instance_id in self._inflight:
            discarded = ("left for the sweep: a run is still inside it"
                         if inst.runtime_home else None)
            scratch_said = ("left for the sweep: a run is still inside it"
                            if self._record else None)
        else:
            discarded = ad.discard_session_home(inst.runtime_home)
            # AND ITS PRIVATE SCRATCH, for the same reason and at the same
            # moment: nobody will continue this execution, and what it had to
            # hand on is in custody or was never handed on.
            scratch_said = (_scratch.discard(self._record, instance_id)
                            if self._record else None)

        return (
            ReleaseResult(
                instance_id=instance_id,
                released=not residue,
                verified_against_machine=True,
                residue=tuple(residue),
                notes=tuple(n for n in (
                    "checked against the OS process table, not against "
                    "Foundation's own registry",
                    # Not residue: discarding a home we made is the release
                    # working, not something left behind by it.
                    f"runtime home: {discarded}" if discarded else None,
                    f"scratch: {scratch_said}" if scratch_said else None,
                ) if n),
            ),
            updated,
        )


def _observed_from(raw: Any) -> Observed:
    if isinstance(raw, dict):
        prov = raw.get("provenance", "unknown")
        try:
            prov = Provenance(prov)
        except ValueError:
            prov = Provenance.UNKNOWN
        return Observed(
            value=raw.get("value"), provenance=prov,
            observed_at=raw.get("observed_at", 0.0), note=raw.get("note"),
        )
    return Observed.unknown("not recorded")


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
