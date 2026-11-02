"""docs/rust/contracts/bench.md, on a stand-in server: --command, what each result records, and the
exits rows B and N depend on. A row treats any nonzero exit as failed."""
import hashlib, json, os, pathlib, shutil, sqlite3, subprocess, sys

import pytest

from .conftest import G, PORT, REPO, TOOLS, point_gate_at, run_main, stand_in_command
import answers as A
import run_workload as RW
import wl_common as W

FAST = ["--rounds", "1", "--skip-statements", "--warm-s", "0", "--person-s", "0.2", "--agent-s", "1.5",
        "--drain-s", "5", "--settle-s", "0", "--boot-quiet-s", "0", "--warm-walk-s", "1", "--warm-cell-s", "0.1",
        "--warm-convs", "1", "--port", str(PORT), "--python", sys.executable]


def workload(monkeypatch, code, master, label="L", levels="idle,agents-1", extra=()):
    return run_main(RW, monkeypatch, ["--command", stand_in_command(), "--code", str(code), "--brain", str(master),
                                      "--label", label, "--levels", levels, *FAST, *extra])


def answers_record(monkeypatch, code, master, label="L", extra=()):
    return run_main(A, monkeypatch, ["record", "--command", stand_in_command(), "--code", str(code),
                                     "--brain", str(master), "--label", label, "--port", str(PORT), *extra])


def tool(script, home, *args):
    """A real exit code from a real process, for the tools that take no gate."""
    return subprocess.run([sys.executable, "-B", str(TOOLS / script), *args], capture_output=True, text=True,
                          env={**os.environ, "BENCH_HOME": str(home)}, timeout=120)


def result(sha="", brain="d1", valid=True, bad=0, busy=0):
    return {"label": "x", "workload_sha": sha or G.workload_sha(), "code": {"commit": "c", "dir": "d"},
            "started": "s", "brain": {"master": "m", "corpus_db_sha256": brain},
            "isolation": {"state": "released", "valid": valid, "invalid_reasons": [] if valid else ["seen"]},
            "levels": {"idle": {"aggregate": {
                "runs": 1, "client_cores_mean": 0, "server": {"cores_mean": 1, "rss_mb_max": 2},
                "probes": {"pulse": {"count": 1, "p50": 1, "p95": 1, "max": 1, "p50_by_run": [1], "p95_by_run": [1],
                                     "count_by_run": [1], "errors": 0, "bad_status": bad}},
                "background": {"kind": "mix", "n": 1, "pace": 0, "p50": 1, "p95": 1, "throughput_qps_mean": 1,
                               "workers_looping_by_run": [1], "errors": 0, "bad_status": 0, "busy_503": busy}}}},
            "cold": {}, "statements": None}


def put(home, label, res, name="workload.json"):
    d = home / "results" / label
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(res), encoding="utf-8")


def answer_set(sha="", brain="d1", valid=True, status=200):
    r = result(sha, brain, valid)
    r.update(normalised={"counts": {}, "volatile_keys_why": {}},
             answers={"pulse": {"status": status, "json": {}}, "turns": {"status": 200, "json": {}},
                      "topics load": {"status": 200, "json": {"topics": [{"t": 1}, {"t": 2}]}}})
    return r


# ---- the command -----------------------------------------------------------------------------


@pytest.mark.parametrize("text,word", [
    ("not json", "not JSON"),
    ('{"a": 1}', "JSON array"),
    ("[]", "JSON array"),
    ('["x", 1]', "JSON array"),
    (json.dumps([sys.executable, "{brain}", "{port}", "{brian}"]), "unknown placeholders"),
    (json.dumps([sys.executable, "--port", "{port}"]), "brain"),
    (json.dumps([sys.executable, "{brain}"]), "port"),
    (json.dumps(["C:/no/such/thing.exe", "{brain}", "{port}"]), "not an executable"),
])
def test_a_bad_command_is_refused_with_nothing_run(text, word, capsys):
    with pytest.raises(G.Refused) as e:
        RW.parse_command(text)
    assert e.value.code == G.REFUSED and word in e.value.why


