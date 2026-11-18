"""Background work opens no terminal window on the owner's desktop (Windows).

What these prove, on a real Windows desktop: the process the release tool starts detached
(`mentis_env.detached_start`) and everything below it have a console whose window is NOT
visible, while their output, their exit code and stopping them by pid all still work.

What they do not prove: that no other program on the machine opens a window. A creation flag
or a hidden parent says nothing about a grandchild that starts itself detached (agy's updater
did exactly that; MARS switches it off, tested there). The watcher in the evidence folder
(console-popups/scripts/watch_windows.py) is what observes the desktop itself.

The visible control is off unless MENTIS_TEST_VISIBLE_CONTROL=1: it opens a real terminal
window, which is the thing this work exists to stop.
"""

import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "env"))
import mentis_env as me  # noqa: E402

windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows consoles")

#: Says what console this process has, starts one more of itself with nothing special asked
#: (the nested child), and the deepest one writes to both streams and then waits or exits.
PROBE = r'''
import ctypes, json, os, subprocess, sys, time
out, depth, wait, code = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
k32, u32 = ctypes.WinDLL("kernel32"), ctypes.WinDLL("user32")
k32.GetConsoleWindow.restype = ctypes.c_void_p
hwnd = k32.GetConsoleWindow()
said = {"pid": os.getpid(), "console_window": hwnd or 0,
        "visible": bool(hwnd and u32.IsWindowVisible(ctypes.c_void_p(hwnd)))}
with open(f"{out}.{depth}.json", "w") as f:
    json.dump(said, f)
if depth:
    sys.exit(subprocess.run([sys.executable, __file__, out, str(depth - 1), str(wait), str(code)]).returncode)
print("the deepest one, on stdout", flush=True)
print("and on stderr", file=sys.stderr, flush=True)
time.sleep(wait)
sys.exit(code)
'''


def _start(tmp_path, script: str, *, wait: float, code: int, depth: int = 2):
    """Start the probe the way `start_env` starts the launcher: a .cmd that sends both streams
    to a log and leaves the exit code in a file, run by `cmd.exe /d /c` through `script`."""
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE, "utf-8")
    cmd = tmp_path / "launch.cmd"
    cmd.write_text("@echo off\n"
                   f'"{sys.executable}" "{probe}" "{tmp_path / "said"}" {depth} {wait} {code} '
                   f'1>>"{tmp_path / "launch.log"}" 2>&1\n'
                   f'echo %errorlevel% >"{tmp_path / "launch.exit"}"\n', "utf-8")
    assert me.ps(script(f'cmd.exe /d /c "{cmd}"', tmp_path)).strip() == "0"


def _said(tmp_path, depth, within=30.0):
    path = tmp_path / f"said.{depth}.json"
    deadline = time.time() + within
    while time.time() < deadline:
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError(f"the probe at depth {depth} never reported")


def _wait_for(path: pathlib.Path, within=30.0) -> str:
    deadline = time.time() + within
    while time.time() < deadline:
        if path.is_file() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(0.1)
    raise AssertionError(f"{path.name} never appeared")


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                         creationflags=subprocess.CREATE_NO_WINDOW).stdout
    return str(pid) in out


def test_the_detached_start_asks_for_a_hidden_window():
    script = me.detached_start('cmd.exe /d /c "C:\\x\\launch.cmd"', "C:\\x")
    assert "Win32_ProcessStartup" in script and "ShowWindow = [uint16]0" in script
    assert "ProcessStartupInformation = $s" in script and "Win32_Process -MethodName Create" in script


@windows
def test_a_detached_start_and_everything_below_it_has_no_visible_console(tmp_path):
    _start(tmp_path, me.detached_start, wait=0, code=0)
    assert _wait_for(tmp_path / "launch.exit") == "0"
    top, middle, deepest = (_said(tmp_path, d) for d in (2, 1, 0))
    for one in (top, middle, deepest):
        assert one["visible"] is False, one
    # NESTED CHILDREN OPEN NO CONSOLE OF THEIR OWN: there is a real (hidden) one to inherit, so
    # a child started with nothing special asked shares its parent's rather than getting a new,
    # visible one, which is what happens below a parent that has none.
    assert top["console_window"] and middle["console_window"] == top["console_window"] == deepest["console_window"]
    # OUTPUT IS STILL CAPTURED, both streams, from the deepest process.
    log = (tmp_path / "launch.log").read_text("utf-8", "replace")
    assert "the deepest one, on stdout" in log and "and on stderr" in log


@windows
def test_a_hidden_start_that_fails_still_reports_its_exit_code_and_its_error_output(tmp_path):
    _start(tmp_path, me.detached_start, wait=0, code=3)
    assert _wait_for(tmp_path / "launch.exit") == "3"
    assert "and on stderr" in (tmp_path / "launch.log").read_text("utf-8", "replace")
    assert _said(tmp_path, 0)["visible"] is False


@windows
def test_a_hidden_tree_is_still_stopped_by_its_pid(tmp_path):
    _start(tmp_path, me.detached_start, wait=120, code=0)
    top, deepest = _said(tmp_path, 2), _said(tmp_path, 0)
    assert _alive(top["pid"]) and _alive(deepest["pid"])
    subprocess.run(["taskkill", "/PID", str(top["pid"]), "/T", "/F"], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.time() + 15
    while time.time() < deadline and (_alive(top["pid"]) or _alive(deepest["pid"])):
        time.sleep(0.2)
    assert not _alive(top["pid"]) and not _alive(deepest["pid"])


@windows
@pytest.mark.skipif(os.environ.get("MENTIS_TEST_VISIBLE_CONTROL") != "1",
                    reason="opens a real terminal window; set MENTIS_TEST_VISIBLE_CONTROL=1 to run it")
def test_control_the_same_start_without_the_hidden_window_is_visible(tmp_path):
    """The probe can tell: the start as it was before (no startup information) reports a visible
    console window. An interactive terminal somebody asks for is this case, and is untouched."""
    def as_before(command_line, cwd):
        return ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ "
                f"CommandLine = '{command_line}'; CurrentDirectory = '{cwd}' }}; $r.ReturnValue")
    _start(tmp_path, as_before, wait=1.5, code=0)
    assert _said(tmp_path, 2)["visible"] is True
    assert _wait_for(tmp_path / "launch.exit") == "0"
