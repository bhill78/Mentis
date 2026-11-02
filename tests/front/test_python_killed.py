"""Row F: Python killed. Owned routes still answer, others answer 503 with the frozen words, and
nothing is left behind. `R1-acceptance.md`, "F"."""

from __future__ import annotations

import shutil

import pytest

from tests.front.pair import FRONT_503, Pair, alive, ask, process_tree, wait_gone


@pytest.fixture
def killed(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    with Pair(copy) as pair:
        tree = process_tree(pair.python_pid)
        pair.kill_python()
        assert all(wait_gone(pid) for pid in tree)
        pair.killed_tree = tree
        yield pair


def test_owned_routes_still_answer(killed):
    assert ask(killed.port, "GET", "/").status == 200
    assert ask(killed.port, "GET", "/assets/no-such-file.js").status == 200
    assert ask(killed.port, "GET", "/api/pulse", headers={"X-Mentis-Client": "1"}).status == 200
    assert ask(killed.port, "GET", "/fluid/api/topics?q=load",
               headers={"X-Mentis-Client": "1"}).status == 200


def test_others_answer_503_with_exactly_the_words_that_nothing_was_done(killed):
    for method, path in [("GET", "/api/server"), ("GET", "/api/conversations"),
                         ("GET", "/fluid/api/runs"), ("OPTIONS", "/api/server"),
                         ("POST", "/api/worker")]:
        got = ask(killed.port, method, path, headers={"X-Mentis-Client": "1"})
        assert got.status == 503, (method, path, got)
        assert got.status_line == "HTTP/1.1 503 Service Unavailable"
        assert got.json == {"error": FRONT_503["Python-unreached"]}, (method, path)
        assert got.header("Connection") == "close"


def test_no_orphan_process_and_only_python_went(killed):
    assert not any(alive(pid) for pid in killed.killed_tree), "an orphan of Python's"
    assert alive(killed.front_pid), "the front outlives Python: nothing watches anything"
    front = killed.front_pid
    killed.close()
    assert wait_gone(front), "closing the pair left its front running"