def test_the_contracts_two_commands_parse_and_fill(tmp_path, monkeypatch):
    python = json.dumps([sys.executable, "-m", "mentis.web", "{brain}", "--port", "{port}", "--workspace", "{ws}", "--mars", "{mars}"])
    cmd = RW.parse_command(python)
    assert RW.fill(cmd, brain="B", port=8831, ws="W", mars=RW.NO_MARS, run="R")[1:] == [
        "-m", "mentis.web", "B", "--port", "8831", "--workspace", "W", "--mars", "workload-no-mars-here"]
    assert RW.fill(["--run-dir={run}\\x"], run="R") == ["--run-dir=R\\x"]


def test_binary_records_each_executable_but_python_and_the_launchers_default_front(tmp_path):
    launch, front, other = tmp_path / "mentis-launch.exe", tmp_path / "mentis-server.exe", tmp_path / "x.exe"
    for f, text in ((launch, b"launch"), (front, b"front"), (other, b"other")):
        f.write_bytes(text)
    python = tmp_path / "python.exe"
    python.write_bytes(b"py")
    # shutil.which wants an executable file; on Windows that is its suffix
    got = RW.binaries([str(launch), "{brain}", "--python", str(python), "--tool", str(other)])
    assert [(pathlib.Path(b["path"]).name, b["sha256"]) for b in got] == [
        ("mentis-launch.exe", hashlib.sha256(b"launch").hexdigest()),
        ("x.exe", hashlib.sha256(b"other").hexdigest()),
        ("mentis-server.exe", hashlib.sha256(b"front").hexdigest())]
    assert RW.binaries([str(python), "-m", "mentis.web"]) == []
    named = RW.binaries([str(launch), "--front", str(other)])
    assert "mentis-server.exe" not in [pathlib.Path(b["path"]).name for b in named]


def test_tools_bench_holds_code_and_what_it_writes_is_outside_the_repository():
    for f in TOOLS.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            assert f.suffix in (".py", ".md"), f
    env = {k: v for k, v in os.environ.items() if k != "BENCH_HOME"}
    out = subprocess.run([sys.executable, "-B", "-c",
                          "import sys; sys.path.insert(0, sys.argv[1]); import benchgate as G; "
                          "print(G.LOCK); print(G.RESULTS); print(G.BUNDLE_DIR); print(G.RUN)", str(TOOLS)],
                         capture_output=True, text=True, env=env, check=True).stdout.split("\n")
    wanted = pathlib.Path(r"C:\Work\Mentis-workspace\day-to-day")
    for line in filter(None, out):
        assert pathlib.Path(line).is_relative_to(wanted) and not pathlib.Path(line).is_relative_to(REPO)


# ---- run_workload ----------------------------------------------------------------------------


def test_a_clean_run_exits_0_and_records_what_the_contract_lists(gate, master, code, monkeypatch):
    # kept: the run directory holds what the command was given
    assert workload(monkeypatch, code, master, extra=["--keep-run-dir"]) == 0
    r = json.loads((gate / "results" / "L" / "workload.json").read_text(encoding="utf-8"))
    assert r["command"] == json.loads(stand_in_command())
    assert r["binary"] == []                                    # only a python and its script
    assert r["brain"]["corpus_db_sha256"] == hashlib.sha256((master / "corpus.db").read_bytes()).hexdigest()
    assert r["isolation"]["valid"] and r["workload_sha"] == G.workload_sha() and r["code"]["commit"] == "abc1234"
    assert r["record_delta"]["new_entry"] == 0
    a = r["levels"]["agents-1"]["aggregate"]
    # the agent levels' timing for the two reads C0 v2 lacks
    assert a["probes"]["agent_kinds"]["count"] >= 1 and a["probes"]["agent_history"]["count"] >= 1
    # by process name, as well as summed
    names = a["server"]["by_process"]
    assert names and all(k.lower().startswith("python") for k in names)
    assert {"cores_by_run", "cores_mean", "rss_mb_max", "rss_mb_mean"} <= set(next(iter(names.values())))
    assert sum(p["cores"] for p in r["levels"]["idle"]["runs"][0]["server"]["by_process"].values()) >= 0


