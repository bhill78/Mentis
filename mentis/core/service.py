"""The implementation of the public seam.

There is exactly one of these. The CLI does not have its own path to a runtime,
and a future HTTP ingress will not get one either -- they both call these
methods.
"""

from __future__ import annotations

from mentis.foundation import scratch as _scratch

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
    ReleaseResult,
    Resumable,
    RuntimeInfo,
    Selection,
    WorkOutcome,
)
from mentis.corpus.store import Corpus, machine_id, require
from mentis.foundation.service import Foundation

#: HOW LONG A FINISHED SESSION'S SCRATCH IS KEPT FOR CONTINUATION before the
#: sweep relinquishes it. Owner's storage audit, 2026-10-26: a scratch was
#: kept while its session read as continuable, and nothing ever relinquished
#: a finished session, so 836 scratches of ended runs (426 of them finished
#: more than a week before) sat under one Brain. Two days covers every
#: continuation observed in the record; after that the session is let go
#: exactly as an explicit release lets it go (`agents_release`).
SCRATCH_RETAIN_S = 48 * 3600.0


class MentisService:
    """Implements `mentis.api.MentisAPI`."""

    def __init__(self, corpus_path: str | None = None) -> None:
        self._corpus: Corpus | None = None
        self._foundation = Foundation()
        self._machine = machine_id()
        #: Per-call continuity notes. Dispatch runs on its own thread.
        self._thread = threading.local()
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
        """Name the record dispatched workers may query.

        NOT the instance corpus this service attaches. That one holds live
        agent bookkeeping; the record a worker is asked questions ABOUT is the
        spine, and only the caller that opened the spine knows where it is. So
        it is said explicitly rather than inferred from what happens to be
        attached here -- an inferred answer would silently hand workers the
        wrong corpus.
        """
        self._foundation.reads(corpus_path, answers_at=answers_at,
                               writable=writable)

    def corpus_status(self) -> dict:
        if self._corpus is None:
            raise CorpusNotAttached("no corpus attached")
        return {
            **self._corpus.identity(),
            "attached_path": self._corpus.path,
            "machine_id": self._machine,
            "history_records": len(self._corpus.instance_history()),
        }

    # -- runtimes -----------------------------------------------------------

    def runtimes_discover(self) -> list[RuntimeInfo]:
        return self._foundation.discover(self._machine)

    def models_list(self, runtime: str) -> list[ModelInfo]:
        ad = self._foundation.adapter(runtime)
        if not ad.capabilities().__contains__(Capability.LIST_MODELS):
            raise Unsupported(runtime, "list_models",
                              "no machine-readable model catalogue was found")
        return ad.list_models()

    def capacity_observe(self, runtime: str) -> CapacityReading:
        ad = self._foundation.adapter(runtime)
        if Capability.OBSERVE_CAPACITY not in ad.capabilities():
            # Not an error: an honest empty reading, so a caller can tell the
            # difference between "no capacity" and "capacity of zero".
            reading = ad.observe_capacity(self._machine)
        else:
            reading = ad.observe_capacity(self._machine)
        # WHAT WAS OBSERVED ANYWAY informs the next selection; nothing is
        # observed in order to select.
        self._foundation.note_capacity(reading)
        if self._corpus is not None:
            self._corpus.record_capacity(reading)
        return reading

    def delivery_opportunities(self, runtime: str) -> list[DeliveryOpportunity]:
        return self._foundation.adapter(runtime).delivery_opportunities()

    # -- selection ----------------------------------------------------------

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
    ) -> Selection:
        """Resolve a runtime/model/effort, and say what informed the choice.

        Capacity participates only where a runtime actually reports it. For a
        runtime that reports none, the selection says so rather than pretending
        capacity was considered.

        `requires` is what the WORK needs, judged from declared capabilities.
        It narrows the candidates and never ranks them.
        """
        return self._foundation.select(
            machine=self._machine,
            difficulty=difficulty,
            runtime=runtime,
            model=model,
            effort=effort,
            requires=requires,
            avoid=avoid,
            considered=considered,
        )

    def execution_usable(self, runtime: str, requires=(),
                         model: str | None = None) -> str | None:
        """None if `runtime` could take this work now, else why not. See
        `Foundation.usable`."""
        return self._foundation.usable(self._machine, runtime, requires, model)

    def execution_eligibility(self, runtime: str, requires,
                              model: str | None = None) -> dict:
        """Whether one runtime -- and, given one, the model behind it -- meets
        each requirement, and on what evidence."""
        return self._foundation.eligibility(runtime, requires, model)

    def provider_of(self, runtime: str, model: str | None) -> str | None:
        """Who SERVES this model under that harness, or None for the runtime
        itself. See `RuntimeAdapter.provider_of`."""
        try:
            return self._foundation.adapter(runtime).provider_of(model)
        except Exception:
            # A runtime that cannot be asked is an honest unknown, not a crash
            # in the middle of recording provenance.
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

    def agents_resolve(self, address: Address, *,
                       participant: str | None = None) -> dict:
        """What summoning this address would do, without doing it.

        Addresses are NOT unique. This reports the live instances whose binding
        matches, so a caller can see why a summon would reuse or would not.

        WHEN THE CALLER KNOWS WHICH PARTICIPANT IT MEANS, THAT DECIDES.
        Measured: two deliberate Participants both aliased `@Ada` produced
        the identical binding key, so the second was handed the first's
        live execution. The name is a label and two identities may share
        it; the reference is the identity. It has to decide in BOTH places
        -- this filter and the comparison below -- because filtering by
        name first would let the collision back in whatever the key says.
        """
        corpus = require(self._corpus)
        # BOTH KINDS OF CANDIDATE. `live_candidates` is instances whose
        # invocation has not ended; `resumable_candidates` is the ones whose
        # has, which is exactly where a dormant session lives. Looking only
        # at the first is what made a finished instance invisible.
        seen_ids: set[str] = set()
        records = []
        for rec in (list(corpus.live_candidates(self._machine))
                    + list(corpus.resumable_candidates(self._machine))):
            iid = rec.get("instance_id", "")
            if iid in seen_ids:
                continue
            seen_ids.add(iid)
            records.append(rec)
        matches = [
            rec for rec in records
            if (rec.get("participant") == participant if participant
                else rec.get("address", {}).get("name") == address.name)
        ]
        verified = []
        for rec in matches:
            inst = self._foundation.verify_liveness(rec)
            # FINISHED IS NOW INCLUDED, because it was never the fact it
            # was being read as. It says the last call returned; whether
            # the runtime session can still be continued is asked of the
            # runtime at claim time. BUSY is excluded because something is
            # inside it, which is a different reason from being over.
            if inst.liveness in (Liveness.ALIVE, Liveness.STARTING,
                                 Liveness.FINISHED):
                verified.append(inst)
        # IDENTITY DECIDES WHERE EITHER SIDE HAS ONE -- the same rule
        # `adopt` applies, because otherwise the two disagree. A caller that
        # named no Participant used to match on the name alone, and was
        # handed a session belonging to a specific identity: reproduced, one
        # @Ada's live session going to an unbound caller. A nameless caller
        # may only continue an instance that is itself unbound.
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
            # Which of those ENDED and so would have to be verified before
            # being continued. Resolving does not ask the runtime: the
            # question costs a look at the filesystem and is asked once, at
            # claim time, by the caller that is actually going to use it.
            "dormant": [i.instance_id for i in exact
                        if i.liveness is Liveness.FINISHED],
            "note": (
                "a live instance under the same name but a different binding is "
                "legitimate concurrency, not a duplicate"
            ),
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
        """Resolve first, then create only if concurrency genuinely requires it.

        Summon is NOT idempotent on the address. It is resolved against live
        instances sharing the same full binding. `@Ada + claude + planner` and
        `@Ada + codex + planner` are different bindings and may both be live.

        `requires` IS APPLIED TO REUSE AS WELL AS TO A FRESH START, and that is
        the whole reason it is a parameter here rather than only in `select`. A
        reused instance "is whatever it already was": an address naming no
        runtime could otherwise resume a session on a runtime the selection had
        just ruled out, which is eligibility bypassed by continuity. A candidate
        whose runtime cannot meet the requirements is left alone -- not
        released, because nothing is wrong with that session; it is simply not
        eligible for THIS work.

        `open_runs` is what the RECORD says is still running, by instance:
        the start act of each run nothing has ended. This store keeps
        instances, not runs, so the caller that holds the operational record
        says -- and a session with an open run is never adopted on the
        strength of its handle's last row, which describes an earlier run.
        """
        corpus = require(self._corpus)
        # EVIDENCE BELONGS TO THIS CALL. Dispatch runs on its own thread
        # and these notes are recorded as what happened to THIS piece of
        # work; kept on the service they were shared, so one dispatch
        # could record another's reasons as its own.
        self._thread.notes = []
        if reuse:
            # 1. A HANDLE THIS PROCESS OWNS. Claiming is what makes the
            #    choice exclusive: two dispatches reading the same dormant
            #    instance cannot both get it, because only one claim wins.
            res = self.agents_resolve(address, participant=participant)
            for candidate in res["live_same_binding"]:
                got = self._foundation.claim(candidate)
                if got is None:
                    self._notes().append(
                        f"{candidate}: in use or gone, not claimed")
                    continue
                # WHAT SELECTION RULED OUT, continuity does not bring back:
                # a runtime exhausted by its own report, or the author's
                # runtime for review work. Left as it is, not released.
                if got.runtime in getattr(selection, "excluded", ()):
                    self._notes().append(
                        f"{candidate}: runs on {got.runtime}, which this "
                        f"selection excluded; not eligible for this work")
                    self._foundation.unclaim(candidate)
                    continue
                # AN EXPLICIT MODEL IS A CONSTRAINT, AND REUSE USED TO IGNORE IT.
                #
                # MEASURED IN REAL USE, and it is the whole reason this check
                # exists. `binding_key` is identity|runtime|persona|context and
                # says nothing about the model, so one live `@ShortRound + codex`
                # session matched every request regardless of which model was
                # named. Traced on execution b87d7782: the FRESH run asked for
                # `qwen2.5-coder:14b` and observed `qwen2.5-coder:14b`, and then
                # SEVEN reused runs asked for `ornith:9b` or `llama3.2:latest`
                # and every one of them observed `gpt-6-astra` -- the runtime's
                # own hosted default, because a resumed thread is not re-pointed
                # at local compute. The owner believed a local experiment was
                # running for twenty minutes while it was hosted.
                #
                # The record was honest throughout -- `requested_model` and
                # `observed_model` disagreed in writing on every one of those
                # acts -- but nothing REFUSED, and a disagreement nobody is
                # looking at is not a control. An explicitly named model now
                # makes a differently-bound session ineligible, so the work
                # starts fresh on what was asked for instead of silently
                # becoming something else.
                #
                # Nothing changes when no model was named: unconstrained work
                # reuses exactly as before, and this never PICKS a model.
                if explicit_model and got.requested_model != explicit_model:
                    self._notes().append(
                        f"{candidate}: bound to model "
                        f"{got.requested_model!r}, and {explicit_model!r} was "
                        f"explicitly requested; not eligible for this work")
                    self._foundation.unclaim(candidate)
                    continue
                # AN EXPLICIT EFFORT, BY THE SAME RULE. An instance keeps the
                # effort it was started with, so reusing one bound otherwise
                # would run the work at an effort nobody asked for while the
                # request said the opposite.
                if explicit_effort and got.requested_effort != explicit_effort:
                    self._notes().append(
                        f"{candidate}: bound to effort "
                        f"{got.requested_effort!r}, and {explicit_effort!r} was "
                        f"explicitly requested; not eligible for this work")
                    self._foundation.unclaim(candidate)
                    continue
                # ELIGIBILITY IS ASKED OF A REUSED SESSION TOO. Checked after
                # the claim, so the answer is about the instance actually in
                # hand and its real runtime rather than what the record last
                # said about it.
                # And of the MODEL that session is bound to, which is what
                # a resume would run.
                if requires and not self._foundation.eligible(
                        got.runtime, requires, got.requested_model):
                    unmet = [n for n, r in self._foundation.eligibility(
                        got.runtime, requires, got.requested_model).items()
                        if r["verdict"] != "supported"]
                    self._notes().append(
                        f"{candidate}: runs on {got.runtime}, which does not "
                        f"meet {unmet}; not eligible for this work")
                    self._foundation.unclaim(candidate)
                    continue
                # THE WORKSPACE IS PART OF CONTINUING, not a detail. An
                # instance runs where it was started; handing this work a
                # session rooted somewhere else would run it in the wrong
                # directory while everything else said otherwise.
                if got.workspace != workspace:
                    self._notes().append(
                        f"{candidate}: working in {got.workspace!r}, not "
                        f"{workspace!r}")
                    # PUT IT DOWN, DO NOT THROW IT AWAY. Releasing would
                    # discard the home and the session in it -- so merely
                    # summoning the same binding from another directory would
                    # have destroyed the first one's work. Nothing is wrong
                    # with that session; it is simply not this work's.
                    self._foundation.unclaim(candidate)
                    continue
                if got.liveness is Liveness.BUSY and got.session_ref:
                    # It ended once. Ask the runtime whether the session is
                    # still there rather than trusting the reference.
                    elig = self._foundation.resume_eligibility(got)
                    if not elig.eligible:
                        self._notes().append(
                            f"{candidate}: {elig.state.value}: {elig.why}")
                        # RELINQUISH ONLY ON A NO, NEVER ON A DON'T KNOW.
                        # Releasing discards a provisioned home and the
                        # session in it, so an UNKNOWN -- codex off PATH, a
                        # timeout, a runtime that cannot answer -- would have
                        # destroyed a perfectly good session over a
                        # transient. An unknown session is left exactly as
                        # it is and the work starts fresh beside it.
                        if elig.state is Resumable.INELIGIBLE:
                            self._foundation.release(candidate)
                        else:
                            self._foundation.unclaim(candidate)
                        continue
                    self._notes().append(f"resumed: {elig.why}")
                return got
            # 2. A SESSION THE RECORD KNOWS AND NOTHING HERE OWNS -- after a
            #    restart, typically. Adoption is explicit and verified; it
            #    is never a side effect of having found a record.
            owned = {i.instance_id for i in self._foundation._live.values()}
            for rec in corpus.resumable_candidates(self._machine):
                if rec.get("instance_id") in owned:
                    continue
                adopted, why = self._foundation.adopt(
                    rec, machine=self._machine, participant=participant,
                    address=address, workspace=workspace,
                    open_run=(open_runs or {}).get(rec.get("instance_id")))
                if adopted is not None:
                    if adopted.runtime in getattr(selection, "excluded", ()):
                        self._notes().append(
                            f"{adopted.instance_id}: adoptable but runs on "
                            f"{adopted.runtime}, which this selection "
                            f"excluded; left as it is")
                        self._foundation.unclaim(adopted.instance_id)
                        continue
                    # THE MODEL CONSTRAINT ON THE ADOPTION PATH TOO, for the
                    # same reason the capability filter is on both: adoption is
                    # the other way a session from a previous run is continued.
                    if (explicit_model
                            and adopted.requested_model != explicit_model):
                        self._notes().append(
                            f"{adopted.instance_id}: adoptable but bound to "
                            f"model {adopted.requested_model!r}, and "
                            f"{explicit_model!r} was explicitly requested")
                        self._foundation.unclaim(adopted.instance_id)
                        continue
                    if (explicit_effort
                            and adopted.requested_effort != explicit_effort):
                        self._notes().append(
                            f"{adopted.instance_id}: adoptable but bound to "
                            f"effort {adopted.requested_effort!r}, and "
                            f"{explicit_effort!r} was explicitly requested")
                        self._foundation.unclaim(adopted.instance_id)
                        continue
                    # THE SAME FILTER ON THE ADOPTION PATH. Reuse and adoption
                    # are two ways to reach the same bypass, and an eligibility
                    # check on only one of them is no check at all.
                    if requires and not self._foundation.eligible(
                            adopted.runtime, requires, adopted.requested_model):
                        unmet = [n for n, r in self._foundation.eligibility(
                            adopted.runtime, requires,
                            adopted.requested_model).items()
                            if r["verdict"] != "supported"]
                        self._notes().append(
                            f"{adopted.instance_id}: adoptable but runs on "
                            f"{adopted.runtime}, which does not meet {unmet}; "
                            f"left as it is")
                        self._foundation.unclaim(adopted.instance_id)
                        continue
                    self._notes().append(f"adopted: {why}")
                    return adopted
                if why:
                    self._notes().append(f"{rec.get('instance_id')}: {why}")
            # 3. Neither. Fall through and start fresh, which is what the
            #    durable record is reconstructed for.

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
            liveness=Liveness.STARTING,
            started_at=time.time(),
            workspace=workspace,
            notes=(f"deliver={'yes' if deliver else 'no'}",),
        )
        # Registered ALREADY CLAIMED, so there is no moment in which a fresh
        # instance is visible and unclaimed. What is recorded is what is
        # owned, and what is returned is what was claimed.
        inst = self._foundation.register(inst, deliver=deliver, claimed=True)
        try:
            corpus.record_instance(inst)
        except Exception:
            # An instance nothing recorded is an instance nobody can find
            # again, and it would sit claimed forever. Put it down.
            self._foundation.release(inst.instance_id)
            raise
        self._notes().append("started fresh")
        return inst

    # -- runs, as this process holds them -------------------------------------
    #
    # A RUN IS NOT AN INSTANCE. Nothing below is written to this store: which
    # runs are open is the operational record's to say, and what a process
    # holding one has observed of it is machine-local and dies with it.

    def agents_open_run(self, instance_id: str, run: str) -> None:
        """This process has recorded `run` as started on that handle."""
        self._foundation.open_run(instance_id, run)

    def agents_end_run(self, run: str) -> None:
        """This process no longer holds `run`, however it ended."""
        self._foundation.end_run(run)

    def agents_runs(self) -> dict[str, dict]:
        """What this process observes of each run it holds, by run."""
        return self._foundation.run_observations()

    def agents_halt_run(self, run: str, *, by: str, why: str) -> bool:
        """Stop a run this process holds (`Foundation.halt_run`)."""
        return self._foundation.halt_run(run, by=by, why=why)

    def agents_perform(self, instance_id: str, work: str, *,
                       deadline_s: int | None = ...,
                       run: str | None = None) -> WorkOutcome:
        """Run the work, then record what the instance became.

        FOUND BY REVIEW: the recording happened after Foundation had let go
        of its lock, so a release landing in between produced a durable
        history of FINISHED, GONE, FINISHED -- and the latest observation is
        what a restart reads, so the released session was adopted again. The
        relinquishment wins whenever it happened, because it is a decision
        and the other is just an outcome.
        """
        corpus = require(self._corpus)
        outcome, updated = self._foundation.perform(
            instance_id, work, deadline_s=deadline_s, run=run)
        if self._foundation.was_released(instance_id):
            updated = replace(updated, liveness=Liveness.GONE)
        corpus.record_instance(updated)
        return outcome

    def agents_answer_once(self, prompt: str, **kw):
        """A Scratch answer: Foundation's `answer_once`, and NOTHING recorded --
        no instance, no capacity, no history. See `Foundation.answer_once`."""
        return self._foundation.answer_once(prompt, **kw)

    def agents_answering_now(self) -> set:
        return self._foundation.answering_now()

    def agents_observe(self, instance_id: str) -> Instance:
        corpus = require(self._corpus)
        live = self._foundation.known(instance_id)
        if live is not None:
            return live
        for rec in reversed(corpus.instance_history()):
            if rec.get("instance_id") == instance_id:
                return self._foundation.verify_liveness(rec)
        raise InstanceNotFound(instance_id)

    def agents_sweep_homes(self) -> dict:
        """Remove runtime homes THIS record says have been relinquished.

        WHY THIS EXISTS, MEASURED: 74 provisioned Codex homes had accumulated
        in %TEMP% on this machine. Each holds a thread rollout and a copy of
        the runtime's auth, and nothing ever removed one.

        WHAT IT WILL NOT DO, LEARNED THE HARD WAY. An earlier version swept
        every home on disk that this corpus did not name -- and a corpus
        knows nothing about homes belonging to another corpus or another
        server, so it deleted all 74 the first time a test opened a state
        over an empty record. Two servers would have destroyed each other's
        live sessions. So the rule is now the narrow one: a home is removed
        only when THIS record names it AND says that session was
        relinquished.

        A home nothing here knows about is LEFT ALONE and counted. It may
        belong to another corpus, and an unprovable claim of abandonment is
        not a reason to delete somebody's session. That is why the count is
        reported: homes do not grow silently, even where they cannot be
        cleaned.

        `~/.codex` is the user's own history, is not a Mentis home, and
        cannot be reached from here -- the adapter only recognises the
        prefix it provisions under.
        """
        corpus = require(self._corpus)
        latest: dict[str, dict] = {}
        for rec in corpus.instance_history():
            if rec.get("_observed_on") == self._machine:
                latest[rec.get("instance_id", "")] = rec
        keep, relinquished = set(), set()
        for rec in latest.values():
            home = rec.get("runtime_home")
            if not home:
                continue
            (relinquished if rec.get("liveness") == "gone" else keep).add(home)
        # A home still named by live or dormant work is never removed, even
        # if some older record of it was relinquished.
        relinquished -= keep

        removed, failed, unknown = [], [], []
        for ad in self._foundation._adapters.values():
            known = getattr(ad, "abandoned_homes", None)
            if known is None:
                continue
            for home in known(set()):
                if home in keep:
                    continue
                if home not in relinquished:
                    unknown.append(home)
                    continue
                said = ad.discard_session_home(home)
                target = removed if (said or "").startswith(("removed",
                                                              "already gone")) else failed
                target.append({"home": home, "said": said})
        return {
            "kept": sorted(keep), "removed": removed, "not_removed": failed,
            "left_alone": sorted(unknown),
            "rule": "removed only where this record names the home AND says "
                    "the session was relinquished; anything else is left "
                    "alone because it may belong to another corpus",
        }
    def agents_sweep_scratch(self) -> dict:
        """Remove private scratch no execution can come back to.

        UNLIKE HOMES, EVERY SCRATCH HERE IS THIS RECORD'S. They live under the
        corpus's own directory, so one no instance record names is an orphan
        of this corpus -- what a crash between provisioning and recording, or
        a record from another machine, leaves -- and not somebody else's.

          removed    the latest record here says relinquished (`gone`), or
                     no record names it
          kept       live or dormant: a session that can still be continued
                     keeps the directory it was recorded in
          unmarked   under the root but not provisioned by Mentis; reported,
                     never touched
        """
        corpus = require(self._corpus)
        record = self._foundation._record
        if not record:
            return {"kept": [], "removed": [], "not_removed": [],
                    "unmarked": [], "transcripts": {"removed": [], "kept": []},
                    "rule": "no record attached"}
        latest: dict[str, dict] = {}
        for rec in corpus.instance_history():
            latest[rec.get("instance_id", "")] = rec
        live = set(self._foundation._live) | set(self._foundation._inflight)
        # A FINISHED SESSION IDLE PAST RETENTION IS RELINQUISHED HERE, the
        # way a release relinquishes it (record, home, scratch, transcript),
        # so what follows removes it as relinquished rather than keeping it
        # as continuable forever.
        # A DORMANT HANDLE THIS PROCESS STILL HOLDS IS NOT A RUN: only a run
        # in flight is spared; `agents_release` lets the handle go with it.
        now = time.time()
        idle = []
        kept, removed, failed = [], [], []
        for execution in _scratch.present(record):
            rec = latest.get(execution)
            if rec is None or execution in self._foundation._inflight \
                    or rec.get("liveness") != "finished":
                continue
            when = (rec.get("finished_at") or rec.get("_observed_at")
                    or rec.get("started_at") or now)
            try:
                if now - float(when) < SCRATCH_RETAIN_S:
                    continue
            except (TypeError, ValueError):
                continue
            try:
                self.agents_release(execution)
            except Exception:                             # noqa: BLE001
                continue
            idle.append(execution)
            removed.append({"execution": execution, "said": "removed",
                            "why": f"relinquished: finished "
                                   f"{(now - float(when)) / 3600:.0f}h ago, "
                                   f"past the {SCRATCH_RETAIN_S / 3600:.0f}h "
                                   f"retention"})
        if idle:
            latest = {}
            for rec in corpus.instance_history():
                latest[rec.get("instance_id", "")] = rec
            live = set(self._foundation._live) | set(self._foundation._inflight)
        for execution in _scratch.present(record):
            rec = latest.get(execution)
            if execution in live or (rec is not None
                                     and rec.get("liveness") != "gone"):
                kept.append(execution)
                continue
            said = _scratch.discard(record, execution)
            (removed if said in ("removed", "already gone") else failed
             ).append({"execution": execution, "said": said,
                       "why": "relinquished" if rec else "named by no record"})
        # AND THE TRANSCRIPTS those relinquished executions left -- only for
        # executions the record names and has relinquished, with the scratch
        # path computed, so the pair is provable after the scratch is gone.
        transcripts = {"removed": [], "kept": []}
        for execution, rec in latest.items():
            if rec.get("liveness") != "gone" or execution in live:
                continue
            said = self._discard_transcripts(execution, rec.get("runtime"))
            if said and said["state"] == "removed":
                transcripts["removed"].append(said["folder"])
            elif said and said["state"] == "kept" and said.get("folder") is None:
                continue
            elif said and said["state"] == "kept":
                transcripts["kept"].append({"execution": execution,
                                            "folder": said["folder"],
                                            "why": said["why"]})
        return {"kept": kept, "removed": removed, "not_removed": failed,
                "relinquished_idle": idle,
                "transcripts": transcripts,
                "unmarked": _scratch.unmarked(record),
                "rule": "kept while the execution's session can be "
                        "continued and has finished within "
                        f"{SCRATCH_RETAIN_S / 3600:.0f}h; relinquished and "
                        "removed past that, once relinquished, or when no "
                        "record names it"}

    def agents_list(self, *, include_finished: bool = False) -> list[Instance]:
        """Only what is actually live, unless history is asked for.

        Every candidate is checked against this machine before being reported
        live, so a finished or killed instance cannot linger as an apparently
        available agent.
        """
        corpus = require(self._corpus)
        seen: dict[str, Instance] = {}
        for rec in corpus.instance_history():
            if rec.get("_observed_on") != self._machine:
                # Another machine's observation. Historical here, always.
                if include_finished:
                    inst = self._foundation.verify_liveness(rec, other_machine=True)
                    seen[inst.instance_id] = inst
                continue
            inst = self._foundation.verify_liveness(rec)
            seen[inst.instance_id] = inst
        out = list(seen.values())
        if not include_finished:
            # BUSY counts as live: something is inside it right now.
            # FINISHED does not -- a dormant session is not working.
            out = [i for i in out if i.liveness in (
                Liveness.ALIVE, Liveness.STARTING, Liveness.BUSY)]
        return out

    def _sessions_of(self, instance_id: str) -> set[str]:
        """Every session the record attributes to this execution."""
        corpus = require(self._corpus)
        return {rec.get("session_ref") for rec in corpus.instance_history()
                if rec.get("instance_id") == instance_id
                and rec.get("session_ref")}

    def _discard_transcripts(self, instance_id: str, runtime) -> dict | None:
        """The transcript a relinquished execution's scratch left, by the
        decided rule (#28/#29). Only where the scratch is already gone: a
        scratch still there (a run inside it) means not yet."""
        record = self._foundation._record
        ad = self._foundation._adapters.get(runtime or "")
        if not record or ad is None or not hasattr(ad, "discard_transcripts"):
            return None
        where = _scratch.path_for(record, instance_id)
        if where.exists():
            return {"state": "kept", "folder": None,
                    "why": "its scratch is still there, so the session is "
                           "not yet over"}
        return ad.discard_transcripts(str(where),
                                      self._sessions_of(instance_id))

    def agents_release(self, instance_id: str) -> ReleaseResult:
        """Relinquish continuity, and RECORD that we did.

        THE RECORD IS WHAT SURVIVES, so it is the record that has to carry
        the decision. Foundation keeps a process-local note of what it let
        go; the durable `GONE` observation written here is what a later
        process reads, and it is why an explicit release does not quietly
        come back after a restart.

        A SESSION NOBODY HERE OWNS CAN STILL BE RELINQUISHED. After a
        restart the handle is not in memory but the session is still
        recorded and still adoptable, and `release` had nothing to say
        about it -- so releasing it did nothing at all and the next process
        adopted it. The record is now written from the record.
        """
        corpus = require(self._corpus)
        result, updated = self._foundation.release(instance_id)
        if updated is not None:
            corpus.record_instance(updated)
            said = self._discard_transcripts(instance_id, updated.runtime)
            if said and said["state"] != "absent":
                result = replace(result, notes=tuple(result.notes) + (
                    f"transcript: {said['state']}"
                    + (f" ({said['why']})" if said.get("why") else ""),))
            return result

        rec = next((r for r in corpus.resumable_candidates(self._machine)
                    if r.get("instance_id") == instance_id), None)
        if rec is None:
            return result
        # Told to this process too, so an adoption already in flight here
        # cannot pass its final check and take what was just let go.
        self._foundation.mark_released(instance_id)
        standing = self._foundation.verify_liveness(rec)
        ad = self._foundation.adapter(standing.runtime)
        discarded = ad.discard_session_home(rec.get("runtime_home"))
        record = self._foundation._record
        scratch_said = (_scratch.discard(record, instance_id)
                        if record else None)
        corpus.record_instance(replace(standing, liveness=Liveness.GONE,
                                       finished_at=time.time()))
        said = self._discard_transcripts(instance_id, standing.runtime)
        return ReleaseResult(
            instance_id=instance_id, released=True,
            verified_against_machine=False,
            notes=tuple(n for n in (
                "nothing live here held it; the recorded session was "
                "relinquished so no later process adopts it",
                f"runtime home: {discarded}" if discarded else None,
                f"scratch: {scratch_said}" if scratch_said else None,
                (f"transcript: {said['state']}"
                 + (f" ({said['why']})" if said.get("why") else ""))
                if said and said["state"] != "absent" else None,
            ) if n))
