"""What MCP servers a dispatched execution is given, stated to MARS (O8, WS-M).

Every dispatched run states its MCP configuration explicitly, as session/new
`_meta["mars/mcp"]` (MARS docs/API.md "MCP assembly"), rather than leaving it to
each runtime's implicit loading of the owner's user-level registrations:

- the run's own `mcpServers`: the Mentis bridge for THIS Brain under THIS run's
  grant (`AgentService.mcp_servers_for`);
- `intended`: the Brain, server and execution that bridge is for, so MARS can
  tell the owner's other registrations apart -- a bridge to another Brain, or to
  this one outside the run's grant, is excluded, not started;
- `user`: the owner's policy for the runtime's user-level MCP servers;
- `mentis_servers`: addresses that are Mentis servers, so a registration that
  reaches one under an innocent name is recognised too.

MARS answers with `_meta["mars/mcp"]` -- given, excluded (with reason),
unavailable -- which Mentis records in the run's evidence (`runtime_evidence.mcp`)
and tells the agent in its tooling block.

THE OWNER'S POLICY is one file beside the record, edited by hand:

    <brain>/mcp-policy.json
    {"format": "mentis.mcp-policy", "version": 1,
     "user_servers": {"default": "allow" | "deny",
                      "allow": [...], "deny": [...], "other_brains": [...]},
     "mentis_servers": ["127.0.0.1:9000", ...]}   # ADDED to DEFAULT_MENTIS_SERVERS

Each list names a server as `name` (every runtime) or `runtime:name` (one
runtime, e.g. `codex:docs`). `default` is `allow`: every non-Mentis user-level
server the runtime would load is given, so nothing the owner made available is
silently removed. `deny` takes one away; with `default: deny` only `allow`ed ones
are given. A registration that reaches a Mentis surface is excluded unless named
in `other_brains` -- the owner's explicit path to give runs another Brain.

No file is the default. A file that cannot be read as this format FAILS CLOSED
for user servers (`default: deny`, nothing allowed) and says why in the
statement (`policy_unreadable`), which MARS's report then shows as excluded:
an unreadable owner restriction is never read as permission.
"""

from __future__ import annotations

import json
import os
from typing import Any

FILE = "mcp-policy.json"
FORMAT = "mentis.mcp-policy"
VERSION = 1
#: The Mentis servers of this installation that a registration could reach by
#: address: DAY-TO-DAY's front and back, the Mark III surface and its sibling,
#: and the Quiet Chat dev server. The run's own server is always added.
DEFAULT_MENTIS_SERVERS = ("127.0.0.1:8760", "127.0.0.1:18760", "127.0.0.1:8770",
                          "127.0.0.1:8773", "127.0.0.1:8790")
_LISTS = ("allow", "deny", "other_brains")


def _strings(value, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where} must be a list of names")
    return list(value)


def read_policy(brain: str | None) -> tuple[dict[str, Any], str | None]:
    """(the owner's policy, why the file is unreadable or None)."""
    default = {"user": {"default": "allow"},
               "mentis_servers": list(DEFAULT_MENTIS_SERVERS)}
    if not brain:
        return default, None
    path = os.path.join(brain, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return default, None
    except (OSError, ValueError, RecursionError) as exc:
        return _closed(f"{FILE} could not be read ({type(exc).__name__})"), f"{FILE} could not be read"
    try:
        if not isinstance(data, dict) or data.get("format") != FORMAT \
                or data.get("version") != VERSION:
            raise ValueError(f"it is not {FORMAT} version {VERSION}")
        unknown = set(data) - {"format", "version", "user_servers", "mentis_servers"}
        if unknown:
            raise ValueError(f"unknown keys {sorted(unknown)}")
        user = data.get("user_servers") or {}
        if not isinstance(user, dict) or set(user) - {"default", *_LISTS}:
            raise ValueError("user_servers must be an object of default/allow/deny/other_brains")
        mode = user.get("default", "allow")
        if mode not in ("allow", "deny"):
            raise ValueError("user_servers.default must be \"allow\" or \"deny\"")
        policy = {"default": mode}
        for key in _LISTS:
            names = _strings(user.get(key), f"user_servers.{key}")
            if names:
                policy[key] = names
        # THE OWNER'S LIST ADDS TO THE DEFAULTS (review L2): naming one more
        # Mentis address never stops this installation's own surfaces from
        # being recognised as Mentis (and so kept from runs).
        servers = list(dict.fromkeys([*DEFAULT_MENTIS_SERVERS,
                                      *_strings(data.get("mentis_servers"),
                                                "mentis_servers")]))
    except ValueError as exc:
        why = f"{FILE} is not an MCP policy: {exc}"
        return _closed(why), why
    return {"user": policy, "mentis_servers": servers}, None


def _closed(why: str) -> dict[str, Any]:
    return {"user": {"default": "deny"},
            "mentis_servers": list(DEFAULT_MENTIS_SERVERS),
            "policy_unreadable": why}


def statement(*, brain: str | None, server: str | None, execution: str) -> dict[str, Any]:
    """`_meta["mars/mcp"]` for one execution."""
    policy, _why = read_policy(brain)
    out: dict[str, Any] = {
        "user": dict(policy["user"]),
        "intended": {k: v for k, v in (("brain", brain), ("server", server),
                                       ("execution", execution)) if v},
        "mentis_servers": list(policy["mentis_servers"]),
    }
    if policy.get("policy_unreadable"):
        # Said to MARS too (an unknown member it ignores), and kept in the
        # run's evidence through the statement.
        out["policy_unreadable"] = policy["policy_unreadable"]
    return out


def given_names(report: dict | None) -> list[str] | None:
    """The servers MARS says the session was given, or None when it did not say."""
    if not isinstance(report, dict) or not isinstance(report.get("given"), list):
        return None
    return sorted({g.get("name") for g in report["given"]
                   if isinstance(g, dict) and isinstance(g.get("name"), str)})


def summary(report: dict | None, stated: dict | None = None) -> dict[str, Any] | None:
    """What the run record keeps of MARS's `mars/mcp` answer: given, excluded
    (with reason) and unavailable, and the policy's state when it was unreadable."""
    if not isinstance(report, dict):
        if stated is None:
            return None
        return {"reported": False,
                "why": "this MARS did not report the session's MCP servers",
                **({"policy_unreadable": stated["policy_unreadable"]}
                   if stated.get("policy_unreadable") else {})}

    def rows(key, fields):
        return [{f: e.get(f) for f in fields if e.get(f) is not None}
                for e in report.get(key) or () if isinstance(e, dict)]
    out = {"reported": True,
           "enforcement": report.get("enforcement"),
           "given": rows("given", ("name", "source", "scope", "how", "mentis", "note")),
           "excluded": rows("excluded", ("name", "scope", "file", "reason", "detail",
                                         "replaced_by_client")),
           "unavailable": rows("unavailable", ("name", "scope", "file", "why"))}
    if isinstance(report.get("also_loaded_by_runtime"), str):
        out["also_loaded_by_runtime"] = report["also_loaded_by_runtime"]
    if stated and stated.get("policy_unreadable"):
        out["policy_unreadable"] = stated["policy_unreadable"]
    return out
