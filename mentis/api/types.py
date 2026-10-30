"""Value types crossing the public Mentis seam.

Nothing here knows about a runtime, a filesystem layout, or a client. These are the
shapes every ingress sees.

Two rules shape almost everything in this file:

1. A fact that could be requested-but-not-observed is never collapsed into one field.
   `requested_*` and `actual_*` are separate, and `actual_*` may be UNKNOWN.
2. A fact that can go stale carries where it came from and when it was seen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


UNKNOWN = "unknown"


class Provenance(str, Enum):
    """Where a fact came from. Never inferred, always stated.

    Ordering matters: PROVIDER_REPORTED outranks LOCALLY_OBSERVED outranks
    LOCALLY_INFERRED. Nothing in Mark IV promotes a value up this ladder.
    """

    PROVIDER_REPORTED = "provider_reported"
    LOCALLY_OBSERVED = "locally_observed"
    LOCALLY_INFERRED = "locally_inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Observed:
    """A value with its provenance and the moment it was seen.

    `value is None` means 'we did not establish this'. It never means zero.
    """

    value: Any
    provenance: Provenance
    observed_at: float = field(default_factory=time.time)
    note: str | None = None

    @property
    def is_established(self) -> bool:
        return self.value is not None

    def age_seconds(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) - self.observed_at

    @staticmethod
    def unknown(note: str) -> "Observed":
        return Observed(value=None, provenance=Provenance.UNKNOWN, note=note)


class Capability(str, Enum):
    """What a runtime genuinely supports.

    A runtime declares these. Foundation refuses an operation a runtime has not
    declared rather than emulating it -- see api.errors.Unsupported.

    This enum exists because the three measured runtimes do NOT support the same
    things, and the alternative was compatibility machinery that lies.
    """

    DISCOVER = "discover"
    INVOKE_HEADLESS = "invoke_headless"
    LIST_MODELS = "list_models"
    REQUEST_MODEL = "request_model"
    OBSERVE_ACTUAL_MODEL = "observe_actual_model"
    REQUEST_EFFORT = "request_effort"
    OBSERVE_ACTUAL_EFFORT = "observe_actual_effort"
    OBSERVE_CAPACITY = "observe_capacity"
    SESSION_IDENTITY = "session_identity"
    RESUME = "resume"
    DELIVER_AT_START = "deliver_at_start"
    DELIVER_TO_LIVE = "deliver_to_live"
    ISOLATE_FROM_MACHINE_CONFIG = "isolate_from_machine_config"
    # This runtime can execute a model served locally on this machine. It says
    # only that the runtime can reach local compute -- nothing about how capable
    # any such model is.
    REACH_LOCAL_MODELS = "reach_local_models"
    # A dispatched worker on this runtime can actually CALL Mentis's read tools.
    # Declared here rather than left in adapter code, because it was already
    # true of all three by three different mechanisms -- a temporary
    # `--mcp-config` plus an `--allowedTools` permission list, a pre-approved
    # namespace in a provisioned config, a provisioned home -- and selection
    # could not see any of them. Work that organises itself through the tools
    # requires this; declaring is not the same as it being callable, which is
    # why each adapter's own pre-approval is part of the claim.
    CALL_MENTIS_TOOLS = "call_mentis_tools"
    # This runtime can write in its workspace with nobody present to approve
    # each write. It says nothing about what those writes may reach: the
    # boundary is the runtime's own sandbox or permission mode, not this flag.
    WRITE_UNATTENDED = "write_unattended"
    # This runtime can BUILD the web UI in its workspace: run `npm ci` /
    # `npm run build` / the render check, which read ancestor directories.
    # Which runtimes can is MARS's to report (`capabilities` / `lacks` in
    # `_mars/backends`, measured through MARS); Mark IV measured it absent on
    # Codex's Windows sandbox. A runtime nobody has established it for may be
    # tried (`MentisService.TRIABLE`), and says so when it cannot.
    BUILD_UI = "build_ui"
    # This runtime can launch and drive a real browser (Playwright / browser
    # tests) from a dispatch, including from its shell. Reported by MARS as
    # above; triable when unknown.
    DRIVE_BROWSER = "drive_browser"
    # DELIBERATELY ABSENT: attended writes. A headless dispatch has nobody to
    # answer a prompt, so no path offers it and no adapter may declare it. A
    # request that genuinely needs one is UNSUPPORTED everywhere, and saying so
    # every time is the honest answer rather than a missing concept.


class Liveness(str, Enum):
    """Deliberately short.

    Only states we can back with evidence from at least one measured runtime.
    `WORKING` vs `WAITING` is absent because nothing measured distinguishes them.
    Adding a state here requires evidence, not a wish.
    """

    STARTING = "starting"
    ALIVE = "alive"
    #: A perform is INSIDE this instance right now. Added on evidence, not
    #: wish: two dispatches were able to select the same dormant instance
    #: and both call perform, because nothing marked the interval between
    #: choosing one and running it. This is that interval, and it is the
    #: claim that makes selection exclusive.
    BUSY = "busy"
    #: THIS INVOCATION ENDED. It does NOT mean the runtime session died --
    #: measured: Claude and Codex both resume a session after this, and no
    #: process survives any perform on any runtime. Whether the session can
    #: still be resumed is a separate question with a separate answer;
    #: `ResumeEligibility` below is that answer.
    FINISHED = "finished"
    FAILED = "failed"
    GONE = "gone"
    UNKNOWN = "unknown"


class Resumable(str, Enum):
    """Whether a runtime session can still be continued. Observed, never assumed."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResumeEligibility:
    """Can this runtime session be continued, and on what evidence.

    A SEPARATE FACT FROM WHETHER THE LAST CALL FINISHED, and separate from
    whether any process is running. Measured on all three runtimes: no
    process outlives a perform, yet Claude and Codex both continue the same
    session afterwards -- so reading FINISHED as "dead" discards something
    that is still there.

    A SESSION REFERENCE IS NOT EVIDENCE. Codex proves why: its rollout
    lives in the CODEX_HOME an invocation was given, and a reference to a
    thread whose home has gone answers `no rollout found for thread id`.
    So the question is asked of the runtime, which can look, rather than
    inferred from the presence of an id.

    UNKNOWN IS A REAL ANSWER and never an invented eligibility. A runtime
    that exposes nothing to check says so, and nothing is adopted on it.
    """

    state: Resumable
    #: What was actually looked at. Always said, including when eligible.
    why: str

    @property
    def eligible(self) -> bool:
        return self.state is Resumable.ELIGIBLE

    @classmethod
    def unknown(cls, why: str) -> "ResumeEligibility":
        return cls(Resumable.UNKNOWN, why)

    @classmethod
    def yes(cls, why: str) -> "ResumeEligibility":
        return cls(Resumable.ELIGIBLE, why)

    @classmethod
    def no(cls, why: str) -> "ResumeEligibility":
        return cls(Resumable.INELIGIBLE, why)


