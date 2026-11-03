"""M1: `GET /fluid/api/magnets/<id>/read` through a real pair, on one changed BRAIN-SEED: the route, the
definition Python wrote, the door's checks, and what a client leaving does."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time

import pytest

from tests.front.pair import CLIENT, SPARE_PORTS, Pair, ask, post_json, request, rows
from tools.r1 import common

PORT = SPARE_PORTS[0]
SIDE = common.REPO / "crates" / "mentis-rules" / "tests" / "support" / "python_side.py"
BIGGEST = ("SELECT l.link_to FROM entry l WHERE l.link_relation = 'in-conversation' "
           "GROUP BY l.link_to ORDER BY COUNT(*) DESC")


def _seed(conversations):
    return {"sources": [{"kind": "conversation", "conversation": c} for c in conversations],
            "selection": {}, "collection": {"mode": "one-time"},
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False, "failures": False},
            "presentation": {"renderer": "disc"}}


@pytest.fixture(scope="module")
def world(brain_seed, tmp_path_factory):
    brain = tmp_path_factory.mktemp("m1") / "brain"
    shutil.copytree(brain_seed, brain)
    done = subprocess.run([str(common.venv_python()), str(SIDE), "change", str(brain)],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONPATH": str(common.REPO),
                               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr
    ids = [r[0] for r in rows(brain, BIGGEST)]
    with Pair(brain, port=PORT) as pair:
        yield {"pair": pair, "ids": ids, "brain": brain}


def _make(world, sources):
    got = post_json(world["pair"].port, "/fluid/api/arrangements/home/magnets", {
        "seed": _seed(sources),
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"},
                   "base": {"format": "mentis.fluid-arrangement", "version": 2,
                            "tree": {"type": "zone", "id": "s", "show": "objects"}}}},
                    headers=CLIENT)
    assert got.status == 200, got
    return got.json["magnet"]["id"]


def _read(world, mid, query):
    return ask(world["pair"].port, "GET", f"/fluid/api/magnets/{mid}/read?{query}", headers=CLIENT)


def test_a_summary_and_a_page_answer_per_source(world):
    mid = _make(world, world["ids"][:1] + ["ent-not-a-conversation"])
    got = _read(world, mid, "mode=summary")
    assert got.status == 200, got
    first, second = got.json["sources"]
    assert first["status"] == "ok" and first["summary"]["posts"] > 0
    assert first["summary"]["title"] and first["results"] == []
    assert second["status"] == "unavailable" and second["reason"]
    assert all(set(p) == {"id", "alias"} for p in first["participants"]) and first["participants"]
    if "latest" in first:
        assert set(first["latest"]) == {"id", "at", "author", "preview"}
    else:
        assert any(a["field"] == "latest" and a["reason"] for a in first["absent"])
    assert not {"participants", "participants_more", "latest", "absent"} & set(second)

    key = f"conversation:{world['ids'][0]}"
    got = _read(world, mid, f"mode=page&types=post&source={key.replace(':', '%3A')}")
    assert got.status == 200, got
    only = got.json["sources"]
    assert [s["key"] for s in only] == [key]
    row = only[0]["results"][0]
    for field in ("id", "version", "conversation", "author", "at"):
        assert field in row, row
    assert "latest" not in only[0] and "participants" not in only[0]


def test_the_answer_comes_from_the_definition_so_a_reconfigure_is_seen(world):
    mid = _make(world, world["ids"][:1])
    assert len(_read(world, mid, "mode=summary").json["sources"]) == 1
    got = post_json(world["pair"].port, f"/fluid/api/arrangements/home/magnets/{mid}/reconfigure",
                    {"change": {"sources": [{"kind": "conversation", "conversation": c}
                                            for c in world["ids"][:2]]}}, headers=CLIENT)
    assert got.status == 200, got
    assert len(_read(world, mid, "mode=summary").json["sources"]) == 2


def test_no_definition_is_python_s_404_and_no_client_header_is_refused(world):
    assert _read(world, "mag-nobody", "mode=summary").status == 404
    mid = _make(world, world["ids"][:1])
    assert ask(world["pair"].port, "GET", f"/fluid/api/magnets/{mid}/read").status == 403
    assert _read(world, mid, "mode=everything").status == 400


def test_a_client_leaving_mid_read_leaves_the_route_answering(world):
    mid = _make(world, world["ids"][:2])
    data = request("GET", f"/fluid/api/magnets/{mid}/read?mode=page&types=post,file", headers=CLIENT)
    for _ in range(8):
        with socket.create_connection(("127.0.0.1", world["pair"].port)) as s:
            s.sendall(data)
    deadline = time.monotonic() + 15
    while True:
        got = _read(world, mid, "mode=summary")
        if got.status == 200:
            break
        assert got.status == 503, got
        assert time.monotonic() < deadline, "the class's places never came back"
        time.sleep(0.05)
    assert json.loads(got.body)["sources"][0]["status"] == "ok"
