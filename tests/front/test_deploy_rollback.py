"""Row O: deployment and rollback, on a disposable fixture server. Never DAY-TO-DAY. A13 maps here.

    python -m pytest tests/front/test_deploy_rollback.py -q -m live

9 live, in this order, on one server: each case stands on what the one before left, as a real
deployment does. A case that fails leaves the ones after it failing: nothing here skips.

The second front binary is the same build copied elsewhere with a byte added past its end, so
"the new binary answers" means a different digest, not a different program.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import time

import pytest

from tests.front import pair_harness as pair

pytestmark = pytest.mark.live

CUTOVER = pathlib.Path(__file__).resolve().parent.parent.parent / "docs" / "cutover"
ROUTE_TABLE = (pathlib.Path(__file__).resolve().parent.parent.parent
               / "crates" / "mentis-server" / "route-table.default.json")
#: A read the default table gives to Rust, and whose answer doesn't need Python.
OWNED_ROUTE, OWNED_READ = "topics", "/fluid/api/topics?q=load"
TABLE_TAKES_S = 2.0
#: What Python's startup may add: `retire_unconsumable`'s closing acts (`web/__init__.py`, `serve`).
STARTUP_ACTS = {"expectation-met"}


def table_with(path: pathlib.Path, owner: str) -> None:
    """One edit to the table, written to a temporary name and renamed, as the contract asks."""
    table = json.loads(ROUTE_TABLE.read_text(encoding="utf-8"))
    rules = [rule for rule in table["routes"] if rule["id"] == OWNED_ROUTE]
    assert rules, f"the default table has no rule {OWNED_ROUTE!r}"
    for rule in rules:
        rule["owner"] = owner
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(table), encoding="utf-8")
    os.replace(temporary, path)


def counts(brain: pathlib.Path) -> dict:
    """Every table's rows."""
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in tables}
    finally:
        conn.close()


#: What a Python restart changes in a Brain's directory beside the record: measured on BRAIN-SEED.
PYTHONS_OWN_FILES = {"corpus.db", "corpus.db-wal", "corpus.db-shm", ".mentis.serve.json",
                     ".mentis.serve.lock", ".mentis.sole.lock", ".mentis.owner.lock",
                     ".mentis.claim"}


def sibling_files(brain: pathlib.Path) -> dict:
    """Every other file in the Brain's directory, by size and modification time."""
    found = {}
    for path in brain.rglob("*"):
        name = path.relative_to(brain).as_posix()
        if path.is_file() and name not in PYTHONS_OWN_FILES:
            seen = path.stat()
            found[name] = (seen.st_size, seen.st_mtime_ns)
    return found


def startup_acts_since(brain: pathlib.Path, seq: int) -> list[str]:
    """Each operational act Python's startup added, by name, for the report and the row."""
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return [row[0] for row in conn.execute(
            "SELECT act FROM operational WHERE seq > ? ORDER BY seq", (seq,))]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def fixture_server(tmp_path_factory, request):
    """One copy of BRAIN-COPY, and what each case leaves for the next."""
    from tools.r1 import common, copy_brain

    root = tmp_path_factory.mktemp("deploy")
    brain = copy_brain.fresh(root / "brain", common.master_dir(),
                             common.EVIDENCE / "brain-copy-manifest.json")
    shared = {"brain": brain, "run": pair.run_dir_of(brain), "table": root / "route-table.json",
              "root": root}
    yield shared
    state_path = shared["run"] / "launch.json"
    pids = []
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pids = [state["front"]["pid"], state["python"]["pid"]]
    pids += shared.get("started", [])
    for pid in pids:
        pair.kill_tree(pid)
    for port in (pair.PORT, pair.PRIVATE_PORT):
        listener = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction "
             "SilentlyContinue).OwningProcess"], capture_output=True, text=True).stdout.split()
        for pid in listener:
            pair.kill_tree(int(pid))


def launcher_of() -> pathlib.Path:
    return pathlib.Path(pair.under_test()[0])


def script_env() -> dict:
    return pair.environment(pair.REAL_MARS)


