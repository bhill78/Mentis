"""Row P: usable, through the front, on a test server. A14 maps here.

    python -m pytest tests/front/test_usable.py -q -m live

5 live. P1 to P4 on one server on BRAIN-COPY with the real MARS, P5 on a fresh BRAIN-SEED by
`tools/r1/browser_check.py`. A runtime without a browser can't accept this row: Chromium that
can't start exits 2, and P5 fails. Nothing here skips.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

import pytest

from tests.front import pair_harness as pair
from tools.r1 import browser_check, common, copy_brain, py_alone

pytestmark = pytest.mark.live

#: What Fluid reads on opening, as seen in Chromium's first load of `b8e324c`'s build on Python
#: alone, the ones naming no id. Python's answer is the expectation.
OPENING_READS = ("/api/brain?identity=1", "/api/capacity", "/api/operational?newest=1&limit=40",
                 "/api/presentation", "/api/pulse", "/fluid/api/arrangements/home",
                 "/fluid/api/changes", "/fluid/api/conversations?activity=1&limit=40",
                 "/fluid/api/home/activity", "/fluid/api/home/briefing",
                 "/fluid/api/home/for-you", "/fluid/api/home/needs-you",
                 "/fluid/api/home/work?state=all", "/fluid/api/layouts",
                 "/fluid/api/needs-you/items", "/fluid/api/participants?limit=1")
#: These say nothing that moves with the clock, the boot or the copy's path, so they compare whole.
WHOLE = {"/api/presentation", "/fluid/api/layouts", "/fluid/api/participants?limit=1",
         "/fluid/api/arrangements/home"}
LOG_EVERY_S = 10
ASSET = re.compile(r'(?:src|href)="(/[^"]+)"')


@pytest.fixture(scope="module")
def on_copy(tmp_path_factory):
    root = tmp_path_factory.mktemp("usable")
    brain = copy_brain.fresh(root / "brain", common.master_dir(),
                             common.EVIDENCE / "brain-copy-manifest.json")
    with pair.running(brain, mars=pair.REAL_MARS) as (_proc, _command, run):
        yield {"brain": brain, "run": run}


def test_p1_fluid_loads_at_http_level(on_copy, tmp_path_factory):
    status, index = pair.get(pair.PORT, "/", client=False)
    assert status == 200 and b"<html" in index.lower()
    assets = sorted(set(ASSET.findall(index.decode("utf-8"))))
    assert assets, "the index names its assets"

    alone_copy = copy_brain.fresh(tmp_path_factory.mktemp("alone") / "brain", common.master_dir(),
                                  common.EVIDENCE / "brain-copy-manifest.json")
    with py_alone.running(alone_copy):
        alone_index = py_alone.get(py_alone.PORT, "/")
        alone_assets = {path: py_alone.get(py_alone.PORT, path) for path in assets}
        alone_reads = {path: py_alone.get(py_alone.PORT, path) for path in OPENING_READS}

    assert (status, index) == alone_index, "the same build, so the same page"
    for path in assets:
        got = pair.get(pair.PORT, path, client=False)
        assert got[0] == 200, path
        assert got == alone_assets[path], path
    for path in OPENING_READS:
        got = pair.get(pair.PORT, path)
        assert got[0] == alone_reads[path][0] == 200, path
        through, alone = json.loads(got[1]), json.loads(alone_reads[path][1])
        through.pop("live", None)  # the listed additive difference, on a pulse that isn't fresh
        if path in WHOLE:
            assert through == alone, path
        else:
            assert through.keys() == alone.keys(), path


def test_p2_the_palette_answers_from_the_front(on_copy):
    status, body = pair.get(pair.PORT, "/fluid/api/topics?q=" + urllib.parse.quote("load"))
    assert status == 200
    answer = json.loads(body)
    assert isinstance(answer.get("topics"), list), answer
    assert pair.answers_without_python(pair.PORT, "/fluid/api/topics?q=load"), \
        "from the front: it answers with Python stopped"


def test_p3_a_new_post_appears_through_pulse(on_copy):
    owner = pair.owner_of_copy(pair.PORT)
    status, opened = pair.post_json(pair.PORT, "/api/conversations", {
        "name": "R1 row P", "about": "row P's posts", "author": owner})
    assert status == 200, opened
    conversation = opened["conversation"]
    on_copy["conversation"] = conversation

    before = pair.get_json(pair.PORT, "/api/pulse")["token"].split("/")[0]
    words = f"R1 row P3, {time.time()}"
    status, posted = pair.post_json(pair.PORT, f"/api/conversations/{conversation}/turns",
                                    {"author": owner, "text": words})
    assert status == 200, posted

    pulse = pair.get_json(pair.PORT, f"/api/pulse?since={before}")
    durable = pulse["token"].split("/")[0]
    assert durable != before, "the durable half moved"
    assert conversation in json.dumps(pulse["moved"]), "`moved` names its Conversation"
    turn = pair.get_json(pair.PORT, f"/api/turns/{posted['turn']}")
    assert words in json.dumps(turn), "and the post reads back"


def test_p4_a_real_agent_run_completes_with_its_calls_through_the_front(on_copy):
    owner = pair.owner_of_copy(pair.PORT)
    carrier = pair.participant(pair.PORT, "@Builder")
    conversation = on_copy["conversation"]
    asked = pair.ask_agent(
        pair.PORT, conversation, owner, carrier,
        "Call your Mentis tool `orient` once, then reply with the single word done. "
        "Do nothing else.")
    run = pair.wait_for_run(pair.PORT, conversation, asked["turn"])
    said = pair.wait_for_run_end(pair.PORT, run)
    assert said["state"] in ("completed", "recovered"), said

    state = pair.launch_state(on_copy["run"])
    assert state["answers_at"] == f"http://127.0.0.1:{pair.PORT}", "agents are told the public port"
    # The front files an agent's calls under this name, in a line every 10 s.
    log = pathlib.Path(on_copy["run"]) / "front.log"
    deadline = time.monotonic() + LOG_EVERY_S + 5
    while "forwarded:/api/worker" not in log.read_text(encoding="utf-8"):
        assert time.monotonic() < deadline, "its Mentis calls aren't in the front's log"
        time.sleep(1)


def test_p5_fluid_opens_in_headless_chromium_through_the_front(brain_seed, tmp_path):
    # P1 to P4's server holds the port until the module ends, so this one takes the next.
    port = pair.PORT + 1
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    with pair.running(copy, port=port):
        done = subprocess.run(
            [sys.executable, str(pathlib.Path(browser_check.__file__)), f"http://127.0.0.1:{port}/"],
            capture_output=True, text=True, timeout=180, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(done.stdout)["passed"] is True
