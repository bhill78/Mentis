"""The permission matrix: `R3-mirror.md`, section 6. What `worker.permitted` says of every grant shape
and what the door says when it refuses, written where Rust's test and Python's can both hold it.

    python tools/r3/permission_matrix.py        write tests/front/permission_matrix.json
    python tools/r3/permission_matrix.py --check    exit 1 if the file differs from a fresh generation

One shape per line, so a changed rule shows as a diff of the shapes it changed. The `permitted` lists
are held once each in `results` and named by index, and every refused operation's text has its
SHA-256 beside the operation's index, which keeps the file under 2 MB. The texts themselves are in
`samples`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mentis.web import _routes  # noqa: E402
from mentis.worker import (AUTHORITY, OPERATIONS, SESSION_ACTS, NotPermitted,  # noqa: E402
                           TRANSIENT_SCOPE, SESSION_SCOPE, permitted)

TARGET = ROOT / "tests" / "front" / "permission_matrix.json"

#: The corpus the stand-in state owns, which the request doesn't name.
CORPUS = "C:\b"
#: No grant for this corpus at all.
NO_GRANT = object()

#: The axes, exactly as section 6 has them.
SCOPES = [None, "", "worker", "organising", "intake", SESSION_SCOPE, TRANSIENT_SCOPE,
          "no-such-scope", "it's a scope", "scöpe"]

NAMES = list(OPERATIONS) + list(SESSION_ACTS) + ["", "no_such_op", "it's_an_op", "öp"]


def _grants() -> list[list[str] | None]:
    subsets = [list(chosen) for size in range(len(AUTHORITY) + 1)
               for chosen in itertools.combinations(AUTHORITY, size)]
    assert len(subsets) == 64
    # `[]` is both its own row in the document's table and the empty subset. It is one shape.
    return [None, *subsets, ["delegate"], ["resolve_intake"], ["deep_dive"], ["no_such_operation"]]


def _door(scope, grant, op):
    """The real door, `_routes`' `/api/worker` branch, on a table holding this one grant. The words
    are the door's own and nothing here restates them; a shape it would admit returns `None`."""
    state = types.SimpleNamespace(
        cv=None, corpus=None, brain=None, path=CORPUS,
        agents=types.SimpleNamespace(authority=types.SimpleNamespace(
            grant_for=lambda presented, path: (
                None if grant is NO_GRANT else {"scope": scope, "operations": grant}))))
    try:
        _routes(state, "/api/worker", {}, {"op": op}, "POST", "a-token")
    except PermissionError as refused:
        return type(refused), str(refused)
    return None


def words(op: str, scope: str | None, grant) -> str:
    """What the door says refusing `op` under this grant. Raises what isn't such a refusal."""
    kind, text = _door(scope, grant, op)
    assert kind is NotPermitted
    return text


def _handler_still_says_this() -> None:
    """The 403's body is `_Handler`'s, which needs a socket, so its source is what is asked."""
    source = (ROOT / "mentis" / "web" / "__init__.py").read_text(encoding="utf-8")
    said = "\n".join(["except PermissionError as exc:",
                      '            return self._send(403, {"error": str(exc),',
                      '                                    "kind": "PermissionError"})'])
    assert said in source, "the 403's body changed: change Rust's `refused_body` as well"


def _sampled(scope, grant, op) -> bool:
    """A sample of the refusals in full: every scope, for three grants and four operations."""
    return (grant in (None, [], ["coordinate"])
            and op in ("open_topic", "respond", "it's_an_op", "öp"))


def generate() -> dict:
    _handler_still_says_this()
    assert issubclass(NotPermitted, PermissionError)
    results: list[list[str]] = []
    shapes = []
    samples = []
    for scope, grant in itertools.product(SCOPES, _grants()):
        allowed = permitted(scope, grant)
        listed = list(allowed)
        if listed not in results:
            results.append(listed)
        refused = []
        for at, op in enumerate(NAMES):
            if op in allowed:
                continue
            text = words(op, scope, grant)
            refused.append([at, hashlib.sha256(text.encode("utf-8")).hexdigest()])
            if _sampled(scope, grant, op):
                samples.append({"scope": scope, "operations": grant, "op": op, "text": text,
                                "body": json.dumps({"error": text, "kind": "PermissionError"},
                                                   default=str)})
        shapes.append({"scope": scope, "operations": grant,
                       "permitted": results.index(listed), "refused": refused})
    kind, other = _door(None, NO_GRANT, "resolve")
    assert kind is PermissionError
    return {"names": NAMES, "results": results, "shapes": shapes, "samples": samples,
            "other_corpus": {"text": other,
                             "body": json.dumps({"error": other, "kind": "PermissionError"},
                                                default=str)}}


def render(matrix: dict) -> str:
    """One JSON document, one shape to a line."""
    def lines(items):
        return ",\n".join(json.dumps(item) for item in items)
    return ("{\n"
            f'"names": {json.dumps(matrix["names"])},\n'
            f'"other_corpus": {json.dumps(matrix["other_corpus"])},\n'
            f'"results": [\n{lines(matrix["results"])}\n],\n'
            f'"shapes": [\n{lines(matrix["shapes"])}\n],\n'
            f'"samples": [\n{lines(matrix["samples"])}\n]\n'
            "}\n")


def main() -> int:
    fresh = render(generate())
    if "--check" in sys.argv[1:]:
        return 0 if TARGET.read_text(encoding="utf-8") == fresh else 1
    TARGET.write_text(fresh, encoding="utf-8", newline="\n")
    print(f"{TARGET}: {len(fresh):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
