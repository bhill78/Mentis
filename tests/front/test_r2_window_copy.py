"""R2 on BRAIN-COPY: every post, thread and conversation of a real Brain, against this commit's Python.

`test_r2_window.py` holds what a small seed can be made to show; this is what only the real record
holds: edited versions and inclusions in numbers, the long conversation, text of every kind. The two
sides have a copy each. A fresh copy costs about a minute, so it's a module of its own.

**The objects sweeps are sampled, by `MENTIS_R2_SAMPLE`, every Nth batch, post and thread (default 10);
1 asks all of it.** Python's cold read of one post's objects is about 290 ms, so one post at a time over
the whole copy, asked twice, takes hours. `tools/r2/js_gate.py` covers every version's extraction.
"""

from __future__ import annotations

import os
import urllib.parse

import pytest

from tests.front.pair import CLIENT, PY_PORT, SPARE_PORTS, Pair, ask, process_tree, resume, rows, \
    suspend
from tests.front.test_r2_window import World, _batches, _conversations, _post_ids, _roots
from tools.r1 import common, copy_brain, py_alone

PAIR_PORT = SPARE_PORTS[0]
MANIFEST = common.EVIDENCE / "brain-copy-manifest.json"
#: One post in this many has each of its objects read at both addresses in each format.
ADDRESS_SAMPLE = 25
SAMPLE = int(os.environ.get("MENTIS_R2_SAMPLE") or 10)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    py_copy = copy_brain.fresh(tmp_path_factory.mktemp("py") / "brain", common.master_dir(), MANIFEST)
    pair_copy = copy_brain.fresh(tmp_path_factory.mktemp("pair") / "brain", common.master_dir(),
                                 MANIFEST)
    with py_alone.running(py_copy, port=PY_PORT, code=common.REPO):
        with Pair(pair_copy, port=PAIR_PORT) as pair:
            yield World(PY_PORT, pair, pair_copy)


def _relation(world, role: str) -> str:
    return rows(world.brain, "SELECT json_extract(body, '$.relation') FROM entry "
                             "WHERE family = 'definition' AND json_extract(body, '$.substrate_role') = ? "
                             "ORDER BY seq LIMIT 1", role)[0][0]


def test_the_copy_holds_what_it_is_here_to_show(world):
    posts = []
    for batch in _batches(_post_ids(world)):
        posts.extend(ask(world.pair.port, "GET", "/fluid/api/posts?ids=" + ",".join(batch),
                         headers=CLIENT, wait=60.0).json["posts"])
    assert len(posts) > 5000
    assert any((p.get("versions") or 1) > 1 for p in posts), "edited posts"
    assert any(p.get("deleted") for p in posts), "deleted posts"
    assert rows(world.brain, "SELECT 1 FROM entry WHERE link_relation = 'linked-into' LIMIT 1"), \
        "inclusions"


def test_every_post(world):
    for batch in _batches(_post_ids(world)):
        got = world.same("/fluid/api/posts?ids=" + ",".join(batch))
        assert got.status == 200
        assert [p["id"] for p in got.json["posts"]] == batch


def test_every_post_with_its_thread(world):
    for batch in _batches(_post_ids(world)):
        assert world.same("/fluid/api/posts?ids=" + ",".join(batch) + "&thread=1").status == 200


@pytest.mark.parametrize("shape", ["threads", "posts"])
def test_every_conversation_every_page(world, shape):
    for conversation in _conversations(world):
        got = world.same(f"/fluid/api/collections/conversation?id={conversation}&shape={shape}"
                         "&limit=50")
        if got.status != 200:
            continue
        before = got.json.get("before")
        while before:
            page = world.same(f"/fluid/api/collections/conversation?id={conversation}&shape={shape}"
                              f"&limit=50&before={urllib.parse.quote(before)}")
            assert page.status == 200
            before = page.json.get("before")
        got = world.same(f"/fluid/api/collections/conversation?id={conversation}&shape={shape}"
                         "&limit=50&from=start")
        after = got.json.get("after")
        while after:
            page = world.same(f"/fluid/api/collections/conversation?id={conversation}&shape={shape}"
                              f"&limit=50&after={urllib.parse.quote(after)}")
            assert page.status == 200
            after = page.json.get("after")


def test_every_conversation_an_inclusion_is_in(world):
    """Inclusions, whichever Conversation shows them, read from where they are included."""
    included = rows(world.brain, "SELECT DISTINCT link_from, link_to FROM entry "
                                 "WHERE link_relation = 'linked-into' ORDER BY seq")
    assert included
    for post, conversation in included:
        world.same(f"/fluid/api/posts?ids={post}&thread=1")
        world.same(f"/fluid/api/collections/conversation?id={conversation}&from={post}&limit=5")
        world.same(f"/fluid/api/collections/conversation?id={conversation}&before={post}&limit=5")
        world.same(f"/fluid/api/objects?post={post}")