def test_o1_the_launcher_starts_python_private_and_the_front_public(fixture_server):
    table_with(fixture_server["table"], "rust")
    done = pair.launch_detached(fixture_server["brain"],
                                extra=["--route-table", str(fixture_server["table"])])
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"Mentis on http://127.0.0.1:{pair.PORT}"
    state = pair.launch_state(fixture_server["run"])
    fixture_server["state"] = state
    assert (state["public_port"], state["private_port"]) == (pair.PORT, pair.PRIVATE_PORT)
    for who in ("front", "python"):
        assert pair.process_exists(state[who]["pid"]), who
    through = pair.get_json(pair.PORT, "/api/server", client=False)
    assert through["process"]["port"] == pair.PORT
    assert through["corpus"] == str(fixture_server["brain"])
    assert pair.get_json(pair.PRIVATE_PORT, "/api/server", client=False)["process"]["pid"] == \
        through["process"]["pid"]


def test_o2_a_route_rolled_back_by_the_table_takes_effect_with_no_restart(fixture_server):
    state = pair.launch_state(fixture_server["run"])
    python_listener = pair.listener_pid(pair.PRIVATE_PORT)
    front_listener = pair.listener_pid(pair.PORT)
    assert pair.answers_without_python(pair.PORT, OWNED_READ), "Rust answers it, with Python stopped"

    table_with(fixture_server["table"], "python")
    time.sleep(TABLE_TAKES_S)
    assert not pair.answers_without_python(pair.PORT, OWNED_READ), \
        "forwarded now, so it needs Python"

    assert pair.launch_state(fixture_server["run"]) == state
    assert (pair.listener_pid(pair.PRIVATE_PORT), pair.listener_pid(pair.PORT)) == \
        (python_listener, front_listener), "neither process restarted"

    table_with(fixture_server["table"], "rust")
    time.sleep(TABLE_TAKES_S)
    assert pair.answers_without_python(pair.PORT, OWNED_READ)


def test_o3_deploy_with_a_run_active_lists_it_and_asks_and_no_changes_nothing(fixture_server):
    new_front = fixture_server["root"] / "new" / "mentis-server.exe"
    new_front.parent.mkdir()
    shutil.copy(launcher_of().with_name("mentis-server.exe"), new_front)
    with open(new_front, "ab") as binary:
        binary.write(b"\0")
    fixture_server["new_front"] = new_front

    owner = pair.owner_of_copy(pair.PORT)
    conversation_id = pair.post_json(pair.PORT, "/api/conversations", {
        "name": "R1 row O", "about": "row O's run", "author": owner})[1]["conversation"]
    carrier = pair.participant(pair.PORT, "@Builder")
    asked = pair.ask_agent(pair.PORT, conversation_id, owner, carrier,
                           "Run a command that waits 240 seconds, then reply with the word done.")
    run = pair.wait_for_run(pair.PORT, conversation_id, asked["turn"])
    fixture_server["run_id"] = run

    before = pair.launch_state(fixture_server["run"])
    done = pair.powershell(CUTOVER / "deploy-front.ps1", "-Front", str(new_front),
                           "-RunDir", str(fixture_server["run"]), "-Launcher", str(launcher_of()),
                           "-YesWhenIdle", answer="no\n", env=script_env())
    assert done.returncode == 3, done.stdout + done.stderr
    assert run in done.stdout, "the run is listed"
    assert "Replace the front?" in done.stdout, "it asks, even with the standing yes"
    assert pair.launch_state(fixture_server["run"]) == before
    assert pair.process_exists(before["front"]["pid"])
    assert pair.get(pair.PORT, "/api/server", client=False)[0] == 200


def test_o4_deploy_answered_yes_replaces_the_front_and_python_stays(fixture_server):
    before = pair.launch_state(fixture_server["run"])
    new_front = fixture_server["new_front"]
    stopped = pair.post_json(pair.PORT, f"/api/runs/{fixture_server['run_id']}/stop",
                             {"why": "row O has what it needed of this run"})
    assert stopped[0] == 200, stopped
    pair.wait_for_run_end(pair.PORT, fixture_server["run_id"])

    done = pair.powershell(CUTOVER / "deploy-front.ps1", "-Front", str(new_front),
                           "-RunDir", str(fixture_server["run"]), "-Launcher", str(launcher_of()),
                           answer="yes\n", env=script_env())
    assert done.returncode == 0, done.stdout + done.stderr

    after = pair.launch_state(fixture_server["run"])
    assert after["python"] == before["python"], "Python's pid is unchanged"
    assert pair.process_exists(after["python"]["pid"])
    assert after["front"]["pid"] != before["front"]["pid"]
    assert not pair.process_exists(before["front"]["pid"])
    assert pathlib.Path(after["front"]["executable"]) == new_front
    assert after["secret"] == before["secret"]
    assert "old sha256" in done.stdout and "new sha256" in done.stdout and " gap " in done.stdout
    assert pair.get(pair.PORT, OWNED_READ)[0] == 200, "the new binary answers"
    assert pair.listener_pid(pair.PORT) == after["front"]["pid"]