@dataclass(frozen=True)
class RuntimeInfo:
    """A runtime as found on THIS machine. Never durable corpus content."""

    kind: str
    present: bool
    version: Observed
    executable: Observed
    capabilities: frozenset[Capability]
    machine_id: str
    discovered_at: float = field(default_factory=time.time)
    notes: tuple[str, ...] = ()

    def supports(self, cap: Capability) -> bool:
        return cap in self.capabilities


@dataclass(frozen=True)
class ModelInfo:
    """A model a runtime says it can run.

    `efforts` is the runtime's OWN vocabulary. It is not translated into a
    common scale, because the measured vocabularies genuinely differ.

    `locality` says WHERE the compute happens and nothing else. It is a fact
    about execution, never a claim about capability: a local model is not
    assumed weaker and a hosted one is not assumed stronger. Selection reasons
    from what the work requires, and `locality` is not one of its inputs --
    tests/test_local_models.py fails if it becomes one.
    """

    slug: str
    runtime: str
    efforts: tuple[str, ...] = ()
    default_effort: str | None = None
    context_window: int | None = None
    display_name: str | None = None
    locality: str = UNKNOWN
    provider: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageWindow:
    """One capacity window, in the units the provider actually used.

    There is no normalisation to a single scale and no blending of windows.
    `used_fraction` is 0..1; a provider reporting percent is converted here and
    the original is kept in `raw`, because a unit change is the one conversion
    that cannot lie.
    """

    label: str
    used_fraction: float | None
    window_seconds: int | None
    resets_at: float | None
    provenance: Provenance
    raw: dict[str, Any] = field(default_factory=dict)
    # The pool this window belongs to, named as the runtime names it, where
    # the runtime splits its quota between groups of models (Antigravity:
    # "Gemini Models", "Claude and GPT models"). None means the runtime has
    # one pool, not that the group is unknown.
    group: str | None = None

    def is_expired(self, now: float | None = None) -> bool:
        """A window past its own reset instant no longer describes anything."""
        if self.resets_at is None:
            return False
        return (now if now is not None else time.time()) >= self.resets_at


