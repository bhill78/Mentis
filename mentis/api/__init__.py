"""The public Mentis seam.

This package IS the contract. Every ingress -- the CLI today, HTTP/desktop/phone
and agents later -- reaches Mentis through `MentisAPI` and the types re-exported
here, and through nothing else.

`mentis.api` deliberately depends on nothing inside Mentis. It does not import
`mentis.core`, `mentis.foundation` or `mentis.corpus`, so it cannot become a
convenience door into an implementation. `connect()` resolves the implementation
lazily, inside the function body, for exactly that reason.

Enforced by tests/test_boundaries.py, which fails if a client imports anything
under `mentis.` other than `mentis.api`, or if this package grows an inward
import.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .errors import (
    CorpusInvalid,
    CorpusNotAttached,
    InstanceNotFound,
    InvocationFailed,
    MentisError,
    RuntimeNotPresent,
    Unsupported,
)
from .types import (
    UNKNOWN,
    Address,
    Capability,
    CapacityReading,
    Consumption,
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

__all__ = [
    "MentisAPI",
    "connect",
    "UNKNOWN",
    "Address",
    "Capability",
    "CapacityReading",
    "Consumption",
    "DeliveryOpportunity",
    "Instance",
    "Liveness",
    "ModelInfo",
    "Observed",
    "Provenance",
    "ReleaseResult",
    "RuntimeInfo",
    "Selection",
    "UsageWindow",
    "WorkOutcome",
    "MentisError",
    "Unsupported",
    "RuntimeNotPresent",
    "CorpusNotAttached",
    "CorpusInvalid",
    "InstanceNotFound",
    "InvocationFailed",
]


@runtime_checkable
class MentisAPI(Protocol):
    """Every Mentis capability an ingress may use.

    Operations return data. None of them returns text formatted for display --
    the moment one does, whichever client it was formatted for becomes the
    reference client and every later ingress inherits its shape.
    """

    # -- corpus -------------------------------------------------------------
    def corpus_attach(self, path: str) -> dict: ...
    def corpus_status(self) -> dict: ...

    # -- runtimes -----------------------------------------------------------
    def runtimes_discover(self) -> list[RuntimeInfo]: ...
    def models_list(self, runtime: str) -> list[ModelInfo]: ...
    def capacity_observe(self, runtime: str) -> CapacityReading: ...
    def delivery_opportunities(self, runtime: str) -> list[DeliveryOpportunity]: ...

    # -- selection ----------------------------------------------------------
    def execution_select(
        self,
        *,
        difficulty: str = "ordinary",
        runtime: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> Selection: ...

    # -- agents -------------------------------------------------------------
    #: `participant` is the durable Participant this is FOR, when the
    #: caller knows it. The Address stays a non-unique name; the reference
    #: travels beside it, because two deliberate Participants may share an
    #: alias and must not share an execution.
    def agents_resolve(self, address: Address, *,
                       participant: str | None = None) -> dict: ...
    def agents_summon(
        self,
        address: Address,
        selection: Selection,
        *,
        workspace: str,
        deliver: str | None = None,
        reuse: bool = True,
        participant: str | None = None,
    ) -> Instance: ...
    #: `deadline_s` is an execution-duration policy, not a constant:
    #: None means the run ends when the process does. Omitted, the
    #: Foundation's own policy applies.
    def agents_perform(self, instance_id: str, work: str, *,
                       deadline_s: int | None = ...,
                       run: str | None = None) -> WorkOutcome: ...
    #: A RUN IS NOT AN INSTANCE. `run` is the recorded start of one run;
    #: these say which runs THIS process holds and what it has observed of
    #: each. Ephemeral: a restart forgets them, and that is the answer.
    def agents_open_run(self, instance_id: str, run: str) -> None: ...
    def agents_end_run(self, run: str) -> None: ...
    def agents_runs(self) -> dict[str, dict]: ...
    def agents_halt_run(self, run: str, *, by: str, why: str) -> bool: ...
    #: Remove provisioned runtime homes no recorded session refers to.
    #: The rule is the record, never an age, and only homes Mentis made.
    def agents_sweep_homes(self) -> dict: ...
    def agents_sweep_scratch(self) -> dict: ...
    def agents_observe(self, instance_id: str) -> Instance: ...
    def agents_list(self, *, include_finished: bool = False) -> list[Instance]: ...
    def agents_release(self, instance_id: str) -> ReleaseResult: ...


def connect(corpus_path: str | None = None) -> MentisAPI:
    """The one way in.

    The import is inside the function so that `mentis.api` has no import-time
    dependency on any implementation. A client that imports `mentis.api` gets
    the contract; it never gets a handle on core, foundation or corpus.
    """
    from mentis.core.service import MentisService

    return MentisService(corpus_path)


def open_corpus(path: str, *, access: str = "auto"):
    """Open a corpus at a path the user chose, and return the spine seam.

    Resolved lazily inside the function body, for the same reason `connect()`
    is: `mentis.api` must not gain an inward import and become a convenience
    door into an implementation.

    Never creates a Brain and never changes its schema (D2). `access="write"`
    refuses a Brain the schema check opens read-only; "read" never writes.
    """
    from mentis.spine.seam import open_corpus as _open

    return _open(path, access=access)


def create_corpus(path: str):
    """Create a new Brain at `path` and return its spine seam. The one way a
    Brain comes into being; refuses where one exists."""
    from mentis.spine.seam import create_corpus as _create

    return _create(path)


def conversations(corpus):
    """The Conversation capability over a corpus. Same lazy-import discipline.

    Everything this returns is built on the spine's own public methods; it
    reaches no store and no record shape.
    """
    from mentis.conversation import open_conversations as _open

    return _open(corpus)


def brain(corpus, attached=()):
    """The Brain a Participant orients to: a primary corpus, and later others.

    Brain scope needs no durable representation. This wires the Conversation
    seam it drills into and returns a computed view; nothing here is stored.
    """
    from mentis.brain import open_brain as _open

    return _open(corpus, conversations(corpus), attached=attached)


def sources(corpus):
    """Bulk Source over a corpus: every connector's collections through one
    facade that routes by each collection's declared connector -- declare,
    bind, plan, sweep, revise scope, and read back what was acquired. Only
    the filesystem connector is available. Same lazy-import discipline as
    `conversations`."""
    from mentis.conversation import open_conversations as _open
    from mentis.sources.registry import Sources as _Sources

    return _Sources(corpus, _open(corpus))


def capability_names() -> set[str]:
    """Every capability a runtime can declare (`types.Capability`), as the
    names a requirement may use. One place, for every door that checks one."""
    from mentis.api.types import Capability
    return {c.value for c in Capability}
