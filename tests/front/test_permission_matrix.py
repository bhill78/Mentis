"""The permission matrix on file against a fresh generation (`R3-mirror.md`, section 6): a Python rule
changed without Rust fails here. `crates/mentis-rules/tests/permitted_matrix.rs` holds Rust to the
same file."""

from __future__ import annotations

import hashlib
import json

from mentis import worker
from tools.r3 import permission_matrix as matrix


def test_the_file_is_a_fresh_generation():
    assert matrix.TARGET.read_text(encoding="utf-8") == matrix.render(matrix.generate())


def test_it_parses_and_covers_every_axis():
    held = json.loads(matrix.TARGET.read_text(encoding="utf-8"))
    shapes = held["shapes"]
    assert {s["scope"] for s in shapes} == {
        None, "", "worker", "organising", "intake", "manual-session", "transient-read",
        "no-such-scope", "it's a scope", "scöpe"}
    grants = [s["operations"] for s in shapes if s["scope"] == "worker"]
    assert None in grants and [] in grants
    assert len(grants) == 1 + 64 + 4
    assert set(worker.OPERATIONS) | set(worker.SESSION_ACTS) <= set(held["names"])


def test_every_scope_the_mirror_holds_may_ask_all_six_moved_reads():
    """Which is why the door's `permitted` refusal is unreachable today (section 5)."""
    moved = {"kinds", "capabilities", "history", "owner_decisions", "governed", "resolve"}
    held = json.loads(matrix.TARGET.read_text(encoding="utf-8"))
    for shape in held["shapes"]:
        assert moved <= set(held["results"][shape["permitted"]]), shape["scope"]


def test_a_sample_says_what_its_hash_says():
    held = json.loads(matrix.TARGET.read_text(encoding="utf-8"))
    assert len(held["samples"]) >= 40
    shapes = {(s["scope"], json.dumps(s["operations"])): s for s in held["shapes"]}
    for sample in held["samples"]:
        shape = shapes[(sample["scope"], json.dumps(sample["operations"]))]
        at = held["names"].index(sample["op"])
        digest = dict((n, d) for n, d in shape["refused"])[at]
        assert hashlib.sha256(sample["text"].encode("utf-8")).hexdigest() == digest


def test_a_real_refusal_is_a_permission_error_in_the_door_s_words():
    assert issubclass(worker.NotPermitted, PermissionError)
    allowed = worker.permitted("worker", None)
    assert "open_topic" not in allowed
    text = matrix.words("open_topic", "worker", None)
    assert text.startswith("'open_topic' is not admissible for this execution.")
    assert repr(sorted(allowed)) in text
