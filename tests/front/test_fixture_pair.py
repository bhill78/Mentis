"""P1.5-PAIR: PAIR's first check, on BRAIN-SEED, on the integrated P1.2, P1.3 and P1.5.

Exactly these 4, before any row that uses PAIR. They join row Q at the integration. Set
`$env:MENTIS_UNDER_TEST` as `docs/rust/R1-acceptance.md`, PAIR, says.
"""

from __future__ import annotations

import json
import shutil

from mentis.spine import brainlock
from tests.front import pair_harness as pair
from tools.r1 import common, py_alone

#: One read PAIR's front owns, and one it forwards. The same copy of the seed gives each side the
#: same record, so the answers can be compared whole.
OWNED = "/fluid/api/topics?q=load"
FORWARDED = "/api/conversations"


def _copy(brain_seed, tmp_path, name="brain"):
    copy = tmp_path / name
    shutil.copytree(brain_seed, copy)
    return copy


def test_the_pair_starts_and_both_answer(brain_seed, tmp_path):
    copy = _copy(brain_seed, tmp_path)
    with pair.running(copy) as (proc, _command, run):
        assert proc.poll() is None, "--attached stays"
        through = pair.get_json(pair.PORT, "/api/server", client=False)
        assert through["process"]["port"] == pair.PORT, "agents are told the public address"
        assert through["corpus"] == str(copy)
        private = pair.get_json(pair.PRIVATE_PORT, "/api/server", client=False)
        assert private["process"]["pid"] == through["process"]["pid"], "the same Python"
        assert pair.get(pair.PORT, "/api/pulse")[0] == 200
        state = pair.launch_state(run)
        assert (state["public_port"], state["private_port"]) == (pair.PORT, pair.PRIVATE_PORT)
        tree = pair.descendants(proc.pid)
        assert {state["front"]["pid"], state["python"]["pid"]} <= tree, "both in the launcher's tree"


def test_an_owned_and_a_forwarded_read_match_py_alone(brain_seed, tmp_path):
    with py_alone.running(_copy(brain_seed, tmp_path, "alone")):
        alone = {path: py_alone.get(py_alone.PORT, path) for path in (OWNED, FORWARDED)}
    with pair.running(_copy(brain_seed, tmp_path)):
        through = {path: pair.get(pair.PORT, path) for path in (OWNED, FORWARDED)}
    for path in (OWNED, FORWARDED):
        assert through[path][0] == alone[path][0] == 200, path
        assert json.loads(through[path][1]) == json.loads(alone[path][1]), path


def test_its_commits_and_binary_digests_are_recorded(brain_seed, tmp_path):
    copy = _copy(brain_seed, tmp_path)
    with pair.running(copy) as (_proc, command, run):
        recorded = json.loads((run / "provenance.json").read_text(encoding="utf-8"))
        server = pair.get_json(pair.PORT, "/api/server", client=False)
    code = pair.option(command, "--code")
    assert recorded["commit"] == common.head_of(code)
    assert server["code"]["commit"] == recorded["commit"], "the Python that ran is that commit"
    assert set(recorded["binaries"]) == {"mentis-launch.exe", "mentis-server.exe"}
    for name, binary in recorded["binaries"].items():
        assert binary["sha256"] == common.sha256_file(binary["path"]), name


def test_killing_its_tree_leaves_no_process_and_no_lock(brain_seed, tmp_path):
    copy = _copy(brain_seed, tmp_path)
    with pair.running(copy) as (proc, _command, run):
        state = pair.launch_state(run)
        everyone = pair.descendants(proc.pid) | {proc.pid}
        assert brainlock.serving(str(copy)), "Python holds the Brain while it runs"
        pair.kill_tree(proc.pid)
        proc.wait(timeout=30)
    assert not [pid for pid in everyone if pair.process_exists(pid)]
    assert not pair.process_exists(state["front"]["pid"])
    pair.wait_port_free(pair.PORT)
    pair.wait_port_free(pair.PRIVATE_PORT)
    # The locks die with their process: both can be taken whole by somebody else now.
    with brainlock.serve(str(copy)):
        brainlock.unserve(str(copy))
    with brainlock.exclusive(str(copy), "after the tree was killed"):
        pass
