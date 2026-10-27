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
        self._run_of: dict[str, str] = {}
        #: WHEN EACH RUNTIME WAS LAST SELECTED, as a sequence number, for the
        #: tie-break in `execution_select`. This process only.
        self._last_selected: dict[str, int] = {}
        self._selections = 0
        #: The last `_mars/capacity` answer and when it was read (monotonic).
        self._capacity: tuple[float, dict] | None = None
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
            notes = [f"MARS backend ({b.get('kind') or 'unknown kind'})"]
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

    def _capacity_report(self) -> dict:
        """MARS's `_mars/capacity`, reused for `CAPACITY_REUSE_S`. An
        Execution without it, or a failed read, is an empty answer."""
        with self._lock:
            held = self._capacity
        if held is not None and time.monotonic() - held[0] < CAPACITY_REUSE_S:
            return held[1]
        read = getattr(self.execution, "capacity", None)
        try:
            report = read() if callable(read) else {}
        except Exception:                                 # noqa: BLE001
            report = {}
        report = report if isinstance(report, dict) else {}
        if report:
            with self._lock:
                self._capacity = (time.monotonic(), report)
        return report

    def capacity_observe(self, runtime: str) -> CapacityReading:
        """What MARS says is left of this runtime's quota (`_mars/capacity`),
        windows kept separate and in the runtime's own labels. A runtime MARS
        reports nothing for is an empty reading saying why -- never zero."""
        r = self._capacity_report().get(runtime)
        now = time.time()
        if not isinstance(r, dict):
            return CapacityReading(runtime=runtime, machine_id=self._machine,
                                   observed_at=now, notes=(
                                       f"{_NO_CAPACITY} for {runtime}",))
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

    # -- selection ----------------------------------------------------------

    def _models_of(self, b: dict) -> set[str]:
        return {str(m.get("id") if isinstance(m, dict) else m)
                for m in b.get("models") or () if m}

    def eligibility(self, runtime: str, requires, model: str | None = None) -> dict:
        """Can this backend meet each named requirement -- and is that KNOWN.

        SUPPORTED when MARS's catalogue says so (`call_mentis_tools`: the
        backend takes stdio MCP servers; anything else: named in a
        `capabilities` list the backend declares), UNKNOWN otherwise.
        **UNKNOWN DOES NOT SATISFY ANYTHING**, as before.
        """
        b = self._backend(runtime) or {}
        declared = {str(c) for c in b.get("capabilities") or ()}
        if "stdio" in ((b.get("supports") or {}).get("mcp") or ()):
            declared.add(Capability.CALL_MENTIS_TOOLS.value)
        known = {c.value for c in Capability}
        out = {}
        for name in requires or ():
            if name in declared:
                out[name] = {"verdict": "supported", "scope": runtime,
                             "evidence": f"MARS lists {runtime} with {name}"}
            elif name not in known:
                out[name] = {"verdict": "unknown", "scope": runtime,
                             "evidence": (f"{name!r} is not a capability any "
                                          f"runtime can declare, so nothing "
                                          f"here can judge it")}
            else:
                out[name] = {"verdict": "unknown", "scope": runtime,
                             "evidence": (f"MARS does not say whether {runtime} "
                                          f"has {name}")}
        return out

    def eligible(self, runtime: str, requires, model: str | None = None) -> bool:
        return all(r["verdict"] == "supported"
                   for r in self.eligibility(runtime, requires, model).values())

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
    ) -> Selection:
        """Resolve a runtime/model/effort, and say what informed the choice.

        Runtimes are MARS backends; one is usable when MARS reports it
        available. `requires` NARROWS who is eligible and nothing else. An
        explicit runtime or model is a constraint: refused, never substituted.
        Capacity is not an input here, so among the eligible the runtime selected
        least recently by this process wins, then MARS's catalogue order --
        the old last tie-break, which is now the whole rule, said as such.

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
            qualified = [b for b in present
                         if all(r["verdict"] == "supported"
                                for r in judged[b["id"]].values())]
            if not qualified:
                raise Unsupported(
                    ", ".join(b["id"] for b in present), "execution_select",
                    "no available runtime meets every requirement: "
                    + "; ".join(f"{k}: " + ", ".join(
                        f"{n} {r['verdict']}" for n, r in sorted(rs.items())
                        if r["verdict"] != "supported")
                        for k, rs in sorted(judged.items())))
            because.append(f"required {list(requires)}; eligible "
                           f"{[b['id'] for b in qualified]}; a capability is a "
                           f"filter, not a preference")
            dims.append("required_capabilities")
            present = qualified
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
        if runtime:
            chosen = next((b for b in present if b["id"] == runtime), None)
            if chosen is None:
                known = self._backend(runtime)
                if known is not None and known.get("available"):
                    raise Unsupported(
                        runtime, "execution_select",
                        "it is available but does not meet every requirement: "
                        + ", ".join(f"{n} {r['verdict']} ({r['evidence']})"
                                    for n, r in sorted(self.eligibility(
                                        runtime, requires).items())
                                    if r["verdict"] != "supported"))
                raise RuntimeNotPresent(
                    f"{runtime} is not available: "
                    + ((known or {}).get("reason") or
                       ("MARS lists it unavailable" if known else
                        "MARS does not list it")))
            because.append(f"runtime {runtime} was requested explicitly")
        else:
            open_ = present
            if avoid:
                others = [b for b in open_ if b["id"] != avoid]
                if others:
                    because.append(
                        f"review: the reviewed work ran on {avoid}; it is "
                        f"avoided so the review runs on a different runtime")
                    excluded = (avoid,)
                    open_ = others
                else:
                    because.append(
                        f"review: the reviewed work ran on {avoid} and no "
                        f"other runtime is available; independence by runtime "
                        f"was not achievable")
                dims.append("review_independence")
            order = {b["id"]: n for n, b in enumerate(backends)}
            with self._lock:
                last = dict(self._last_selected)
            open_ = sorted(open_, key=lambda b: (last.get(b["id"], -1),
                                                 order[b["id"]]))
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
                chosen = open_[0]
                because.append(f"capacity is not an input to this rule; runtime "
                               f"{chosen['id']} chosen as "
                               f"the least recently selected here, then by MARS's "
                               f"catalogue order, of {[b['id'] for b in open_]}")
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
                         model: str | None = None) -> str | None:
        """None when `runtime` could take this work now, else why not."""
        b = self._backend(runtime)
        if b is None:
            return f"{runtime} is not a runtime MARS lists"
        if not b.get("available"):
            return f"{runtime} is not available: {b.get('reason') or 'MARS gave no reason'}"
        requires = tuple(requires or ())
        if requires and not self.eligible(runtime, requires, model):
            unmet = [n for n, r in self.eligibility(runtime, requires, model).items()
                     if r["verdict"] != "supported"]
            return f"{runtime} does not meet {unmet}"
        return None

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
                        why = f"runs on {got.runtime}, which does not meet {list(requires)}"
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
        spec = RunSpec(run_id=instance_id, backend=inst.runtime,
                       workspace=inst.workspace or ".", prompt=work,
                       mcp_servers=self.mcp_servers_for(instance_id,
                                                        inst.workspace),
                       options={k: v for k, v in (
                           ("model", inst.requested_model),
                           ("effort", inst.requested_effort)) if v},
                       limits=limits)

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
                                    ("started_at", res.started_at),
                                    ("finished_at", res.finished_at))
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