def test_what_the_bench_guarantees_the_command(gate, master, code, monkeypatch):
    monkeypatch.setenv("MENTIS_SOMETHING", "1")
    monkeypatch.setenv("PATH", os.pathsep.join([r"C:\has-mars-in-it", r"C:\Work\Mentis\x", os.environ["PATH"]]))
    assert workload(monkeypatch, code, master, levels="idle", extra=["--keep-run-dir", "--server-env", "EXTRA=2"]) == 0
    run = gate / "run" / "L" / "main"
    given = json.loads((run / "given.json").read_text())
    assert given["argv"] == [str(run / "brain"), "--port", str(PORT), "--workspace", str(run / "ws"),
                             "--mars", "workload-no-mars-here", "--run", str(run)]
    assert pathlib.Path(given["cwd"]) == run
    env = given["env"]
    assert not [k for k in env if k.upper().startswith("MENTIS") and k.upper() != "MENTIS_FLUID_DIST"]
    assert env["MENTIS_FLUID_DIST"] == str(gate / "bundle") and env["PYTHONPATH"] == str(code)
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTHONIOENCODING"] == "utf-8" and env["EXTRA"] == "2"
    assert not [p for p in env["PATH"].split(os.pathsep) if "mars" in p.lower() or "mentis" in p.lower()]
    # fresh, and writable though the master's files are not
    assert sorted(given["brain_files"]) == ["corpus.db", "derived", "mentis-corpus.json", "presentation"]
    assert given["corpus_writable"] and given["corpus_json_writable"]
    assert not os.access(master / "corpus.db", os.W_OK)
    assert "stand-in up" in (run / "server.log").read_text()


def test_the_master_is_never_opened_through_sqlite_and_is_left_unchanged(gate, master, code, monkeypatch):
    before = {p: p.read_bytes() for p in master.rglob("*") if p.is_file()}
    opened = []
    real = sqlite3.connect

    def spy(database, *a, **k):
        opened.append(str(database))
        return real(database, *a, **k)
    monkeypatch.setattr(sqlite3, "connect", spy)
    assert workload(monkeypatch, code, master, levels="idle") == 0
    assert answers_record(monkeypatch, code, master, label="M") == 0
    assert opened and not [x for x in opened if master.as_posix() in x.replace("\\", "/")]
    assert {p: p.read_bytes() for p in master.rglob("*") if p.is_file()} == before


def test_a_bad_status_exits_nonzero_and_keeps_the_result(gate, master, code, monkeypatch, capsys):
    assert workload(monkeypatch, code, master, levels="idle", extra=["--server-env", "STAND_IN_BAD=/fluid/api/topics"]) == G.FAILED
    assert "BAD STATUS: idle topic_lookup" in capsys.readouterr().out
    r = json.loads((gate / "results" / "L" / "workload.json").read_text(encoding="utf-8"))
    assert r["isolation"]["valid"] and W.bad_statuses(r)


def test_an_invalid_run_exits_nonzero(gate, master, code, monkeypatch, capsys):
    real = G.Hold.finish

    def seen(self, completed=True):
        if not self.record:
            self.invalidate("seen: a cargo")
        return real(self, completed)
    monkeypatch.setattr(G.Hold, "finish", seen)
    assert workload(monkeypatch, code, master, levels="idle") == G.FAILED
    assert "INVALID: seen: a cargo" in capsys.readouterr().out


@pytest.mark.parametrize("level,where,word", [
    ({"background": {"bad_status": 1}}, "background", "1 bad status"),
    ({"background": {"errors": 1}}, "background", "1 errors"),
    ({"background": {"busy_503": 1}}, "background", "1 503s"),
    ({"writes": {"errors": 2}}, "writes", "2 errors"),
    ({"probes": {"pulse": {"errors": 1, "bad_status": 0}}}, "pulse", "1 errors"),
])
def test_bad_statuses_finds_each_kind(level, where, word):
    got = W.bad_statuses({"levels": {"n-sql": {"aggregate": level}}})
    assert len(got) == 1 and where in got[0] and word in got[0]


def test_bad_statuses_looks_at_cold_and_statements_and_passes_a_clean_result():
    assert W.bad_statuses(result(sha="s")) == []
    assert W.bad_statuses({"cold": {"by_probe": {"cold_pulse": {"bad_status": 1, "errors": 0}}}})
    assert W.bad_statuses({"statements": {"reads": {"pulse": {"warm": {"status": 500}}}}})
    assert W.bad_statuses({"statements": {"reads": {"post_window": {"warm_data_statements": 3, "note": "derived"}}}}) == []


