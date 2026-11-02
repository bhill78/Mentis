"""Row C: a read through the front sees a write the moment Python has answered it. `R1-acceptance.md`,
row C: 300 commits each, for pulse and topics, 0 misses. Reported as a trial, not as a guarantee about
every read.

Each write goes through the front to Python, and each read through the front to Rust, on its own
connection to a Brain another process just committed to. There is no wait between them.
"""

from __future__ import annotations

import shutil

import pytest

from tests.front.pair import CLIENT, Pair, advance, ask, conversation_named, post_json, rows

COMMITS = 300


@pytest.fixture(scope="module")
def pair(brain_seed, tmp_path_factory):
    copy = tmp_path_factory.mktemp("c") / "brain"
    shutil.copytree(brain_seed, copy)
    with Pair(copy) as running:
        yield running


def owner_of(brain) -> str:
    return rows(brain, "SELECT id FROM entry WHERE def_name='participant' "
                       "AND json_extract(body,'$.alias')='@r1-owner'")[0][0]


def durable_of(answer) -> tuple[int, ...]:
    return tuple(int(part) for part in answer.json["token"].split("/")[0].split("."))


def test_a_commit_is_in_the_next_pulse(pair):
    conversation = conversation_named(pair.brain, "R1 known conversation")
    owner = owner_of(pair.brain)
    missed = []
    for n in range(COMMITS):
        posted = post_json(pair.port, "/fluid/api/posts", {
            "conversation": conversation, "author": owner, "text": f"row C post {n}"}, CLIENT)
        assert posted.status == 200, posted
        committed = advance(pair.brain)
        pulse = ask(pair.port, "GET", "/api/pulse", headers=CLIENT)
        assert pulse.status == 200, pulse
        if durable_of(pulse) < committed:
            missed.append((n, committed, pulse.json["token"]))
    print(f"row C pulse: {COMMITS} commits, {len(missed)} misses")
    assert not missed


def test_a_commit_is_in_the_next_topics(pair):
    conversation = conversation_named(pair.brain, "R1 known conversation")
    owner = owner_of(pair.brain)
    missed = []
    for n in range(COMMITS):
        name = f"row C topic {n:03d} unique"
        opened = post_json(pair.port, f"/api/conversations/{conversation}/topics",
                           {"name": name, "author": owner}, CLIENT)
        assert opened.status == 200 and "topic" in opened.json, opened
        found = ask(pair.port, "GET", f"/fluid/api/topics?q={name.replace(' ', '%20')}",
                    headers=CLIENT)
        assert found.status == 200, found
        if [t["ref"] for t in found.json["topics"]] != [opened.json["topic"]]:
            missed.append((n, opened.json["topic"], found.json))
    print(f"row C topics: {COMMITS} commits, {len(missed)} misses")
    assert not missed
