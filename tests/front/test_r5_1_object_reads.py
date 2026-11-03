"""R5.1 on the wire: `/api/references`, `/fluid/api/search`, `/fluid/api/object-refs` and
`/fluid/api/document` from a real front against Python alone, status, headers and body, on one changed
BRAIN-SEED. Then worker `find` and `check_rendering` through the door. What each answers is compared
case by case, byte for byte, in `crates/mentis-server/tests/object_reads.rs`: this is what only a socket
shows, the door each route has and the protections a document carries.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse

import pytest

from tests.front.mirror_harness import world as door_world
from tests.front.pair import (CLIENT, PY_PORT, SPARE_PORTS, Answer, Pair, exchange, request)
from tests.front.test_door_answers import _whole
from tests.front.test_mirror_protocol import _answered_count
from tools.r1 import common, py_alone

PAIR_PORT = SPARE_PORTS[0]
WAIT_S = 120.0
SIDE = common.REPO / "crates" / "mentis-server" / "tests" / "support" / "object_reads_side.py"
#: What every answer on the document route carries, and no other route here.
PROTECTIONS = {"X-Content-Type-Options", "Content-Security-Policy", "Cross-Origin-Resource-Policy",
               "Referrer-Policy"}


def _side(*args) -> None:
    done = subprocess.run([str(common.venv_python()), str(SIDE), *map(str, args)],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env={**_system_environment(), "PYTHONPATH": str(common.REPO),
                               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
                               "MENTIS_FLUID_DIST": str(common.dist_dir())})
    assert done.returncode == 0, done.stderr


def _system_environment() -> dict:
    import os
    return {name: os.environ[name] for name in ("SYSTEMROOT", "PATH", "TEMP", "TMP")
            if name in os.environ}


class World:
    def __init__(self, py_port, pair, facts):
        self.py_port, self.pair, self.facts = py_port, pair, facts

    def both(self, target: str, headers=CLIENT) -> tuple[Answer, Answer]:
        data = request("GET", target, headers=headers)
        got = (Answer(exchange(self.py_port, data, wait=WAIT_S)),
               Answer(exchange(self.pair.port, data, wait=WAIT_S)))
        assert got[0].status and got[1].status, f"no answer in {WAIT_S} s: {target}"
        return got

    def same(self, target: str, headers=CLIENT) -> Answer:
        """Asked twice of each, and the second compared whole, so what each process has already read
        can't differ."""
        self.both(target, headers)
        theirs, ours = self.both(target, headers)
        assert ours.comparable == theirs.comparable, target
        return ours


@pytest.fixture(scope="module")
def world(brain_seed, tmp_path_factory):
    changed = tmp_path_factory.mktemp("changed") / "brain"
    shutil.copytree(brain_seed, changed)
    _side("change", changed)
    facts = json.loads((changed / "r5-1-world.json").read_text(encoding="utf-8"))
    py_copy = tmp_path_factory.mktemp("py") / "brain"
    pair_copy = tmp_path_factory.mktemp("pair") / "brain"
    shutil.copytree(changed, py_copy)
    shutil.copytree(changed, pair_copy)
    with py_alone.running(py_copy, port=PY_PORT, code=common.REPO):
        with Pair(pair_copy, port=PAIR_PORT) as pair:
            yield World(PY_PORT, pair, facts)


def _names(answer: Answer) -> set[str]:
    return {name for name, _ in answer.headers}


# -- /fluid/api/document ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["plain", "latin", "junk", "exact", "missing", "corrupt", "purged"])
def test_a_document_is_python_s_with_the_protections(world, name):
    got = world.same(f"/fluid/api/document?ref={world.facts[name]}")
    assert got.status == (200 if name in ("plain", "latin", "junk", "exact") else 404)
    assert PROTECTIONS <= _names(got), got.headers


def test_a_cut_document_is_python_s_at_every_distance_from_a_character(world):
    for ref in world.facts["cuts"]:
        got = world.same(f"/fluid/api/document?ref={ref}")
        assert got.status == 200 and got.json["cut"] is True


@pytest.mark.parametrize("query", ["", "ref=", "other=1", "ref=adm-000000000000", "ref=caf%C3%A9", "ref=%ff",
                                   "ref=a#b"])
def test_a_document_asked_badly_is_python_s_with_the_protections(world, query):
    got = world.same(f"/fluid/api/document?{query}")
    assert PROTECTIONS <= _names(got), got.headers


def test_a_grant_on_the_document_route_is_refused_as_python_refuses_it(world):
    got = world.same(f"/fluid/api/document?ref={world.facts['plain']}", {"X-Mentis-Worker": "any"})
    assert got.status == 403
    assert PROTECTIONS <= _names(got), got.headers


