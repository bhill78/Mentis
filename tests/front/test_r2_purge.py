"""R2: a purge as each side reads it, on one BRAIN-SEED. Its own module, so that its own two processes
have read nothing but what it asks: what a process has already read is the question.

`r2_side.py` attaches before the copies are made, so both sides hold one record, and purges each copy.
"""

from __future__ import annotations

import json
import shutil
import urllib.parse

import pytest

from tests.front.pair import CLIENT, PY_PORT, SPARE_PORTS, Pair, ask
from tests.front.test_r2_window import _side
from tools.r1 import common, py_alone

R2_SIDE = common.REPO / "tests" / "front" / "r2_side.py"
PAIR_PORT = SPARE_PORTS[0]
WAIT_S = 30.0


class World:
    def __init__(self, py_port, pair, brain, py_brain, attached):
        self.py_port, self.pair, self.brain = py_port, pair, brain
        self.py_brain, self.attached = py_brain, attached


@pytest.fixture(scope="module")
def world(brain_seed, tmp_path_factory):
    changed = tmp_path_factory.mktemp("changed") / "brain"
    shutil.copytree(brain_seed, changed)
    attached = json.loads(_side(R2_SIDE, "attach", changed))
    py_copy = tmp_path_factory.mktemp("py") / "brain"
    pair_copy = tmp_path_factory.mktemp("pair") / "brain"
    shutil.copytree(changed, py_copy)
    shutil.copytree(changed, pair_copy)
    with py_alone.running(py_copy, port=PY_PORT, code=common.REPO):
        with Pair(pair_copy, port=PAIR_PORT) as pair:
            yield World(PY_PORT, pair, pair_copy, py_copy, attached)


def _media(world, port, post) -> dict:
    """The post's attachment as its listing has it, and as the object's own address reads it now."""
    listing = ask(port, "GET", f"/fluid/api/objects?post={post}", headers=CLIENT, wait=WAIT_S)
    assert listing.status == 200, listing
    listed = [o for o in listing.json["objects"] if o.get("kind") == "media"]
    assert len(listed) == 1, listing
    address = urllib.parse.quote(listed[0]["address"]["live"], safe="")
    one = ask(port, "GET", f"/fluid/api/objects/{address}", headers=CLIENT, wait=WAIT_S)
    assert one.status == 200, one
    # What's in the listing, with this post's own ids out of it.
    shown = json.loads(json.dumps(listed[0]).replace(post, "POST"))
    return {"listed": shown, "cached": listing.json["cached"],
            "now": one.json["object"]["artifact"]["state"]}


def test_a_purge_as_each_side_reads_it(world):
    """A purge changes what an artifact is, and an extraction's key is the version, what was returned
    and the bundle, so an extraction held from before a purge goes on being answered, on both sides.
    What's asserted here is what each process does and that the two do it alike, read before the purge
    and first read after it, and that a state asked for is read now."""
    a = world.attached
    sides = {"python": world.py_port, "rust": world.pair.port}
    before = {name: _media(world, port, a["read_before"]) for name, port in sides.items()}
    assert before["rust"] == before["python"]
    assert before["rust"]["now"] == "held"
    for brain in (world.py_brain, world.brain):
        assert json.loads(_side(R2_SIDE, "purge", brain, a["ref"]))["state"] == "purged"
    kept = {name: _media(world, port, a["read_before"]) for name, port in sides.items()}
    first = {name: _media(world, port, a["read_after"]) for name, port in sides.items()}
    assert kept["rust"] == kept["python"]
    assert first["rust"] == first["python"]
    for name in sides:
        # An extraction from before the purge is answered from where it's held.
        assert kept[name]["cached"] is True
        assert first[name]["cached"] is False
        # Whatever asks the state reads it now.
        assert kept[name]["now"] == "purged"
        assert first[name]["now"] == "purged"
        # And for an attachment, holding the extraction costs nothing: it doesn't say the state.
        assert kept[name]["listed"] == first[name]["listed"]