def test_every_thread(world):
    roots = _roots(world)
    assert roots
    for root in roots:
        got = world.same(f"/fluid/api/collections/thread?root={root}&limit=50")
        before = got.json.get("before") if got.status == 200 else None
        while before:
            page = world.same(f"/fluid/api/collections/thread?root={root}&limit=50"
                              f"&before={urllib.parse.quote(before)}")
            assert page.status == 200
            before = page.json.get("before")


def test_every_post_s_objects_in_batches(world):
    for batch in _batches(_post_ids(world))[::SAMPLE]:
        assert world.same("/fluid/api/objects?posts=" + ",".join(batch)).status == 200


def test_every_thread_and_conversation_s_objects(world):
    for root in _roots(world)[::SAMPLE * 10]:
        world.same(f"/fluid/api/objects?thread={root}")
    for at, conversation in enumerate(_conversations(world)):
        got = world.same(f"/fluid/api/objects?conversation={conversation}&limit=50")
        before = got.json.get("before") if got.status == 200 else None
        while before and at % SAMPLE == 0:
            page = world.same(f"/fluid/api/objects?conversation={conversation}&limit=50"
                              f"&before={urllib.parse.quote(before)}")
            assert page.status == 200
            before = page.json.get("before")


def test_every_post_alone_and_a_sample_of_its_objects(world):
    for at, post in enumerate(_post_ids(world)[::SAMPLE * 4]):
        got = world.same(f"/fluid/api/objects?post={post}")
        if at % ADDRESS_SAMPLE or got.status != 200:
            continue
        for listed in got.json.get("objects") or []:
            for form in ("exact", "live"):
                address = urllib.parse.quote(listed["address"][form], safe="")
                world.same(f"/fluid/api/objects/{address}")
                for fmt in ("md", "csv"):
                    world.same(f"/fluid/api/objects/{address}?format={fmt}")


def test_every_edited_version(world):
    edited = rows(world.brain, """
        SELECT l.link_from, l.link_to FROM entry l JOIN entry e ON e.id = l.link_to
        WHERE l.link_relation = ? AND e.def_name = 'contribution' ORDER BY l.seq""",
                  _relation(world, "supersedes"))
    assert edited
    for newer, older in edited:
        world.same(f"/fluid/api/posts?ids={older},{newer}&thread=1")
        world.same(f"/fluid/api/objects?post={older}")
        world.same(f"/fluid/api/objects?post={older}&version={older}")
        world.same(f"/fluid/api/objects?post={older}&version={newer}")
        got = world.same(f"/fluid/api/objects?post={newer}&version={older}")
        for listed in (got.json.get("objects") or [])[:3] if got.status == 200 else []:
            address = urllib.parse.quote(listed["address"]["exact"], safe="")
            world.same(f"/fluid/api/objects/{address}")


def test_the_long_conversation_is_answered_with_python_suspended(world):
    """The busiest Conversation, with nothing behind the front to forward to: Rust's own answers."""
    counted = rows(world.brain, "SELECT link_to, COUNT(*) AS n FROM entry "
                                "WHERE link_relation = 'in-conversation' GROUP BY link_to "
                                "ORDER BY n DESC LIMIT 1")
    home = counted[0][0]
    posts = _post_ids(world)
    targets = [f"/fluid/api/collections/conversation?id={home}",
               f"/fluid/api/collections/conversation?id={home}&shape=posts&limit=50",
               f"/fluid/api/objects?conversation={home}&limit=50",
               "/fluid/api/posts?ids=" + ",".join(posts[-64:]) + "&thread=1",
               "/fluid/api/objects?posts=" + ",".join(posts[-64:])]
    wanted = {target: world.same(target) for target in targets}
    tree = process_tree(world.pair.python_pid)
    assert tree
    for pid in tree:
        suspend(pid)
    try:
        for target in targets:
            got = ask(world.pair.port, "GET", target, headers=CLIENT, wait=30.0)
            assert got.status == 200, f"{target}: {got}"
            assert got.body == wanted[target].body, target
    finally:
        for pid in tree:
            resume(pid)


def test_a_window_read_on_the_copy_writes_nothing(world):
    query = ("SELECT (SELECT MAX(seq) FROM entry), (SELECT MAX(seq) FROM operational),"
             " (SELECT MAX(seq) FROM delivery)")
    before = rows(world.brain, query)
    for post in _post_ids(world)[:50]:
        ask(world.pair.port, "GET", f"/fluid/api/objects?post={post}", headers=CLIENT)
    assert rows(world.brain, query) == before
