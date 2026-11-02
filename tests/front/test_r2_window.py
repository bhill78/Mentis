"""R2: the post window against Python's own answers, on one changed BRAIN-SEED.

The seed is changed by Python's commands (`crates/mentis-rules/tests/support/python_side.py change`),
so it holds edited and deleted posts. It is then copied, and THIS COMMIT'S Python answers on one copy
and the pair on the other: the same record, so the same ids, positions and cursors.

Every read is asked of each side twice and the second answers compared, byte for byte but for `Date`,
because `cached` says what that process has already read. A cold answer is compared with `cached`
taken out. A difference fails: a known difference is a defect here, not an entry on a list
(`AGENTS.md`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse

import pytest

from tests.front.pair import (CLIENT, PY_PORT, SPARE_PORTS, Answer, Pair, ask, exchange, post_json,
                              request, rows)
from tools.r1 import common, py_alone

PAIR_PORT = SPARE_PORTS[0]
SIDE = common.REPO / "crates" / "mentis-rules" / "tests" / "support" / "python_side.py"


class World:
    def __init__(self, py_port, pair, brain):
        self.py_port, self.pair, self.brain = py_port, pair, brain

    def both(self, target: str) -> tuple[Answer, Answer]:
        data = request("GET", target, headers=CLIENT)
        return (Answer(exchange(self.py_port, data, wait=30.0)),
                Answer(exchange(self.pair.port, data, wait=30.0)))

    def same(self, target: str) -> Answer:
        """The second answer from each, whole, so what they've read before can't differ."""
        self.both(target)
        theirs, ours = self.both(target)
        assert ours.comparable == theirs.comparable, target
        return ours


@pytest.fixture(scope="module")
def world(brain_seed, tmp_path_factory):
    changed = tmp_path_factory.mktemp("changed") / "brain"
    shutil.copytree(brain_seed, changed)
    done = subprocess.run([str(common.venv_python()), str(SIDE), "change", str(changed)],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env={"PYTHONPATH": str(common.REPO), "PYTHONDONTWRITEBYTECODE": "1",
                               "PYTHONIOENCODING": "utf-8", **_system_environment()})
    assert done.returncode == 0, done.stderr
    py_copy = tmp_path_factory.mktemp("py") / "brain"
    pair_copy = tmp_path_factory.mktemp("pair") / "brain"
    shutil.copytree(changed, py_copy)
    shutil.copytree(changed, pair_copy)
    with py_alone.running(py_copy, port=PY_PORT, code=common.REPO):
        with Pair(pair_copy, port=PAIR_PORT) as pair:
            yield World(PY_PORT, pair, pair_copy)


def _system_environment() -> dict:
    import os
    return {name: os.environ[name] for name in ("SYSTEMROOT", "PATH", "TEMP", "TMP")
            if name in os.environ}


def _post_ids(world) -> list[str]:
    return [row[0] for row in rows(world.brain, """
        SELECT DISTINCT e.id FROM entry e JOIN entry l
          ON l.link_from = e.id AND l.link_relation = 'in-conversation'
        WHERE e.family = 'entry' AND e.def_name = 'contribution' AND e.link_relation IS NULL
        ORDER BY e.seq""")]


def _conversations(world) -> list[str]:
    return [row[0] for row in rows(world.brain, """
        SELECT id FROM entry WHERE family = 'entry' AND def_name = 'conversation'
          AND link_relation IS NULL ORDER BY seq""")]


def _batches(ids: list[str], size: int = 64) -> list[list[str]]:
    return [ids[at:at + size] for at in range(0, len(ids), size)]


# -- posts --------------------------------------------------------------------------------------

def test_every_post_in_batches_and_alone(world):
    ids = _post_ids(world)
    assert ids
    for batch in _batches(ids):
        got = world.same("/fluid/api/posts?ids=" + ",".join(batch))
        assert got.status == 200
        assert [p["id"] for p in got.json["posts"]] == batch
    for post in ids[:30]:
        world.same(f"/fluid/api/posts?ids={post}")


def test_every_post_with_its_thread(world):
    seen_thread = False
    for batch in _batches(_post_ids(world)):
        got = world.same("/fluid/api/posts?ids=" + ",".join(batch) + "&thread=1")
        assert got.status == 200
        seen_thread = seen_thread or any(p.get("thread", {}).get("replies") for p in got.json["posts"])
    assert seen_thread, "the seed has replies, so a thread should have counted one"


def test_a_deleted_post_and_an_edited_one_read_as_python_says(world):
    answers = []
    for batch in _batches(_post_ids(world)):
        answers.extend(world.same("/fluid/api/posts?ids=" + ",".join(batch)).json["posts"])
    assert any(p.get("deleted") for p in answers), "the changed seed deletes a post"
    assert any((p.get("versions") or 1) > 1 for p in answers), "the changed seed edits a post"


@pytest.mark.parametrize("query", [
    "", "ids=", "ids=,", "ids=a/b", "ids=ent-000000000000", "ids=ent-000000000000,ent-111111111111",
    "ids=" + ",".join(f"i{n}" for n in range(65)), "ids=%ff", "ids=x&thread=0", "ids=x&thread=1",
    "ids=caf%C3%A9",
])
def test_posts_questions(world, query):
    world.same("/fluid/api/posts?" + query)


def test_things_that_are_not_posts(world):
    entry = rows(world.brain, "SELECT id FROM entry WHERE family = 'definition' LIMIT 1")[0][0]
    conversation = _conversations(world)[0]
    got = world.same(f"/fluid/api/posts?ids={entry},{conversation}")
    assert [p.get("error") for p in got.json["posts"]] == ["not a post", "not a post"]


# -- collections/conversation --------------------------------------------------------------------

@pytest.mark.parametrize("shape", ["threads", "posts"])
def test_every_conversation_pages_as_python_s(world, shape):
    for conversation in _conversations(world):
        first = world.same(f"/fluid/api/collections/conversation?id={conversation}&shape={shape}"
                           "&limit=2")
        assert first.status in (200, 400), first
        if first.status != 200:
            continue
        before = first.json.get("before")
        while before:
            quoted = urllib.parse.quote(before)
            page = world.same(f"/fluid/api/collections/conversation?id={conversation}"
                              f"&shape={shape}&limit=2&before={quoted}")
            assert page.status == 200
            before = page.json.get("before")
        forward = world.same(f"/fluid/api/collections/conversation?id={conversation}"
                             f"&shape={shape}&limit=2&from=start")
        after = forward.json.get("after")
        while after:
            quoted = urllib.parse.quote(after)
            page = world.same(f"/fluid/api/collections/conversation?id={conversation}"
                              f"&shape={shape}&limit=2&after={quoted}")
            assert page.status == 200
            after = page.json.get("after")


def test_a_conversation_paged_from_a_member_id(world):
    post = _post_ids(world)[0]
    home = rows(world.brain, "SELECT link_to FROM entry WHERE link_from = ? AND "
                             "link_relation = 'in-conversation' ORDER BY seq LIMIT 1", post)[0][0]
    for way in ("before", "after", "from"):
        got = world.same(f"/fluid/api/collections/conversation?id={home}&{way}={post}")
        assert got.status == 200


def test_a_topic_of_a_conversation(world):
    for topic, home in rows(world.brain, """
            SELECT link_from, link_to FROM entry WHERE link_relation = 'topic-of'"""):
        got = world.same(f"/fluid/api/collections/conversation?id={home}&topic={topic}")
        assert got.status == 200
        assert got.json["key"] == f"topic:{home}:{topic}"
    other = _conversations(world)[0]
    world.same(f"/fluid/api/collections/conversation?id={other}&topic=ent-000000000000")


@pytest.mark.parametrize("query", [
    "", "id=", "id=ent-000000000000", "id=a'b", "id=caf%C3%A9",
    "id={c}&limit=0", "id={c}&limit=x", "id={c}&limit=9999", "id={c}&shape=odd",
    "id={c}&before=1_1&after=1_1", "id={c}&before=1_1&from=start", "id={c}&before=x",
    "id={c}&before=abc_1", "id={c}&before=1_x", "id={c}&before=ent-000000000000",
    "id={c}&before=inf_1", "id={c}&before=1e3_2", "id={c}&from=adm-000000000000",
    "id={c}&after=0_0", "id={c}&before=0_0", "id={c}&after=99999999999_0",
])
def test_conversation_questions(world, query):
    conversation = _conversations(world)[0]
    world.same("/fluid/api/collections/conversation?" + query.format(c=conversation))


# -- collections/thread ---------------------------------------------------------------------------

def _roots(world) -> list[str]:
    return [row[0] for row in rows(world.brain, """
        SELECT DISTINCT link_to FROM entry WHERE link_relation = 'replies-to' ORDER BY seq""")]


def test_every_thread_pages_as_python_s(world):
    assert _roots(world)
    for root in _roots(world):
        got = world.same(f"/fluid/api/collections/thread?root={root}&limit=1")
        assert got.status == 200
        before = got.json.get("before")
        while before:
            page = world.same(f"/fluid/api/collections/thread?root={root}&limit=1"
                              f"&before={urllib.parse.quote(before)}")
            before = page.json.get("before")
        world.same(f"/fluid/api/collections/thread?root={root}&from=start")


@pytest.mark.parametrize("query", [
    "", "root=", "root=ent-000000000000", "root={p}&limit=0", "root={p}&before=x",
    "root={p}&before=1_1&after=1_1",
])
def test_thread_questions(world, query):
    world.same("/fluid/api/collections/thread?" + query.format(p=_post_ids(world)[0]))


# -- objects ----------------------------------------------------------------------------------------

def test_every_post_s_objects(world):
    for post in _post_ids(world):
        got = world.same(f"/fluid/api/objects?post={post}")
        assert got.status in (200, 400), got
        if got.status == 200 and got.json.get("extracted"):
            assert "renderer" in got.json
            for listed in got.json["objects"]:
                for form in ("exact", "live"):
                    address = urllib.parse.quote(listed["address"][form], safe="")
                    world.same(f"/fluid/api/objects/{address}")
                    for fmt in ("md", "csv", "nope"):
                        world.same(f"/fluid/api/objects/{address}?format={fmt}")


def test_many_posts_threads_and_conversations(world):
    for batch in _batches(_post_ids(world)):
        world.same("/fluid/api/objects?posts=" + ",".join(batch))
    for root in _roots(world):
        world.same(f"/fluid/api/objects?thread={root}")
    for conversation in _conversations(world):
        got = world.same(f"/fluid/api/objects?conversation={conversation}&limit=2")
        if got.status == 200 and got.json.get("before"):
            before = urllib.parse.quote(got.json["before"])
            world.same(f"/fluid/api/objects?conversation={conversation}&limit=2&before={before}")


def test_an_edited_post_s_older_version(world):
    edited = rows(world.brain, """
        SELECT l.link_from, l.link_to FROM entry l
        JOIN entry e ON e.id = l.link_to
        WHERE l.link_relation = (SELECT json_extract(body, '$.relation') FROM entry
                                 WHERE family = 'definition'
                                   AND json_extract(body, '$.substrate_role') = 'supersedes'
                                 ORDER BY seq LIMIT 1)
          AND e.def_name = 'contribution' LIMIT 5""")
    assert edited
    for newer, older in edited:
        world.same(f"/fluid/api/objects?post={older}")
        world.same(f"/fluid/api/objects?post={newer}")
        world.same(f"/fluid/api/objects?post={older}&version={older}")
        world.same(f"/fluid/api/objects?post={older}&version={newer}")
        world.same(f"/fluid/api/objects?post={older}&version=ent-000000000000")


@pytest.mark.parametrize("query", [
    "", "post=", "posts=", "thread=", "conversation=", "post=ent-000000000000",
    "posts=,", "thread=ent-000000000000", "conversation=ent-000000000000",
    "conversation={c}&limit=0", "posts=a/b", "post={c}", "thread={c}",
])
def test_objects_questions(world, query):
    world.same("/fluid/api/objects?" + query.format(c=_conversations(world)[0]))


@pytest.mark.parametrize("address", [
    "x", "exact:", "exact:a:b:c", "live:a", "live::k", "exact:ent-000000000000:0:k",
    "live:ent-000000000000:k", "exact:ent-000000000000:-:k", "caf%C3%A9",
    "live:{c}:k", "exact:{c}:0:k", "live:{p}:no-such-key", "exact:{p}:0:no-such-key",
    "exact:{p}:999:no-such-key",
])
def test_addresses_that_do_not_resolve(world, address):
    target = address.format(c=_conversations(world)[0], p=_post_ids(world)[0])
    got = world.same("/fluid/api/objects/" + target)
    assert got.status in (400, 404), got


# -- what only an order of events can show ---------------------------------------------------------

def _home_and_author(world) -> tuple[str, str]:
    post = _post_ids(world)[0]
    home = rows(world.brain, "SELECT link_to FROM entry WHERE link_from = ? AND "
                             "link_relation = 'in-conversation' ORDER BY seq LIMIT 1", post)[0][0]
    author = rows(world.brain, "SELECT attributed_to FROM entry WHERE id = ?", post)[0][0]
    return home, author


def _post(world, home, author, text, **more) -> str:
    done = post_json(world.pair.port, "/fluid/api/posts",
                     {"conversation": home, "author": author,
                      "parts": [{"type": "text", "text": text}], **more}, headers=CLIENT)
    assert done.status == 200, done
    return done.json["id"]


def test_read_your_writes_straight_after_python_commits(world):
    home, author = _home_and_author(world)
    for at in range(30):
        post = _post(world, home, author, f"read me straight after {at}")
        items = ask(world.pair.port, "GET", "/fluid/api/collections/conversation?"
                    f"id={home}&limit=3&shape=posts", headers=CLIENT).json["items"]
        assert post in [item["id"] for item in items], at
        read = ask(world.pair.port, "GET", f"/fluid/api/posts?ids={post}&thread=1",
                   headers=CLIENT).json["posts"][0]
        assert read["parts"][0]["text"] == f"read me straight after {at}"


def test_an_oversized_post_is_refused_in_python_s_words_and_a_big_one_is_read(world):
    home, author = _home_and_author(world)
    over = _post(world, home, author, "x" * 400_001)
    got = ask(world.pair.port, "GET", f"/fluid/api/objects?post={over}", headers=CLIENT)
    assert got.status == 200, got
    assert got.json["extracted"] is False
    assert got.json["why_not"] == ("the post's text is 400001 characters; extraction reads at most "
                                   "400000")
    assert "input" in got.json
    summary = ask(world.pair.port, "GET", f"/fluid/api/posts?ids={over}&thread=1",
                  headers=CLIENT).json["posts"][0]["thread"]
    assert summary["extracted"] is False
    at_the_limit = _post(world, home, author, "y" * 400_000)
    got = ask(world.pair.port, "GET", f"/fluid/api/objects?post={at_the_limit}", headers=CLIENT,
              wait=60.0)
    assert got.status == 200, got
    assert got.json["extracted"] is True, json.dumps(got.json)[:300]


def test_a_window_read_writes_nothing_in_the_record(world):
    before = rows(world.brain, "SELECT (SELECT MAX(seq) FROM entry), (SELECT MAX(seq) FROM operational),"
                               " (SELECT MAX(seq) FROM delivery)")
    for post in _post_ids(world)[:5]:
        ask(world.pair.port, "GET", f"/fluid/api/objects?post={post}", headers=CLIENT)
        ask(world.pair.port, "GET", f"/fluid/api/posts?ids={post}&thread=1", headers=CLIENT)
    after = rows(world.brain, "SELECT (SELECT MAX(seq) FROM entry), (SELECT MAX(seq) FROM operational),"
                              " (SELECT MAX(seq) FROM delivery)")
    assert after == before


def test_a_grant_is_refused_in_fluid_s_words_and_a_host_with_python_s(world):
    data = request("GET", "/fluid/api/posts?ids=x",
                   headers={**CLIENT, "X-Mentis-Worker": "anything"})
    theirs = Answer(exchange(world.py_port, data))
    ours = Answer(exchange(world.pair.port, data))
    assert ours.comparable == theirs.comparable
    assert ours.status == 403
    data = request("GET", "/fluid/api/objects?post=x", host="evil.example", headers=CLIENT)
    assert Answer(exchange(world.pair.port, data)).comparable == \
        Answer(exchange(world.py_port, data)).comparable