@dataclass(frozen=True)
class CapacityReading:
    """Capacity for one runtime, on one machine, at one moment.

    Deliberately NOT a score. Windows stay separate, units stay explicit, and a
    reading that established nothing says so rather than reporting zero.
    """

    runtime: str
    machine_id: str
    observed_at: float
    windows: tuple[UsageWindow, ...] = ()
    plan: Observed | None = None
    tokens: Observed | None = None
    cost_usd: Observed | None = None
    context_window: Observed | None = None
    notes: tuple[str, ...] = ()
    # Which model draws on which group's windows, as (slug, group) pairs, for
    # a runtime whose windows carry a `group`. The group is None where the
    # runtime's own grouping does not place the model: that model has no
    # meter, and never borrows another group's.
    model_groups: tuple[tuple[str, str | None], ...] = ()
    # LOCAL RESOURCES, NOT QUOTA: for a local-model runtime, what its model
    # servers say about themselves now (MARS's `local`, verbatim: servers,
    # models, loaded memory, running turns, and what is `unavailable`). Never
    # turned into windows: a loaded model's memory is not a share of a plan.
    local: dict | None = None

    @property
    def established(self) -> bool:
        return bool(self.windows) or bool(self.plan and self.plan.is_established)

    def live_windows(self, now: float | None = None) -> tuple[UsageWindow, ...]:
        """Windows that have not passed their own reset instant."""
        return tuple(w for w in self.windows if not w.is_expired(now))


@dataclass(frozen=True)
class Consumption:
    """What ONE execution consumed, in the runtime's own accounting.

    Consumption is not capacity. Capacity is how much of a window remains;
    consumption is what a single run used. They are measured by different
    mechanisms, at different resolutions, and one cannot be derived from the
    other -- see `docs/evidence/consumption.md`.

    `native` is the runtime's own usage object, verbatim and unconverted. It is
    the authoritative record, and anything a caller needs beyond the common
    field below must be read from there, knowing which accounting it follows.

    THERE IS DELIBERATELY NO COMMON `input_tokens`, AND NO TOTAL. Measured:

        claude   input_tokens=2      cache_read=15553  cache_creation=13537
        codex    input_tokens=14561  cached_input_tokens=12288

    Claude's input EXCLUDES cached tokens; Codex's INCLUDES them. The word is
    the same and the concept is not, so a shared field would be a falsehood
    that arithmetic could not detect.

    `output_tokens` IS shared, because it was measured to mean the same thing
    in all three: tokens generated, with reasoning/thinking counted inside it.
    """

    runtime: str
    accounting: str
    native: dict[str, Any]
    output_tokens: Observed
    reported_cost_usd: Observed
    observed_at: float = field(default_factory=time.time)
    reobservable: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    """A resolved choice, carrying why it was made.

    `because` is not decoration. A selection whose reasoning cannot be inspected
    cannot be reviewed, and capacity-informed choices are exactly the kind that
    need reviewing.
    """

    runtime: str
    model: str | None
    requested_effort: str | None
    because: tuple[str, ...]
    dimensions_used: tuple[str, ...] = ()
    #: Runtimes this selection ruled out when nobody chose one -- exhausted,
    #: or the author's for review work -- so continuing a session cannot
    #: quietly put the work back on one of them. Empty for an explicit runtime.
    excluded: tuple[str, ...] = ()
    # Exact observations and constraints used by the deterministic selector.
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Address:
    """How a human names an agent. NOT an identity, and NOT unique.

    `@Ada + claude + planner` and `@Ada + codex + planner` are different bindings
    of the same name and may both be live. Nothing here enforces a count.
    """

    name: str
    runtime: str | None = None
    persona: str | None = None
    context: str | None = None

    def binding_key(self, identity: str | None = None) -> str:
        """The tuple that distinguishes legitimate concurrent instances.

        Two invocations sharing a binding_key are candidates for continuity.
        Two invocations differing in any component are legitimately separate.

        `identity` IS NOT STORED HERE, AND THAT IS THE POINT. An Address is
        how a human names an agent; it must stay non-unique and stay not an
        identity. But two deliberate Participants may share the alias
        `@Ada`, and keying continuity on the name alone hands the second
        one the first one's live execution. So a caller that KNOWS which
        durable Participant it means passes the reference, and the
        reference leads the key instead of the label.

        Everything after it is unchanged: the same Participant reaching
        Claude and Codex is one identity with two legitimate bindings, and
        runtime, persona and context still tell those apart.
        """
        return "|".join(
            [identity or self.name, self.runtime or "*",
             self.persona or "*", self.context or "*"]
        )

    def __str__(self) -> str:
        bits = [f"@{self.name}"]
        if self.runtime:
            bits.append(self.runtime)
        if self.persona:
            bits.append(self.persona)
        if self.context:
            bits.append(f"in {self.context}")
        return " + ".join(bits)


