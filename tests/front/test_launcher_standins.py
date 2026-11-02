"""The launcher against stand-ins: its refusals, its order, and what `--upstream` gives the front.

P1.5's own tests until the integration, and not a frozen row: `docs/rust/R1-acceptance.md`, "The
order". The launcher's success against a real front is `test_fixture_pair.py`'s. These also take the
deploy and rollback scripts through their questions, against the same stand-ins, so that row O isn't
their first run; row O is what accepts them.

Set `MENTIS_LAUNCH_EXE` to the binary under test: by default this clone's debug build.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
STANDIN = pathlib.Path(__file__).with_name("launcher_standins.py")
CUTOVER = REPO / "docs" / "cutover"
PUBLIC, PRIVATE = 8871, 18871
LAUNCH = pathlib.Path(os.environ.get("MENTIS_LAUNCH_EXE")
                      or REPO / "target" / "debug" / "mentis-launch.exe")
#: Far enough off that a second one can take a port the first has just left.
QUIET_S = 0.3


class Rig:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.dir = root / "standin"
        self.brain = root / "brain"
        self.code = root / "code"
        self.run_dir = root / "run"
        self.workspace = root / "ws"
        web = self.code / "mentis" / "web"
        web.mkdir(parents=True)
        self.brain.mkdir()
        self.dir.mkdir()
        self.workspace.mkdir()
        (self.code / "mentis" / "__init__.py").write_text("")
        (web / "__init__.py").write_text("")
        shutil.copy(STANDIN, web / "__main__.py")
        shutil.copy(STANDIN, self.brain / "__main__.py")
        self.behaviour({})
        self.started: list[int] = []

    def behaviour(self, how: dict) -> None:
        (self.dir / "behaviour.json").write_text(json.dumps(how), encoding="utf-8")

    def args(self, *extra: str, front: str | None = None, port: int = PUBLIC) -> list[str]:
        return [str(self.brain), "--port", str(port), "--workspace", str(self.workspace),
                "--python", sys.executable, "--code", str(self.code),
                "--front", front or sys.executable, "--dist", str(self.root / "dist"),
                "--run-dir", str(self.run_dir), *extra]

    def launch(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        env = {**os.environ, "MENTIS_STANDIN_DIR": str(self.dir), "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("MENTIS_BOOT_SECRET", None)
        return subprocess.run([str(LAUNCH), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout, env=env, stdin=subprocess.DEVNULL)

    def events(self, who: str | None = None) -> list[dict]:
        path = self.dir / "events.jsonl"
        if not path.exists():
            return []
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        return [e for e in lines if who in (None, e["who"])]

    def state(self) -> dict:
        return json.loads((self.run_dir / "launch.json").read_text(encoding="utf-8"))

    def stop_all(self) -> None:
        pids = {e["pid"] for e in self.events()}
        path = self.run_dir / "launch.json"
        if path.exists():
            state = self.state()
            pids |= {state["front"]["pid"], state["python"]["pid"]}
        for pid in pids:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def alive(pid: int) -> bool:
    found = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                           text=True).stdout
    return str(pid) in found


def free(port: int) -> bool:
    try:
        socket.create_server(("127.0.0.1", port)).close()
        return True
    except OSError:
        return False


def wait_free(port: int, limit: float = 10) -> None:
    deadline = time.monotonic() + limit
    while not free(port):
        assert time.monotonic() < deadline, f"port {port} is still held"
        time.sleep(0.1)


def get(port: int, path: str = "/api/server") -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as fh:
        return json.loads(fh.read())


@pytest.fixture
def rig(tmp_path):
    made = Rig(tmp_path)
    assert free(PUBLIC) and free(PRIVATE), "this test's ports are in use"
    yield made
    made.stop_all()
    wait_free(PUBLIC)
    wait_free(PRIVATE)


def test_the_binary_is_there():
    assert LAUNCH.is_file(), f"build it first: {LAUNCH}"


@pytest.mark.parametrize("taken", [PUBLIC, PRIVATE])
def test_a_port_in_use_is_refused_and_nothing_is_written(rig, taken):
    with socket.create_server(("127.0.0.1", taken)):
        done = rig.launch(*rig.args())
    assert done.returncode == 3
    assert f"port {taken}" in done.stderr and "in use" in done.stderr
    assert not rig.run_dir.exists()
    assert rig.events() == []


def test_a_run_directory_in_the_brain_is_refused(rig):
    args = rig.args()
    args[args.index("--run-dir") + 1] = str(rig.brain / "run")
    done = rig.launch(*args)
    assert done.returncode == 3 and "is in the Brain" in done.stderr
    assert rig.events() == []


@pytest.mark.parametrize("bad", ["http://localhost:8873", "https://127.0.0.1:8873",
                                 "http://127.0.0.1:8873/", "http://10.0.0.1:8873"])
def test_an_upstream_that_is_not_this_machines_port_is_refused(rig, bad):
    done = rig.launch(*rig.args("--upstream", bad))
    assert done.returncode == 3 and "--upstream is only" in done.stderr
    assert rig.events() == []


def test_a_missing_executable_or_tree_is_refused(rig):
    for flag, value in (("--python", rig.root / "none.exe"), ("--front", rig.root / "none.exe"),
                        ("--code", rig.root)):
        args = rig.args()
        args[args.index(flag) + 1] = str(value)
        done = rig.launch(*args)
        assert done.returncode == 3 and flag in done.stderr, done.stderr
    assert rig.events() == []


def test_python_refusing_stops_the_order_with_its_reason(rig):
    rig.behaviour({"python": "refuse"})
    done = rig.launch(*rig.args())
    assert done.returncode == 3
    assert "python stand-in refuses, in words" in done.stderr
    assert rig.events("front") == []
    assert not (rig.run_dir / "launch.json").exists()


def test_a_front_refusing_stops_the_python_this_invocation_started(rig):
    rig.behaviour({"front": "refuse"})
    done = rig.launch(*rig.args())
    assert done.returncode == 3
    assert "front stand-in refuses, in words" in done.stderr
    python = rig.events("python")[0]
    wait_free(PRIVATE)
    assert not alive(python["pid"])
    assert not (rig.run_dir / "launch.json").exists()


def test_a_front_that_never_answers_is_given_30_s_then_stopped_with_python(rig):
    rig.behaviour({"front": "silent"})
    began = time.monotonic()
    done = rig.launch(*rig.args(), timeout=90)
    assert 29 < time.monotonic() - began < 60
    assert done.returncode == 3 and "within 30 s" in done.stderr
    for who in ("python", "front"):
        assert not alive(rig.events(who)[0]["pid"])
    wait_free(PRIVATE)
    assert not (rig.run_dir / "launch.json").exists()


def test_the_order_and_the_contracts_commands(rig):
    done = rig.launch(*rig.args("--writable-root", str(rig.root), "--mars", "workload-no-mars-here"))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"Mentis on http://127.0.0.1:{PUBLIC}"

    python, front = rig.events("python")[0], rig.events("front")[0]
    assert python["at"] < front["at"], "Python starts first, and answers before the front starts"
    assert python["argv"] == [str(rig.brain), "--host", "127.0.0.1", "--port", str(PRIVATE),
                              "--answers-at", f"http://127.0.0.1:{PUBLIC}",
                              "--workspace", str(rig.workspace),
                              "--writable-root", str(rig.root),
                              "--mars", "workload-no-mars-here"]
    assert pathlib.Path(python["cwd"]) == rig.code
    assert front["argv"] == [str(rig.brain), "--host", "127.0.0.1", "--port", str(PUBLIC),
                             "--upstream", f"http://127.0.0.1:{PRIVATE}",
                             "--dist", str(rig.root / "dist")]

    secret = python["secret"]
    assert secret and secret == front["secret"] and len(secret) == 43
    assert python["dist_env"] == str(rig.root / "dist")
    assert all(secret not in word for e in (python, front) for word in e["argv"]), \
        "the secret never goes on a command line"

    state = rig.state()
    assert state == {
        "format": 1, "brain": str(rig.brain), "public_host": "127.0.0.1",
        "public_port": PUBLIC, "private_port": PRIVATE,
        "answers_at": f"http://127.0.0.1:{PUBLIC}", "secret": secret,
        "front": {"pid": state["front"]["pid"], "executable": sys.executable,
                  "log": str(rig.run_dir / "front.log")},
        "python": {"pid": state["python"]["pid"], "executable": sys.executable,
                   "log": str(rig.run_dir / "python.log")}}

    # Both outlived the launcher, with their output in their logs.
    assert get(PUBLIC)["who"] == "front" and get(PRIVATE)["who"] == "python"
    assert "python stand-in" in (rig.run_dir / "python.log").read_text(encoding="utf-8")
    assert "front stand-in" in (rig.run_dir / "front.log").read_text(encoding="utf-8")


def test_a_second_launch_finds_the_ports_taken_and_touches_nothing(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = rig.launch(*rig.args())
    assert done.returncode == 3 and "in use" in done.stderr
    assert rig.state() == before
    assert get(PUBLIC)["pid"] == rig.events("front")[0]["pid"]


def test_the_state_file_is_this_users_alone(rig):
    assert rig.launch(*rig.args()).returncode == 0
    said = subprocess.run(["icacls", str(rig.run_dir / "launch.json")], capture_output=True,
                          text=True).stdout
    trustees = [line for line in said.splitlines() if ":(" in line]
    assert len(trustees) == 1 and os.environ["USERNAME"].lower() in trustees[0].lower(), said
    assert "(F)" in trustees[0] and "(I)" not in trustees[0], said
    assert not [p for p in rig.run_dir.iterdir() if p.suffix == ".tmp"]


def test_upstream_goes_to_the_front_alone_and_is_not_remembered(rig):
    upstream = "http://127.0.0.1:8873"
    assert rig.launch(*rig.args("--upstream", upstream)).returncode == 0
    python, front = rig.events("python")[0], rig.events("front")[0]
    assert front["argv"][front["argv"].index("--upstream") + 1] == upstream
    assert upstream not in " ".join(python["argv"])
    assert str(PRIVATE) in python["argv"], "Python and the wait don't change"
    assert upstream not in (rig.run_dir / "launch.json").read_text(encoding="utf-8")
    assert upstream not in (rig.run_dir / "launch-args.json").read_text(encoding="utf-8")

    stop = rig.launch("stop", "--run-dir", str(rig.run_dir), "--front")
    assert stop.returncode == 0, stop.stderr
    wait_free(PUBLIC)
    assert rig.launch("--only", "front", "--run-dir", str(rig.run_dir),
                      "--front", sys.executable,
                      str(rig.brain)).returncode == 0
    again = rig.events("front")[-1]
    assert again["argv"][again["argv"].index("--upstream") + 1] == f"http://127.0.0.1:{PRIVATE}"

    stop = rig.launch("stop", "--run-dir", str(rig.run_dir), "--front")
    assert stop.returncode == 0, stop.stderr
    wait_free(PUBLIC)
    assert rig.launch(*rig.args("--only", "front", "--upstream", upstream)).returncode == 0
    last = rig.events("front")[-1]
    assert last["argv"][last["argv"].index("--upstream") + 1] == upstream


def test_only_front_takes_the_secret_and_ports_from_the_state_file(rig):
    assert rig.launch(*rig.args("--route-table", str(STANDIN))).returncode == 0
    first = rig.state()
    python_pid = first["python"]["pid"]
    assert rig.launch("stop", "--run-dir", str(rig.run_dir), "--front").returncode == 0
    assert not alive(first["front"]["pid"])
    assert alive(python_pid), "stopping the front leaves Python running"
    wait_free(PUBLIC)

    done = rig.launch("--only", "front", "--run-dir", str(rig.run_dir), "--front", sys.executable,
                      str(rig.brain))
    assert done.returncode == 0, done.stderr
    second = rig.state()
    assert second["secret"] == first["secret"]
    assert second["python"] == first["python"]
    assert second["front"]["pid"] != first["front"]["pid"]
    front = rig.events("front")[-1]
    assert front["secret"] == first["secret"]
    assert front["argv"][front["argv"].index("--route-table") + 1] == str(STANDIN), \
        "the table a front ran with is the table its replacement runs with"
    assert len(rig.events("python")) == 1


def test_only_python_takes_the_secret_and_leaves_the_front(rig):
    assert rig.launch(*rig.args("--mars", "mars here")).returncode == 0
    first = rig.state()
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(first["python"]["pid"])],
                   capture_output=True)
    wait_free(PRIVATE)
    done = rig.launch("--only", "python", "--run-dir", str(rig.run_dir))
    assert done.returncode == 0, done.stderr
    second = rig.state()
    assert second["secret"] == first["secret"] and second["front"] == first["front"]
    assert second["python"]["pid"] != first["python"]["pid"]
    python = rig.events("python")[-1]
    assert python["secret"] == first["secret"]
    assert "--mars" in python["argv"] and "mars here" in python["argv"]
    assert len(rig.events("front")) == 1


@pytest.mark.parametrize("only", ["front", "python"])
def test_only_without_a_state_file_is_refused(rig, only):
    rig.run_dir.mkdir()
    done = rig.launch("--only", only, "--run-dir", str(rig.run_dir))
    assert done.returncode == 3 and "launch.json" in done.stderr


def test_only_refuses_what_contradicts_the_state_file(rig):
    assert rig.launch(*rig.args()).returncode == 0
    done = rig.launch(*rig.args("--only", "front", port=8872))
    assert done.returncode == 3 and "says public port" in done.stderr


def test_only_refuses_a_port_in_use(rig):
    assert rig.launch(*rig.args()).returncode == 0
    done = rig.launch("--only", "front", "--run-dir", str(rig.run_dir))
    assert done.returncode == 3 and "in use" in done.stderr


def test_stop_refuses_with_nothing_there_and_exits_when_the_front_has(rig):
    rig.run_dir.mkdir()
    done = rig.launch("stop", "--run-dir", str(rig.run_dir), "--front")
    assert done.returncode == 3 and "launch.json" in done.stderr

    assert rig.launch(*rig.args()).returncode == 0
    state = rig.state()
    assert rig.launch("stop", "--run-dir", str(rig.run_dir), "--front").returncode == 0
    assert not alive(state["front"]["pid"])

    done = rig.launch("stop", "--run-dir", str(rig.run_dir), "--front")
    assert done.returncode == 3 and "no front took the stop" in done.stderr


def test_stop_with_the_wrong_secret_is_answered_and_changes_nothing(rig):
    assert rig.launch(*rig.args()).returncode == 0
    path = rig.run_dir / "launch.json"
    state = rig.state()
    forged = {**state, "secret": "not-it"}
    other = rig.root / "other"
    other.mkdir()
    (other / "launch.json").write_text(json.dumps(forged), encoding="utf-8")
    done = rig.launch("stop", "--run-dir", str(other), "--front")
    assert done.returncode == 3 and "answered the stop with 404" in done.stderr
    assert alive(state["front"]["pid"]) and path.exists()


def test_attached_stays_as_their_parent_and_a_tree_kill_leaves_nothing(rig):
    env = {**os.environ, "MENTIS_STANDIN_DIR": str(rig.dir), "PYTHONDONTWRITEBYTECODE": "1"}
    launcher = subprocess.Popen([str(LAUNCH), *rig.args("--attached")], env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
    try:
        line = launcher.stdout.readline().strip()
        assert line == f"Mentis on http://127.0.0.1:{PUBLIC}"
        assert launcher.poll() is None, "it stays"
        state = rig.state()
        parents = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={launcher.pid}').ProcessId"],
            capture_output=True, text=True).stdout.split()
        assert {str(state["front"]["pid"]), str(state["python"]["pid"])} <= set(parents)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(launcher.pid)], capture_output=True)
        launcher.wait(timeout=30)
    wait_free(PUBLIC)
    wait_free(PRIVATE)
    for event in rig.events():
        assert not alive(event["pid"])


def powershell(script: str, *args: str, answer: str | None = None, env=None):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(CUTOVER / script), *args], capture_output=True, text=True,
                          input=answer if answer is not None else "", env=env, timeout=180)


def script_env(rig) -> dict:
    return {**os.environ, "MENTIS_STANDIN_DIR": str(rig.dir), "PYTHONDONTWRITEBYTECODE": "1"}


ACTIVE = {"activity": {"open": 1, "items": ["opr-1"]},
          "runs": [{"id": "opr-1", "participant_name": "@A", "runtime": "claude",
                    "state": "running", "words": "running; latest event: x"}]}


def deploy(rig, *extra, answer=None):
    return powershell("deploy-front.ps1", "-Front", sys.executable, "-RunDir", str(rig.run_dir),
                      "-Launcher", str(LAUNCH), *extra, answer=answer, env=script_env(rig))


def test_deploy_with_nobody_to_answer_changes_nothing_and_exits_3(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig)
    assert done.returncode == 3, done.stdout + done.stderr
    assert "No active runs" in done.stdout and "Nothing was changed" in done.stdout
    assert rig.state() == before and alive(before["front"]["pid"])


@pytest.mark.parametrize("flags", [(), ("-YesWhenIdle",)])
def test_deploy_with_a_run_active_lists_it_and_asks_whatever_the_flag(rig, flags):
    rig.behaviour(ACTIVE)
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig, *flags, answer="no\n")
    assert done.returncode == 3, done.stdout + done.stderr
    assert "opr-1" in done.stdout and "running" in done.stdout
    assert "Replace the front?" in done.stdout and "Nothing was changed" in done.stdout
    assert rig.state() == before and alive(before["front"]["pid"])


def test_deploy_when_the_list_cannot_be_read_asks_even_with_the_standing_yes(rig):
    rig.behaviour({"activity": {"open": "not a number", "items": []}})
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig, "-YesWhenIdle")
    assert done.returncode == 3, done.stdout + done.stderr
    assert "could not be read" in done.stdout
    assert rig.state() == before


def test_deploy_when_idle_with_the_standing_yes_replaces_the_front_and_says_what_changed(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig, "-YesWhenIdle")
    assert done.returncode == 0, done.stdout + done.stderr
    after = rig.state()
    assert after["front"]["pid"] != before["front"]["pid"]
    assert after["python"] == before["python"] and after["secret"] == before["secret"]
    assert alive(before["python"]["pid"])
    assert not alive(before["front"]["pid"])
    assert get(PUBLIC)["pid"] == rig.events("front")[-1]["pid"]
    assert "old sha256" in done.stdout and "new sha256" in done.stdout and "gap" in done.stdout
    assert len(rig.events("python")) == 1
    time.sleep(QUIET_S)
    assert alive(after["front"]["pid"]), "the new front outlives the script"


def test_deploy_answered_yes_once_with_more_open_than_it_can_list_goes_on(rig):
    rig.behaviour({"activity": {"open": 100, "items": ["opr-1"]}, "runs": ACTIVE["runs"]})
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig, answer="yes\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "and 99 more" in done.stdout
    assert done.stdout.count("Replace the front?") == 1
    assert rig.state()["front"]["pid"] != before["front"]["pid"]


def test_deploy_answered_yes_with_a_run_active_replaces_the_front(rig):
    rig.behaviour(ACTIVE)
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    done = deploy(rig, answer="yes\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert rig.state()["front"]["pid"] != before["front"]["pid"]


def rollback(rig, answer=None):
    return powershell("rollback-to-python.ps1", "-RunDir", str(rig.run_dir),
                      "-Launcher", str(LAUNCH), answer=answer, env=script_env(rig))


def test_rollback_always_asks_and_answered_no_changes_nothing(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    for answer in ("no\n", ""):
        done = rollback(rig, answer=answer)
        assert done.returncode == 3, done.stdout + done.stderr
        assert "Nothing was changed" in done.stdout
    assert rig.state() == before
    assert alive(before["front"]["pid"]) and alive(before["python"]["pid"])


def test_rollback_goes_on_when_the_front_is_already_dead(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(before["front"]["pid"])],
                   capture_output=True)
    wait_free(PUBLIC)
    done = rollback(rig, answer="yes\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "could not be read" in done.stdout
    assert "no front took the stop" in done.stdout
    assert get(PUBLIC)["who"] == "python"
    assert not alive(before["python"]["pid"])


def test_deploy_says_why_when_no_front_takes_the_stop_and_changes_nothing(rig):
    assert rig.launch(*rig.args()).returncode == 0
    before = rig.state()
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(before["front"]["pid"])],
                   capture_output=True)
    wait_free(PUBLIC)
    done = deploy(rig, answer="yes\n")
    assert done.returncode == 3, done.stdout + done.stderr
    assert "no front took the stop" in done.stderr
    assert rig.state() == before
    assert alive(before["python"]["pid"])


def test_rollback_answered_yes_is_python_alone_on_the_public_port(rig):
    assert rig.launch(*rig.args("--mars", '"C:\\x y\\mars.exe" stdio')).returncode == 0
    before = rig.state()
    done = rollback(rig, answer="yes\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert get(PUBLIC)["who"] == "python", "no front"
    wait_free(PRIVATE)
    assert not alive(before["front"]["pid"]) and not alive(before["python"]["pid"])
    assert not (rig.run_dir / "launch.json").exists()
    python = rig.events("python")[-1]
    assert python["secret"] is None, "Python alone has no secret"
    assert "--answers-at" not in python["argv"]
    assert python["argv"][python["argv"].index("--port") + 1] == str(PUBLIC)
    assert python["mars_env"] == '"C:\\x y\\mars.exe" stdio'
    assert python["dist_env"] == str(rig.root / "dist")
    assert pathlib.Path(python["cwd"]) == rig.code