def test_a_label_that_has_a_result_is_refused(gate, master, code, monkeypatch):
    put(gate, "L", {"already": True})
    assert workload(monkeypatch, code, master, levels="idle") == G.REFUSED
    assert json.loads((gate / "results" / "L" / "workload.json").read_text()) == {"already": True}


def test_a_port_outside_the_range_is_refused(gate, master, code, monkeypatch):
    rc = run_main(RW, monkeypatch, ["--command", stand_in_command(), "--code", str(code), "--label", "L", "--port", "8851"])
    assert rc != 0 and not (gate / "results" / "L").exists()


def test_a_held_gate_refuses_exit_3_from_the_real_entry_point(tmp_path, master, code):
    home = tmp_path / "h"
    home.mkdir()
    (home / "bundle").mkdir()
    (home / "bundle" / "render-check.js").write_text("x")
    (home / "RUNLOCK").write_text(json.dumps({"holder": "somebody", "pid": os.getpid(), "purpose": "p"}))
    got = tool("run_workload.py", home, "--command", stand_in_command(), "--code", str(code), "--brain", str(master),
               "--label", "L", "--port", str(PORT))
    assert got.returncode == G.REFUSED and "held by somebody" in got.stderr
    assert not (home / "results" / "L" / "workload.json").exists()


# ---- compare.py ------------------------------------------------------------------------------


@pytest.mark.parametrize("args", [[], ["--noise"]])
def test_compare_exits_0_on_two_comparable_clean_results(home, args):
    put(home, "baseline", result())
    put(home, "R1", result())
    got = tool("compare.py", home, *args, "baseline", "R1")
    assert got.returncode == 0, got.stderr
    assert "pulse" in got.stdout


@pytest.mark.parametrize("args", [[], ["--noise"]])
@pytest.mark.parametrize("r1,word", [
    (dict(valid=False), "marked invalid"),
    (dict(sha="different"), "workload_sha differs"),
    (dict(brain="d2"), "the Brain differs"),
    (dict(brain=None), "no brain digest"),
])
def test_compare_refuses_exit_3(home, args, r1, word):
    put(home, "baseline", result())
    put(home, "R1", result(**r1))
    got = tool("compare.py", home, *args, "baseline", "R1")
    assert got.returncode == G.REFUSED and word in got.stderr and "### pulse" not in got.stdout


@pytest.mark.parametrize("args", [[], ["--noise"]])
@pytest.mark.parametrize("r1", [dict(bad=1), dict(busy=1)])
def test_compare_exits_nonzero_on_a_bad_status_with_its_tables(home, args, r1):
    put(home, "baseline", result())
    put(home, "R1", result(**r1))
    got = tool("compare.py", home, *args, "baseline", "R1")
    assert got.returncode == G.FAILED and "BAD STATUS: R1" in got.stderr and "pulse" in got.stdout


def test_compare_exits_nonzero_on_a_missing_result(home):
    put(home, "baseline", result())
    assert tool("compare.py", home, "baseline", "R1").returncode != 0


def test_compare_evidence_reads_an_invalid_result_and_judges_nothing(home):
    put(home, "old", result(valid=False, bad=1))
    got = tool("compare.py", home, "--evidence", "old")
    assert got.returncode == 0 and "EVIDENCE ONLY" in got.stdout


def test_compare_shows_processes_apart(home):
    r = result()
    r["levels"]["idle"]["aggregate"]["server"]["by_process"] = {
        "python.exe": {"cores_mean": 1.5, "rss_mb_max": 900}, "mentis-server.exe": {"cores_mean": 0.1, "rss_mb_max": 20}}
    put(home, "baseline", r)
    put(home, "R1", r)
    got = tool("compare.py", home, "baseline", "R1")
    assert got.returncode == 0 and "python.exe 1.5 cores, 900 MB" in got.stdout and "mentis-server.exe 0.1 cores" in got.stdout


# ---- answers.py record -----------------------------------------------------------------------