def test_o5_rollback_is_python_on_the_public_port_and_only_its_own_startup_acts(fixture_server):
    brain = fixture_server["brain"]
    before = pair.launch_state(fixture_server["run"])
    counted = counts(brain)
    siblings = sibling_files(brain)
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    last_act = conn.execute("SELECT MAX(seq) FROM operational").fetchone()[0]
    conn.close()

    done = pair.powershell(CUTOVER / "rollback-to-python.ps1", "-RunDir", str(fixture_server["run"]),
                           "-Launcher", str(launcher_of()), answer="yes\n", env=script_env())
    assert done.returncode == 0, done.stdout + done.stderr

    server = pair.get_json(pair.PORT, "/api/server", client=False)
    assert server["process"]["port"] == pair.PORT
    assert server["corpus"] == str(brain)
    pair.wait_port_free(pair.PRIVATE_PORT)
    assert not pair.process_exists(before["front"]["pid"]), "no front"
    assert not pair.process_exists(before["python"]["pid"])
    assert not (fixture_server["run"] / "launch.json").exists()
    fixture_server["started"] = [server["process"]["pid"]]

    acts = startup_acts_since(brain, last_act)
    grown = counts(brain)
    assert {table: count for table, count in grown.items() if table != "operational"} == \
        {table: count for table, count in counted.items() if table != "operational"}, \
        "Python's startup adds acts, and nothing else"
    assert grown["operational"] - counted["operational"] == len(acts)
    assert sibling_files(brain) == siblings, "nothing else in the Brain's directory moved"
    print(json.dumps({"python_startup_acts": acts}))  # each listed, for the report
    assert set(acts) <= STARTUP_ACTS, acts


def test_o6_the_launcher_again_on_the_same_brain_and_both_verifiers_pass(fixture_server):
    brain = fixture_server["brain"]
    for pid in fixture_server.get("started", []):
        pair.kill_tree(pid)
    pair.wait_port_free(pair.PORT)
    _wait_for_log_released(fixture_server["run"] / "python.log")

    done = pair.launch_detached(brain, extra=["--route-table", str(fixture_server["table"])])
    assert done.returncode == 0, done.stderr
    state = pair.launch_state(fixture_server["run"])
    assert pair.get_json(pair.PORT, "/api/server", client=False)["process"]["port"] == pair.PORT
    assert pair.get_json(pair.PRIVATE_PORT, "/api/server", client=False)["corpus"] == str(brain)
    assert pair.get(pair.PORT, OWNED_READ)[0] == 200

    pair.kill_tree(state["front"]["pid"])
    pair.kill_tree(state["python"]["pid"])
    pair.wait_port_free(pair.PORT)
    pair.wait_port_free(pair.PRIVATE_PORT)

    said = _verify_with_python(brain)
    assert said["intact"] is True, said
    tables = _verify_with_rust(brain)
    assert {table["table"] for table in tables} == set(said["streams"])
    for table in tables:
        assert table["broke_at_seq"] is None, table
        assert table["head"] == said["streams"][table["table"]]["head"], table


def _wait_for_log_released(log: pathlib.Path, limit: float = 30.0) -> None:
    """Rollback's Python writes through `cmd.exe`'s redirection (`Start-Outside`), and the launcher
    can't open the log until that shell has gone, a moment after the port."""
    deadline = time.monotonic() + limit
    while True:
        try:
            log.open("ab").close()
            return
        except PermissionError:
            assert time.monotonic() < deadline, f"{log} is still held"
            time.sleep(0.1)


def _launched_again(fixture_server) -> dict:
    done = pair.launch_detached(fixture_server["brain"],
                                extra=["--route-table", str(fixture_server["table"])])
    assert done.returncode == 0, done.stderr
    return pair.launch_state(fixture_server["run"])