def test_no_client_header_is_refused_on_each_route_before_anything(world):
    for target in ("/fluid/api/document?ref=x", "/fluid/api/object-refs?post=x",
                   "/fluid/api/search?conversation=x&q=y", "/api/references?q=x"):
        assert world.same(target, {}).status == 403


# -- /fluid/api/object-refs ------------------------------------------------------------------------

def test_a_post_s_references_are_python_s(world):
    got = world.same(f"/fluid/api/object-refs?post={world.facts['holder']}")
    assert got.status == 200
    said = {r.get("resolves") for r in got.json["references"]}
    assert said == {True, False}, said
    assert not PROTECTIONS & _names(got)


@pytest.mark.parametrize("name", ["source", "attached", "edited_holder", "deleted_holder", "many",
                                  "plain_post", "later", "deleted"])
def test_each_sort_of_post_is_python_s(world, name):
    world.same(f"/fluid/api/object-refs?post={world.facts[name]}")


def test_one_part_asked_for_is_python_s(world):
    whole = world.facts["whole"]
    quoted = urllib.parse.quote
    key, exact = quoted(whole["key"], safe=""), quoted(whole["exact"], safe="")
    for query in (f"ref={whole['ref']}&key={key}", f"ref={whole['ref']}&key={key}&exact={exact}",
                  f"ref={whole['ref']}&key=nothing", f"ref=ent-000000000000&key={key}",
                  "", "post=", "ref=x", "key=x", "post=ent-000000000000", "post=it%27s"):
        world.same(f"/fluid/api/object-refs?{query}")


# -- /fluid/api/search -----------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "q=needle", "q=NEEDLE", "q=kelvin", "q=so", "q=two++spaces", "q=needle&limit=1", "q=needle&limit=9999",
    "q=zzz-no-such", "q=", "q=x&limit=0", "q=x&limit=y", "q=x&before=abc_1", "q=x&before=ent-000000000000",
    "q=caf%C3%A9", "q=%E2%84%AAelvin", "q=%ff", "q=" + "y" * 501,
])
def test_a_search_is_python_s(world, query):
    world.same(f"/fluid/api/search?conversation={world.facts['known']}&{query}")


@pytest.mark.parametrize("query", ["", "q=x", "conversation=&q=x", "conversation=ent-000000000000&q=x"])
def test_a_search_asked_badly_is_python_s(world, query):
    world.same(f"/fluid/api/search?{query}")


# -- /api/references -------------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "", "q=", "q=%20", "q=%23", "q=needle", "q=@r1", "q=known", "q=1", "q=2&conversation={known}", "q=9999",
    "q=needle&limit=2", "q=needle&limit=0", "q=needle&limit=x", "q=needle&conversation={known}",
    "q=in-conversation", "q=fencedword", "q=ent-000000000000", "q=caf%C3%A9", "q=%D9%A3",
    "ref={known}", "ref=ent-000000000000", "ref={plain_post}", "ref=it%27s", "q=%ff",
])
def test_a_reference_is_python_s(world, query):
    filled = query.format(known=world.facts["known"], plain_post=world.facts["plain_post"])
    world.same(f"/api/references?{filled}")


def test_a_grant_on_references_is_refused_as_python_refuses_it(world):
    assert world.same("/api/references?q=x", {"X-Mentis-Worker": "any"}).status == 403


# -- the door --------------------------------------------------------------------------------------

READS = [
    ("find", {"q": ""}),
    ("find", {"q": "#"}),
    ("find", {"q": "welcome"}),
    ("find", {"q": "1"}),
    ("find", {"q": "known", "limit": 2}),
    ("find", {"q": "in-conversation", "limit": 3}),
    ("find", {"q": 5}),
    ("find", {"q": "x", "limit": "3"}),
    ("check_rendering", {}),
    ("check_rendering", {"text": "plain words"}),
    ("check_rendering", {"text": "```chart version=1 form=nothing\nx\n```"}),
    ("check_rendering", {"text": "x" * 400_001}),
    ("check_rendering", {"text": "- a\n- b"}),
    ("check_rendering", {"syntax": "chart"}),
    ("check_rendering", {"text": 5}),
]


def test_find_and_check_rendering_are_the_same_through_the_front(brain_seed, tmp_path):
    with door_world(brain_seed, tmp_path) as w:
        by_front = {"find": 0, "check_rendering": 0}
        for op, args in READS:
            direct = _whole(w.private, w.token, op, args)
            before = _answered_count(w)
            through = _whole(w.public, w.token, op, args)
            by_front[op] += _answered_count(w) - before
            assert direct == through, (op, args)
        # The lists, `syntax=` and the arguments Python coerces are its own, so neither is all of them.
        assert by_front["find"] > 0 and by_front["check_rendering"] > 0, by_front
        print(f"\nanswered by the front, of {len(READS)}: {by_front}")
