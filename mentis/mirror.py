"""The front's copy of the grant table: Python's half (`docs/rust/R3-mirror.md`).

`authority.py`'s table stays the only authority. This holds what is needed to
tell a front about it: a generation, whether a push has failed since the last
pull, and when a position or a pull was last answered, which is what a fence is
measured from. It exists only with a boot secret; Python alone has none of it.

Nothing here retries. A push that fails is failed: `down` makes the next position
tell the front to pull, and a change that removed or narrowed a grant waits out
any lease that could predate it.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import time
import urllib.parse
from typing import Any

#: The whole push, connect included. Windows takes 2-2.5 s to refuse a loopback
#: connect (`contracts/live-snapshot.md`), so a dead front costs this, not that.
PUSH_TIMEOUT = 0.5
#: How long a front may answer from a confirmation it sent, and the same plus a
#: margin for scheduling: `perf_counter` and Rust's `Instant` read one clock.
LEASE = 3.0
FENCE = LEASE + 0.1

SCHEMA = 1
PUSH_PATH = "/private/grants"
PULL_PATH = "/private/grants"
POSITION_PATH = "/private/grants/position"


def key_of(token: str) -> str:
    """What the mirror knows a grant by: nothing that can be presented."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mirrored(grant: dict[str, Any]) -> dict[str, Any] | None:
    """What a front holds of this grant, or None if it holds nothing and so
    forwards: Quick Ask's scope, a scope that isn't a string (Rust matches scopes
    by name) and `operations` that aren't null or a list of strings (`permitted`
    uses `in`, which would mean something else on a string)."""
    from mentis.worker import TRANSIENT_SCOPE
    scope, operations = grant.get("scope"), grant.get("operations")
    if not isinstance(scope, str) or scope == TRANSIENT_SCOPE:
        return None
    if operations is not None and not (
            isinstance(operations, list)
            and all(isinstance(name, str) for name in operations)):
        return None
    return {"corpus": grant["corpus"], "scope": scope,
            "operations": list(operations) if operations is not None else None}


class Mirror:
    """One boot's position. `authority._lock` guards all of it: the mutators hold
    that lock when they call `moved` and the routes when they call `pull` or
    `position`."""

    def __init__(self, corpus: str, answers_at: str, secret: str,
                 secret_header: str):
        self.corpus = corpus
        self.boot_id = secrets.token_hex(16)
        self.generation = 0
        self.down = False
        #: `perf_counter` when a confirmation was last answered, or never.
        self.last_confirmed: float | None = None
        self._target = urllib.parse.urlsplit(answers_at).port
        self._secret, self._secret_header = secret, secret_header

    def moved(self) -> tuple[int, float | None]:
        """The table changed, and what the front holds of it. Its generation, and
        the deadline a fence would wait for if this change's push fails: only a
        confirmation answered before now can give a lease on a table without it,
        and every such lease ends by `last_confirmed + LEASE`."""
        self.generation += 1
        return (self.generation,
                None if self.last_confirmed is None
                else self.last_confirmed + FENCE)

    def pull(self, grants: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """`GET /private/grants`, under the table's lock."""
        self.down = False
        self.last_confirmed = time.perf_counter()
        table = {}
        for token, grant in grants.items():
            view = mirrored(grant)
            if view is not None:
                table[key_of(token)] = view
        return {"schema": SCHEMA, "boot_id": self.boot_id,
                "generation": self.generation, "corpus": self.corpus,
                "grants": table}

    def position(self, pid: int) -> dict[str, Any]:
        """`GET /private/grants/position`, under the table's lock. Reads no record."""
        if not self.down:
            self.last_confirmed = time.perf_counter()
        return {"schema": SCHEMA, "boot_id": self.boot_id,
                "generation": self.generation, "down": self.down, "pid": pid}

    def push(self, generation: int, key: str,
             grant: dict[str, Any] | None) -> bool:
        """Tell the front, once, holding no table lock. Whether it said yes."""
        body = json.dumps({"schema": SCHEMA, "boot_id": self.boot_id,
                           "generation": generation, "key": key,
                           "grant": grant}).encode("utf-8")
        return self._post(body)

    def _post(self, body: bytes) -> bool:
        if self._target is None:
            return False
        deadline = time.perf_counter() + PUSH_TIMEOUT
        head = (f"POST {PUSH_PATH} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self._target}\r\n"
                f"{self._secret_header}: {self._secret}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n").encode("latin-1")
        try:
            with socket.create_connection(("127.0.0.1", self._target),
                                          timeout=PUSH_TIMEOUT) as sock:
                sock.settimeout(_left(deadline))
                sock.sendall(head + body)
                got = b""
                while True:
                    sock.settimeout(_left(deadline))
                    more = sock.recv(4096)
                    if not more:
                        break
                    got += more
        except (OSError, ValueError):
            return False
        status, _, answer = got.partition(b"\r\n\r\n")
        if not status.startswith(b"HTTP/1.1 200 "):
            return False
        try:
            return json.loads(answer) == {"ok": True}
        except ValueError:
            return False


def _left(deadline: float) -> float:
    left = deadline - time.perf_counter()
    if left <= 0:
        raise TimeoutError("the push's time ran out")
    return left