def test_record_takes_brain_and_exits_0_with_47_reads(gate, master, code, monkeypatch):
    assert answers_record(monkeypatch, code, master, extra=["--twice"]) == 0
    r = json.loads((gate / "results" / "L" / "answers.json").read_text(encoding="utf-8"))
    assert len(r["answers"]) == 47 and {v["status"] for v in r["answers"].values()} == {200}
    assert r["brain"] == {"master": str(master), "corpus_db_sha256": hashlib.sha256((master / "corpus.db").read_bytes()).hexdigest()}
    assert r["command"] == json.loads(stand_in_command()) and r["binary"] == []
    assert r["isolation"]["valid"] and r["code"]["commit"] == "abc1234"
    assert (gate / "results" / "L" / "answers-second.json").exists() and (gate / "results" / "L" / "answers-self.md").exists()


def test_record_exits_nonzero_on_a_bad_status(gate, master, code, monkeypatch):
    assert answers_record(monkeypatch, code, master, extra=["--server-env", "STAND_IN_BAD=/api/owed"]) == G.FAILED


def test_record_exits_nonzero_on_an_invalid_recording(gate, master, code, monkeypatch):
    real = G.Hold.finish

    def seen(self, completed=True):
        if not self.record:
            self.invalidate("seen: a pytest")
        return real(self, completed)
    monkeypatch.setattr(G.Hold, "finish", seen)
    assert answers_record(monkeypatch, code, master) == G.FAILED


def test_record_twice_exits_nonzero_when_two_copies_differ(gate, master, code, monkeypatch):
    assert answers_record(monkeypatch, code, master, extra=["--twice", "--server-env", "STAND_IN_VARY=1"]) == G.FAILED
    assert "differ" in (gate / "results" / "L" / "answers-self.md").read_text(encoding="utf-8")


def test_record_refuses_a_label_that_has_answers(gate, master, code, monkeypatch):
    put(gate, "L", {"already": True}, "answers.json")
    assert answers_record(monkeypatch, code, master) == G.REFUSED
    assert json.loads((gate / "results" / "L" / "answers.json").read_text()) == {"already": True}


def test_record_refuses_a_port_outside_the_range(gate, master, code, monkeypatch):
    rc = run_main(A, monkeypatch, ["record", "--command", stand_in_command(), "--code", str(code),
                                   "--brain", str(master), "--label", "L", "--port", "8851"])
    assert rc != 0 and not (gate / "results" / "L").exists()


def test_record_watches_the_code_for_change(gate, master, code, monkeypatch):
    calls = []
    real = G.commit_of

    def moving(d):
        calls.append(d)
        got = real(d)
        return {**got, "commit": "abc1234" if len(calls) == 1 else "moved"}
    monkeypatch.setattr(G, "commit_of", moving)
    assert answers_record(monkeypatch, code, master) == G.FAILED
    r = json.loads((gate / "results" / "L" / "answers.json").read_text(encoding="utf-8"))
    assert any("the code changed" in x for x in r["isolation"]["invalid_reasons"])


# ---- answers.py compare and selftest ---------------------------------------------------------


def test_answers_compare_exits_0_when_identical(home):
    put(home, "baseline", answer_set(), "answers.json")
    put(home, "R1", answer_set(), "answers.json")
    got = tool("answers.py", home, "compare", "baseline", "R1")
    assert got.returncode == 0, got.stderr
    assert "0 differences" in got.stdout


def test_answers_compare_exits_nonzero_on_any_difference(home):
    other = answer_set()
    other["answers"]["turns"]["json"] = {"changed": 1}
    put(home, "baseline", answer_set(), "answers.json")
    put(home, "R1", other, "answers.json")
    got = tool("answers.py", home, "compare", "baseline", "R1")
    assert got.returncode == G.FAILED and "1 differences" in got.stdout
    assert (home / "results" / "R1" / "answers-vs-baseline.md").exists()


def test_answers_compare_exits_nonzero_on_a_bad_status_they_share(home):
    put(home, "baseline", answer_set(status=500), "answers.json")
    put(home, "R1", answer_set(status=500), "answers.json")
    got = tool("answers.py", home, "compare", "baseline", "R1")
    assert got.returncode == G.FAILED and "0 differences" in got.stdout and "not 200" in got.stdout


@pytest.mark.parametrize("r1,word", [
    (dict(valid=False), "marked invalid"),
    (dict(sha="different"), "workload_sha differs"),
    (dict(brain="d2"), "the Brain differs"),
])
def test_answers_compare_refuses_exit_3(home, r1, word):
    put(home, "baseline", answer_set(), "answers.json")
    put(home, "R1", answer_set(**r1), "answers.json")
    got = tool("answers.py", home, "compare", "baseline", "R1")
    assert got.returncode == G.REFUSED and word in got.stderr
    assert not (home / "results" / "R1" / "answers-vs-baseline.md").exists()


