"""Errors that cross the public seam.

These are part of the contract. An ingress renders them; it never inspects a
runtime to work out what went wrong.
"""

from __future__ import annotations


class MentisError(Exception):
    """Base for everything the seam raises."""


class Unsupported(MentisError):
    """The runtime genuinely does not provide this.

    Raised instead of emulating a capability. The three measured runtimes differ
    substantially, and a fabricated equivalence would be worse than a refusal:
    a caller can handle 'this runtime reports no capacity', but cannot handle
    'it reported capacity that we made up'. (Antigravity was the worked example
    here until its `/usage` surface was found; see docs/evidence A6.)
    """

    def __init__(self, runtime: str, capability: str, note: str = "") -> None:
        self.runtime = runtime
        self.capability = capability
        self.note = note
        msg = f"{runtime} does not support {capability}"
        if note:
            msg += f" ({note})"
        super().__init__(msg)


class RuntimeNotPresent(MentisError):
    """The runtime was not found on this machine."""


class CatalogueUnavailable(MentisError):
    """The runtime does list its models, and this reading of them failed.

    Not `Unsupported`: the capability is real, this attempt did not establish
    it. The message is the reason, so an empty list is never shown in its
    place.
    """


class CorpusNotAttached(MentisError):
    """No corpus has been attached. Mentis will not guess a location."""


class CorpusInvalid(MentisError):
    """The directory is not a Mentis corpus, or is unreadable."""


class InstanceNotFound(MentisError):
    """No such instance in this corpus, on this machine."""


class InvocationFailed(MentisError):
    """The runtime was invoked and failed in a way the caller must see."""

    def __init__(self, runtime: str, detail: str, exit_code: int | None = None) -> None:
        self.runtime = runtime
        self.detail = detail
        self.exit_code = exit_code
        super().__init__(f"{runtime}: {detail}" + (f" (exit {exit_code})" if exit_code is not None else ""))