def _front_on(fixture_server, front) -> None:
    done = subprocess.run([str(launcher_of()), "--only", "front", "--run-dir",
                           str(fixture_server["run"]), "--front", str(front)],
                          env=script_env(), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=120)
    assert done.returncode == 0, done.stderr


def test_o7_a_new_front_that_wont_start_leaves_python_and_says_how_to_go_back(fixture_server):
    before = _launched_again(fixture_server)
    broken = fixture_server["root"] / "broken" / "mentis-server.exe"
    broken.parent.mkdir()
    broken.write_bytes(b"not a program")
    done = pair.powershell(CUTOVER / "deploy-front.ps1", "-Front", str(broken),
                           "-RunDir", str(fixture_server["run"]), "-Launcher", str(launcher_of()),
                           answer="yes\n", env=script_env())
    assert done.returncode == 3, done.stdout + done.stderr
    assert "THE FRONT IS DOWN" in done.stderr
    assert before["front"]["executable"] in done.stderr, "the previous binary is named"
    assert pair.launch_state(fixture_server["run"]) == before
    assert not pair.process_exists(before["front"]["pid"])
    assert pair.process_exists(before["python"]["pid"])
    assert pair.get(pair.PRIVATE_PORT, "/api/server", client=False)[0] == 200

    pair.wait_port_free(pair.PORT)
    _front_on(fixture_server, before["front"]["executable"])
    assert pair.get(pair.PORT, OWNED_READ)[0] == 200
    assert pair.launch_state(fixture_server["run"])["python"] == before["python"]


def test_o8_deploy_with_a_front_already_dead_refuses_and_changes_nothing(fixture_server):
    before = pair.launch_state(fixture_server["run"])
    pair.kill_tree(before["front"]["pid"])
    pair.wait_port_free(pair.PORT)
    done = pair.powershell(CUTOVER / "deploy-front.ps1", "-Front", str(fixture_server["new_front"]),
                           "-RunDir", str(fixture_server["run"]), "-Launcher", str(launcher_of()),
                           answer="yes\n", env=script_env())
    assert done.returncode == 3, done.stdout + done.stderr
    assert "no front took the stop" in done.stderr
    assert pair.launch_state(fixture_server["run"]) == before
    assert pair.process_exists(before["python"]["pid"])

    _front_on(fixture_server, before["front"]["executable"])


def test_o9_rollback_leaves_a_process_that_reused_pythons_pid(fixture_server):
    state = pair.launch_state(fixture_server["run"])
    pair.kill_tree(state["python"]["pid"])
    pair.wait_port_free(pair.PRIVATE_PORT)
    bystander = subprocess.Popen([state["python"]["executable"], "-c",
                                  "import time; time.sleep(600)"])
    try:
        state["python"]["pid"] = bystander.pid
        (fixture_server["run"] / "launch.json").write_text(json.dumps(state), encoding="utf-8")
        done = pair.powershell(CUTOVER / "rollback-to-python.ps1",
                               "-RunDir", str(fixture_server["run"]),
                               "-Launcher", str(launcher_of()), answer="yes\n", env=script_env())
        assert done.returncode == 0, done.stdout + done.stderr
        assert bystander.poll() is None, "the unrelated process is untouched"
        server = pair.get_json(pair.PORT, "/api/server", client=False)
        assert server["corpus"] == str(fixture_server["brain"])
        fixture_server["started"] = [server["process"]["pid"]]
    finally:
        bystander.kill()
        bystander.wait()


def _verify_with_python(brain: pathlib.Path) -> dict:
    """`Store.verify_chain`, read through SQLite so what the kill left in `-wal` counts."""
    from mentis.spine import backup

    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return backup._chain(conn)
    finally:
        conn.close()


def _verify_with_rust(brain: pathlib.Path) -> list[dict]:
    """P1.1's `verify_chains` on this Brain, by the front's binary, as rows E and J15 use it. It
    exits 0 whatever it finds, so what it says is the result."""
    done = subprocess.run(
        [str(launcher_of().with_name("mentis-server.exe")), "--verify-chains", str(brain)],
        capture_output=True, text=True, encoding="utf-8", timeout=900)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)
