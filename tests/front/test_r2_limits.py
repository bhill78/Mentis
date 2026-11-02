"""R2: an engine limit, end to end. A bundle that never ends and one that takes all the memory, served
to both sides from one dist. The words a limit is answered with hold Python's own exception, so Rust's
engine stops and the front forwards: the answer must be Python's, byte for byte, and quickly enough to
show the limit ended it.
"""

from __future__ import annotations

import shutil
import time

import pytest

from tests.front.pair import CLIENT, PY_PORT, SPARE_PORTS, Pair, ask
from tests.front.test_r2_window import World, _post_ids
from tools.r1 import common, py_alone

PAIR_PORT = SPARE_PORTS[0]
BUNDLES = {
    "time": "var MentisRenderCheck = {extractPost: function () { while (true) {} }};",
    "memory": "var MentisRenderCheck = {extractPost: function () {"
              " var all = []; while (true) { all.push(new Array(100000).fill(1)); } }};",
}


@pytest.fixture(scope="module", params=sorted(BUNDLES))
def world(request, brain_seed, tmp_path_factory):
    dist = tmp_path_factory.mktemp("dist") / "dist"
    shutil.copytree(common.dist_dir(), dist)
    (dist / "render-check.js").write_text(BUNDLES[request.param], encoding="utf-8")
    py_copy = tmp_path_factory.mktemp("py") / "brain"
    pair_copy = tmp_path_factory.mktemp("pair") / "brain"
    shutil.copytree(brain_seed, py_copy)
    shutil.copytree(brain_seed, pair_copy)
    with py_alone.running(py_copy, port=PY_PORT, code=common.REPO, dist=dist):
        with Pair(pair_copy, port=PAIR_PORT, dist=dist) as pair:
            yield World(PY_PORT, pair, pair_copy)


def test_a_limit_is_answered_in_python_s_words(world):
    post = _post_ids(world)[0]
    target = f"/fluid/api/objects?post={post}"
    theirs = ask(world.py_port, "GET", target, headers=CLIENT, wait=60.0)
    started = time.monotonic()
    ours = ask(world.pair.port, "GET", target, headers=CLIENT, wait=60.0)
    took = time.monotonic() - started
    assert ours.comparable == theirs.comparable
    assert ours.status == 200
    assert ours.json["extracted"] is False
    assert "extraction failed" in ours.json["why_not"]
    # Rust's engine's limit, then Python's: each at most a few seconds, however long the call would go.
    assert took < 30, took


def test_the_next_read_after_a_limit_still_answers(world):
    posts = _post_ids(world)
    for post in posts[:2]:
        target = f"/fluid/api/objects?post={post}"
        got = ask(world.pair.port, "GET", target, headers=CLIENT, wait=60.0)
        assert got.status == 200
        assert got.json["extracted"] is False
    conversation = ask(world.pair.port, "GET", f"/fluid/api/posts?ids={posts[0]}", headers=CLIENT)
    assert conversation.status == 200
