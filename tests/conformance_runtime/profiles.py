"""The runtime profiles the offline conformance mode serves.

Each profile is what MARS says of one runtime (its `_mars/backends` entry, with the
round-2 capability contract as MARS's `runtime_contract.rs` declares it for that backend)
and how the runtime behaves through MARS where Mentis can tell the difference: how it
resumes (`on-new`: a token at session/new that a later session/new may load; `per-prompt`:
a token per turn that MARS says cannot be resumed; `none`: no token), and its quota.

The states here MUST be MARS's. `test_contract.py::test_profiles_say_what_mars_declares`
checks them against a MARS build when one is named (`MENTIS_CONFORMANCE_MARS`).
"""

from __future__ import annotations

from mentis.core.runtime_contract import (CAPABILITIES, SUPPORTED, UNSUPPORTED,
                                          UNVERIFIED)

RECORD_FALLBACK = ("the client opens a fresh session and sends the whole composition "
                   "derived from its record (Mentis: the full payload, with everything new "
                   "since the previous run)")


def _contract(states: dict, kinds: dict | None = None) -> dict:
    caps = {}
    for name in CAPABILITIES:
        s = states.get(name, UNVERIFIED)
        c = {"state": s, "evidence": f"profile: {name} {s}",
             # MARS (bf6f991): a state it declares without having shown it is
             # `not-yet-verified` with its kind and source "mars".
             "source": ("verified" if s != UNVERIFIED
                        else "mars" if (kinds or {}).get(name) else "none")}
        if (kinds or {}).get(name):
            c["kind"] = kinds[name]
        if s == UNSUPPORTED and name == "native_resume":
            c["fallback"] = RECORD_FALLBACK
        caps[name] = c
    return {"version": 1, "states": ["supported", "unsupported", "temporarily-unavailable",
                                     "not-yet-verified"],
            "availability": {"state": SUPPORTED}, "capabilities": caps}


def _backend(id_, *, kind="acp", permissions="forwarded", mcp=("stdio",), models=(),
             contract=None, cancel="cooperative"):
    return {"id": id_, "kind": kind, "installed": True, "available": True, "reason": None,
            "version": "conformance", "models": list(models), "efforts": [],
            "capabilities": [], "lacks": {},
            "supports": {"cancel": cancel, "load": False, "images": False,
                         "mcp": list(mcp), "permissions": permissions},
            "contract": contract}


PROFILES = {
    "claude": {
        "resume": "on-new", "codeword": "CLAUDE",
        "backend": _backend("claude", models=("default", "sonnet", "opus"), contract=_contract(
            {"native_resume": SUPPORTED, "permission_enforcement": SUPPORTED,
             "mcp_tools": SUPPORTED, "cancellation": SUPPORTED, "execution_events": SUPPORTED,
             "completion_reporting": SUPPORTED, "model_discovery": SUPPORTED,
             "delegation_coordination": SUPPORTED},
            {"native_resume": "session/resume", "permission_enforcement": "forwarded+runtime-rules",
             "cancellation": "cooperative+kill", "capacity_reporting": "quota"})),
    },
    "codex": {
        "resume": "on-new", "codeword": "CODEXX",
        "backend": _backend("codex", permissions="backend-mode", mcp=("stdio", "http"),
                            models=("gpt-6-luna", "gpt-6.1-terra"), contract=_contract(
            {"native_resume": SUPPORTED, "execution_events": SUPPORTED,
             "model_discovery": SUPPORTED,
             "context_restoration": SUPPORTED, "mcp_tools": SUPPORTED, "cancellation": SUPPORTED,
             "completion_reporting": SUPPORTED, "delegation_coordination": SUPPORTED},
            {"permission_enforcement": "sandbox+runtime-reviewer",
             "capacity_reporting": "quota"})),
    },
    "antigravity": {
        "resume": "per-prompt", "codeword": "AGYAGY",
        "backend": _backend("antigravity", kind="cli", permissions="none",
                            models=("gemini-3-flash",), cancel="kill", contract=_contract(
            {"native_resume": UNSUPPORTED, "permission_enforcement": SUPPORTED,
             "cancellation": SUPPORTED, "execution_events": SUPPORTED,
             "context_restoration": SUPPORTED, "mcp_tools": SUPPORTED,
             "completion_reporting": SUPPORTED, "delegation_coordination": SUPPORTED},
            {"permission_enforcement": "pre-turn", "cancellation": "kill",
             "model_discovery": "agy models", "capacity_reporting": "quota"})),
    },
    "kimi-k3": {
        "resume": "none", "codeword": "KIMIKK",
        "backend": _backend("kimi-k3", contract=_contract(
            {"capacity_reporting": UNSUPPORTED}, {"permission_enforcement": "forwarded"})),
    },
    "local": {
        "resume": "none", "codeword": "LOCALL",
        "backend": _backend("local", permissions="none", mcp=("stdio", "http", "sse"),
                            contract=_contract(
            {"native_resume": UNSUPPORTED, "model_discovery": UNSUPPORTED,
             "execution_events": SUPPORTED, "mcp_tools": SUPPORTED,
             "cancellation": SUPPORTED},
            {"permission_enforcement": "none", "capacity_reporting": "resources",
             "mcp_tools": "stdio", "cancellation": "cooperative+kill"})),
    },
}

#: MARS (round 2 E, `consent::client_review`): how a client becomes the reviewer of a
#: consented codex session's requests to leave its sandbox, declared in the contract.
PROFILES["codex"]["backend"]["contract"]["capabilities"]["permission_enforcement"]["client_review"] = {
    "options": {"escalations": "client"}, "applies_to": "a session with mars/consent",
    "enforced_by": "sandbox+client", "runtime_mode": "workspace-write",
    "evidence": "profile: client_review"}

#: MARS (round 2 E, `consent::secret_read_deny`): agy refuses named files, by exact path, to
#: its file tools and its sandboxed shell, given as `mars/options.deny_read`.
PROFILES["antigravity"]["backend"]["contract"]["capabilities"]["permission_enforcement"][
    "secret_read_deny"] = {"option": "deny_read", "form": "absolute paths, no globs",
                           "evidence": "profile: secret_read_deny"}

#: MARS (owner decision 2026-11-11, `consent::execution_policies`): the interim host
#: development policy codex and antigravity declare; its container successor is unsupported.
for _rt, _mech in (("codex", "codex-acp session mode full-access (sandbox danger-full-access)"),
                   ("antigravity", "agy --dangerously-skip-permissions, without --sandbox")):
    PROFILES[_rt]["backend"]["contract"]["capabilities"]["permission_enforcement"][
        "execution_policies"] = {
            "host-development-unrestricted": {
                "options": {"execution_policy": "host-development-unrestricted"},
                "applies_to": "a session with mars/consent in mode task", "mechanism": _mech,
                "isolation": "host", "container": False, "enforced_by": "none",
                "temporary": True, "successor": "container-development-unrestricted"},
            "container-development-unrestricted": {
                "state": "unsupported", "why": "MARS cannot assign a container yet"}}

RUNTIMES = tuple(PROFILES)