def test_selftest_exits_0_when_the_differ_reports_the_changes(home):
    put(home, "baseline", answer_set(), "answers.json")
    got = tool("answers.py", home, "selftest", "baseline")
    assert got.returncode == 0, got.stderr
    assert "FAIL" not in got.stdout and got.stdout.count("PASS") == 2


def test_selftest_exits_nonzero_on_failure(home):
    r = answer_set()
    r["answers"]["topics load"]["json"]["topics"] = [{"t": 1}]      # a reversal changes nothing: 2 of 3 reported
    put(home, "baseline", r, "answers.json")
    got = tool("answers.py", home, "selftest", "baseline")
    assert got.returncode == G.FAILED and "FAIL" in got.stdout


def test_selftest_exits_nonzero_with_no_baseline(home):
    assert tool("answers.py", home, "selftest", "baseline").returncode != 0


# ---- the gate's new duties -------------------------------------------------------------------


def test_a_binary_that_changes_during_the_work_invalidates_it(gate, tmp_path):
    exe = tmp_path / "front.exe"
    exe.write_bytes(b"one")
    hold = G.take(kind="k", holder="me", purpose="why", code={"commit": "t", "dir": "t"})
    hold.watch_binaries([{"path": str(exe), "sha256": G.sha256_of(exe)}])
    exe.write_bytes(b"two")
    rec = hold.finish()
    assert not rec["valid"] and any("a binary changed" in x for x in rec["invalid_reasons"])


def test_an_unchanged_binary_passes_and_is_checked(gate, tmp_path):
    exe = tmp_path / "front.exe"
    exe.write_bytes(b"one")
    hold = G.take(kind="k", holder="me", purpose="why", code={"commit": "t", "dir": "t"})
    hold.watch_binaries([{"path": str(exe), "sha256": G.sha256_of(exe)}])
    rec = hold.finish()
    assert rec["valid"] and [c for c in rec["checks"] if "front.exe" in c["check"]][0]["ok"]


def test_the_home_is_made_when_it_does_not_exist(tmp_path, monkeypatch):
    point_gate_at(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "LOCK", tmp_path / "new" / "deep" / "RUNLOCK")
    assert G.acquire({"pid": os.getpid()}) == []
    assert (tmp_path / "new" / "deep" / "RUNLOCK").exists()


# ---- the rows' own form, in the only PowerShell this machine has ------------------------------


def test_the_rows_form_survives_windows_powershell(tmp_path):
    """`--command $env:MENTIS_UNDER_TEST` in PowerShell 5.1: it passes the value with its quotes gone."""
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("no Windows PowerShell here")
    script = tmp_path / "show.py"
    script.write_text("import json, sys\nsys.path.insert(0, sys.argv[1])\nimport run_workload as R\n"
                      "print(json.dumps(R.parse_command(sys.argv[2])))\n")
    wanted = [sys.executable, "{brain}", "--port", "{port}", "--workspace", "{ws}", "--mars", "{mars}", "--run-dir", "{run}"]
    got = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command",
                          f"& '{sys.executable}' -B '{script}' '{TOOLS}' $env:MENTIS_UNDER_TEST"],
                         capture_output=True, text=True, timeout=120,
                         env={**os.environ, "MENTIS_UNDER_TEST": json.dumps(wanted)})
    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout) == wanted


def test_a_quoteless_value_is_taken_only_from_the_variable_it_matches(monkeypatch):
    wanted = [sys.executable, "{brain}", "--port", "{port}"]
    monkeypatch.setenv("MENTIS_UNDER_TEST", json.dumps(wanted))
    assert RW.parse_command(json.dumps(wanted).replace('"', "")) == wanted
    with pytest.raises(G.Refused) as e:
        RW.parse_command(json.dumps(wanted + ["--more"]).replace('"', ""))
    assert "not JSON" in e.value.why
    monkeypatch.delenv("MENTIS_UNDER_TEST")
    with pytest.raises(G.Refused):
        RW.parse_command(json.dumps(wanted).replace('"', ""))