@dataclass(frozen=True)
class Instance:
    """A live or historical runtime instance.

    `pid`, `session_ref` and `workspace` are machine-local. They are attributed to
    a machine and never travel as corpus truth -- see corpus.records.
    """

    instance_id: str
    address: Address
    runtime: str
    machine_id: str
    session_ref: str | None
    requested_model: str | None
    actual_model: Observed
    requested_effort: str | None
    actual_effort: Observed
    liveness: Liveness
    started_at: float
    #: THE DURABLE PARTICIPANT THIS INSTANCE IS CARRYING, when the caller
    #: knew it. Optional because a caller may legitimately name only an
    #: alias, and because a record written before this existed has none.
    #: It is a reference, not a name: the alias remains a display name and
    #: remains shareable.
    participant: str | None = None
    #: THE RUNTIME HOME THIS SESSION LIVES IN, where the runtime keeps one.
    #: Machine-local like `pid` and `workspace`, and never corpus truth.
    #: Codex keeps its rollout here and cannot resume a thread without it,
    #: so a home that is thrown away takes the session with it -- measured.
    runtime_home: str | None = None
    pid: int | None = None
    workspace: str | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    notes: tuple[str, ...] = ()

    @property
    def model_matched_request(self) -> bool | None:
        """None when we could not observe the actual model at all."""
        if not self.actual_model.is_established or self.requested_model is None:
            return None
        return self.actual_model.value == self.requested_model


@dataclass(frozen=True)
class DeliveryOpportunity:
    """A real moment at which information can reach a runtime.

    Only created from a mechanism that was observed to work. `verified` records
    whether THIS repository proved it end to end, as opposed to reading it in docs.
    """

    runtime: str
    moment: str
    mechanism: str
    verified: bool
    note: str = ""


@dataclass(frozen=True)
class WorkOutcome:
    """The result of asking an instance to do something.

    `reported` is what the agent SAID. It is never evidence. Verification happens
    outside this type, against the artifact.
    """

    instance_id: str
    terminal: str
    reported: str | None
    exit_code: int | None
    #: WHETHER A PROCESS ACTUALLY RAN, which is not the same as whether
    #: the work succeeded. A runtime that is not installed comes back as
    #: an ordinary failed result rather than an exception, and nothing
    #: crossed in that case -- so anything recording evidence of delivery
    #: has to be able to tell the two apart. Only Foundation can: it is
    #: the layer that owns the adapter contract.
    started: bool = True
    #: A DEADLINE STOPPED THIS, and that is not a crash. Made a field
    #: because review found the only statement of it was a sentence in
    #: `notes` that nothing rendered or read -- so the distinction the
    #: deadline work exists to draw reached nobody.
    timed_out: bool = False

    #: WHAT THIS EXECUTION ACTUALLY CALLED, as its runtime reported it, and
    #: whether that runtime reports such things at all. An observation of one
    #: run: work that needed no tool calls none, and that says nothing about
    #: what the model could have done. Deliberately NOT a model property --
    #: there is no `supports_tools` here and there should never be one.
    #: THE MOST SPECIFIC REASON ANYTHING OBSERVED, carried rather than
    #: summarised. A run that failed before the runtime spoke has no
    #: `reported`, and saying only `nothing reported` describes the silence
    #: instead of the failure -- which is what a real Antigravity failure
    #: was recorded as: `terminal 'failed', exit -1, nothing reported`, with
    #: the adapter's own exception string discarded on the way here.
    error: str | None = None
    tool_calls: tuple[str, ...] = ()
    tool_calls_observable: bool = False
    #: Reasoning items the runtime's own stream carried; None where it does
    #: not report reasoning. See `RunResult.reasoning_items`.
    reasoning_items: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    consumption: "Consumption | None" = None
    notes: tuple[str, ...] = ()

    #: WHAT THE RUNTIME CALLED A WARNING. Carried separately from `error` so
    #: that a line the runtime said it was proceeding past cannot be presented
    #: as the reason it stopped.
    warnings: tuple[str, ...] = ()

    #: THE RUNTIME'S OWN OUTPUT for a failed run, kept distinct from `error`,
    #: which is Mentis's interpretation of it.
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseResult:
    """What release actually achieved, checked against the machine.

    `residue` is what we could NOT prove gone. An empty registry is not proof.
    """

    instance_id: str
    released: bool
    verified_against_machine: bool
    residue: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
