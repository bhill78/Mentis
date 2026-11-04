"""R4.1's routes over what the master doesn't hold, written on a copy by Python's own functions.

A reaction changed, withdrawn, deleted by somebody else or generically superseded; an edited or deleted
post under an anchor; own words and an interpretation; asks reassigned, withdrawn and left on a deleted
post; a renamed Conversation, Topic and Participant; a picture whose bytes are gone or changed; two
designations standing. `routes_diff.shapes` writes them, and `routes_diff.run` compares every family with
every other row of the copy: wire bytes, key order included.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3

import pytest

from tests.front.pair import SPARE_PORTS, _template
from tools.r1 import common
from tools.r4 import routes_diff

BASE = SPARE_PORTS[0]


@pytest.fixture(scope="module")
def shaped(tmp_path_factory):
    where = tmp_path_factory.mktemp("r41shapes")
    brain = where / "brain"
    written = routes_diff.shapes(common.master_dir(), brain)
    # Python refuses a blank; nothing else it refused would leave a shape untested.
    assert {name for name, (state, _) in written.items() if state == "refused"} == {"own words, blank"}, written
    binary = pathlib.Path(_template()[0]).with_name("mentis-server.exe")
    status = routes_diff.run(argparse.Namespace(
        copy=str(brain), out=str(where / "run"), front=str(binary), families=None, sample=30, port_base=BASE))
    report = json.loads((where / "run" / "report.json").read_text(encoding="utf-8"))
    differences = (where / "run" / "differences.jsonl").read_text(encoding="utf-8")
    return brain, status, report, differences


def test_every_family_is_python_s_answer_on_every_shape(shaped):
    _, status, report, differences = shaped
    assert status == 0 and not differences, differences[:2000]
    assert report.pop("_record_unchanged") is True
    assert sum(tally["requests"] for tally in report.values()) > 1000


def test_what_used_to_forward_for_a_picture_is_answered(shaped):
    _, _, report, _ = shaped
    tally = report["api-participants"]
    # What forwards is what Python raises on (`limit=-1`, `limit=abc`), never a picture.
    assert tally["forwarded"] <= 2 and tally["answered"] >= 30, tally


def test_the_shapes_are_on_the_routes_that_read_them(shaped):
    brain, _, report, _ = shaped
    db = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        acts = dict(db.execute("SELECT act, COUNT(*) FROM operational GROUP BY act").fetchall())
    finally:
        db.close()
    for act in ("reaction-changed", "material-deleted", "expectation-assigned", "participant-renamed",
                "conversation-renamed", "turn-edited", "turn-deleted"):
        assert acts.get(act), act
    # A generic supersession of a reaction is Python's to say: its post forwards, and matches.
    assert report["post-anchors"]["forwarded"] >= 1
    # An interpretation's view reads the block through the engine: that accounting forwards.
    assert report["response-accounting"]["forwarded"] >= 2
