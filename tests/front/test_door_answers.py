"""Each moved read, through a real front, equal to Python alone. `R3-mirror.md`, section 8.

Byte equality of each read's body, kind by kind, is `crates/mentis-server/tests/worker_reads.rs`. This
is the same comparison across the wire: status, headers and JSON, per grant shape.
"""

from __future__ import annotations

import json
import socket

from tests.front.mirror_harness import read_answer, worker_request, world
from tests.front.test_mirror_protocol import _answered_count

READS = [
    ("capabilities", {}),
    ("kinds", {}),
    ("history", {}),
    ("history", {"limit": 3}),
    ("history", {"since": "x"}),
    ("history", {"set": "ent-nothing"}),
    ("owner_decisions", {}),
    ("owner_decisions", {"conversation": "ent-nothing"}),
    ("governed", {}),
    ("governed", {"kind": "rule", "limit": 3}),
    ("governed", {"state": "not-a-state"}),
    ("resolve", {"ref": "ent-nothing"}),
]


def _whole(port: int, token: str, op: str, args: dict) -> tuple[list[str], bytes]:
    """The status line and each header but `Date` and `Server`'s time, and the body."""
    with socket.create_connection(("127.0.0.1", port), timeout=60) as sock:
        sock.sendall(worker_request(port, token, op, args))
        got = b""
        while b"\r\n\r\n" not in got:
            got += sock.recv(1 << 20)
        head, _, rest = got.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        length = next(int(line.split(":")[1]) for line in lines
                      if line.lower().startswith("content-length"))
        while len(rest) < length:
            rest += sock.recv(1 << 20)
    return [line for line in lines if not line.lower().startswith("date:")], rest


def test_every_moved_read_is_the_same_through_the_front(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        answered = _answered_count(w)
        by_front = 0
        for op, args in READS:
            direct = _whole(w.private, w.token, op, args)
            before = _answered_count(w)
            through = _whole(w.public, w.token, op, args)
            by_front += _answered_count(w) - before
            if op == "kinds":
                # `as_read_at` is the moment, and nothing else in it may differ.
                direct_body = json.loads(direct[1])
                through_body = json.loads(through[1])
                direct_body.pop("as_read_at"), through_body.pop("as_read_at")
                assert (direct[0][0], direct_body) == (through[0][0], through_body)
            else:
                assert direct == through, (op, args)
        assert by_front > len(READS) / 2, f"only {by_front} of {len(READS)} were the front's"
        assert answered < _answered_count(w)
        print(f"\nanswered by the front: {by_front} of {len(READS)}")


def test_a_read_on_a_real_reference_of_each_kind_is_the_same(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        # What `history` names is real on this Brain, so `resolve` has something to say of it.
        with socket.create_connection(("127.0.0.1", w.private), timeout=60) as sock:
            sock.sendall(worker_request(w.private, w.token, "history", {"limit": 40}))
            _, body = read_answer(sock)
        refs = set()
        for act in json.loads(body).get("acts", []):
            for field in ("id", "actor", "conversation", "turn"):
                if isinstance(act.get(field), str):
                    refs.add(act[field])
        assert refs
        by_front = 0
        for ref in sorted(refs):
            direct = _whole(w.private, w.token, "resolve", {"ref": ref})
            before = _answered_count(w)
            through = _whole(w.public, w.token, "resolve", {"ref": ref})
            by_front += _answered_count(w) - before
            assert direct == through, ref
        print(f"\nresolve answered by the front: {by_front} of {len(refs)}")
